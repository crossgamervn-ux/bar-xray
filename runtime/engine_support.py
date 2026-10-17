"""Build verification, process discovery and read-only unit snapshots for Windows x64."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import math
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
SHA256='2b5362606e697d9f81bdb8cda7ecad9951957d9de8ad516f79f337d905351e3b'
RVA=0xDA0FB0
PREFIX=bytes.fromhex('4157415641554154555756534883ec58')

class ProcessEntry(C.Structure):
    _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),
              ('heap',C.c_size_t),('module',W.DWORD),('threads',W.DWORD),
              ('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]

class ModuleEntry(C.Structure):
    _fields_=[('size',W.DWORD),('module_id',W.DWORD),('pid',W.DWORD),
              ('global_usage',W.DWORD),('process_usage',W.DWORD),('base',C.c_void_p),
              ('image_size',W.DWORD),('module',W.HMODULE),('name',W.WCHAR*256),('path',W.WCHAR*260)]

def kernel():
    k=C.WinDLL('kernel32',use_last_error=True)
    declarations={
        'CreateToolhelp32Snapshot':([W.DWORD,W.DWORD],W.HANDLE),
        'Process32FirstW':([W.HANDLE,C.POINTER(ProcessEntry)],W.BOOL),
        'Process32NextW':([W.HANDLE,C.POINTER(ProcessEntry)],W.BOOL),
        'Module32FirstW':([W.HANDLE,C.POINTER(ModuleEntry)],W.BOOL),
        'OpenProcess':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'ReadProcessMemory':([W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)],W.BOOL),
        'CheckRemoteDebuggerPresent':([W.HANDLE,C.POINTER(W.BOOL)],W.BOOL),
        'CloseHandle':([W.HANDLE],W.BOOL),
    }
    for name,(args,result) in declarations.items():
        function=getattr(k,name);function.argtypes=args;function.restype=result
    return k

def snapshot(k,flags,pid):
    handle=k.CreateToolhelp32Snapshot(flags,pid)
    if handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    return handle

def discover():
    k=kernel();handle=snapshot(k,2,0);found=[]
    try:
        entry=ProcessEntry();entry.size=C.sizeof(entry)
        ok=k.Process32FirstW(handle,C.byref(entry))
        while ok:
            if entry.exe.lower()=='spring.exe':found.append(entry.pid)
            ok=k.Process32NextW(handle,C.byref(entry))
    finally:k.CloseHandle(handle)
    return found

def module_for_pid(pid):
    k=kernel();handle=snapshot(k,8,pid)
    try:
        entry=ModuleEntry();entry.size=C.sizeof(entry)
        if not k.Module32FirstW(handle,C.byref(entry)):raise C.WinError(C.get_last_error())
        return Path(entry.path),entry.base
    finally:k.CloseHandle(handle)

def verify(path):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('Unsupported engine build (SHA256 mismatch). Re-analyze this executable; do not reuse these RVAs.')

def file_prefix(path,target_rva,length=16):
    b=path.read_bytes();pe=struct.unpack_from('<I',b,60)[0]
    count=struct.unpack_from('<H',b,pe+6)[0]
    table=pe+24+struct.unpack_from('<H',b,pe+20)[0]
    for i in range(count):
        _,rva,size,raw=struct.unpack_from('<IIII',b,table+40*i+8)
        if rva<=target_rva and target_rva+length<=rva+size:
            return b[raw+target_rva-rva:raw+target_rva-rva+length].hex()
    raise ValueError('Function RVA outside file sections')

class Engine:
    def __init__(self,pid):
        self.pid=pid;self.path,self.base=module_for_pid(pid);verify(self.path)
        self.k=kernel();self.handle=self.k.OpenProcess(0x410,False,pid)
        if not self.handle:raise C.WinError(C.get_last_error())
    def __enter__(self):return self
    def __exit__(self,*args):self.k.CloseHandle(self.handle)
    def read(self,address,size):
        buffer=C.create_string_buffer(size);done=C.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,address,buffer,size,C.byref(done)) or done.value!=size:
            raise C.WinError(C.get_last_error())
        return buffer.raw
    def q(self,address):return struct.unpack('<Q',self.read(address,8))[0]
    def i(self,address):return struct.unpack('<i',self.read(address,4))[0]
    def own_team(self):
        gu=self.q(self.q(self.base+0x169d440))
        if not gu:raise ValueError('Game state not initialized')
        if self.read(gu+0x30,1)!=b'\0':raise ValueError('Spectator; own-unit commands unavailable')
        return self.i(gu+0x20)
    def table(self):
        handler=self.q(self.base+0x169d8b0)
        count=self.i(handler+0x1920)
        ptr=self.q(handler+0xa8)
        if not ptr or not 0<count<=1_000_000:raise ValueError('No active unit table; enter a match first')
        return ptr,count
    def describe(self,unit_id,pointer,team):
        actual_team=self.i(pointer+0x1d8)
        if actual_team!=team:raise ValueError('Unit is not on your own team')
        health=struct.unpack('<f',self.read(pointer+0x19c,4))[0]
        xyz=struct.unpack('<fff',self.read(pointer+0xe0,12))
        if not math.isfinite(health) or health<=0 or not all(math.isfinite(v) for v in xyz):
            raise ValueError('Unit is dead or has invalid state')
        return {'unit_id':unit_id,'unit_ptr':hex(pointer),'team':actual_team,'health':health,'position':list(xyz)}
    def unit(self,unit_id):
        ptr,count=self.table()
        if not 0<=unit_id<count:raise ValueError('Unit ID outside table')
        pointer=self.q(ptr+8*unit_id)
        if not pointer:raise ValueError('Unit no longer exists')
        return self.describe(unit_id,pointer,self.own_team())
    def target_unit(self,unit_id):
        # Target lookup accepts other teams; command sender still uses unit().
        ptr,count=self.table()
        if type(unit_id) is not int or not 0<=unit_id<count:raise ValueError('Target ID outside table')
        pointer=self.q(ptr+8*unit_id)
        if not pointer:raise ValueError('Target no longer exists')
        return self.describe(unit_id,pointer,self.i(pointer+0x1d8))
    def units(self):
        ptr,count=self.table();team=self.own_team()
        pointers=struct.unpack('<'+'Q'*count,self.read(ptr,count*8))
        result=[]
        for unit_id,pointer in enumerate(pointers):
            if not pointer:continue
            try:result.append(self.describe(unit_id,pointer,team))
            except (OSError,ValueError):pass
        return result
    def has_debugger(self):
        present=W.BOOL()
        if not self.k.CheckRemoteDebuggerPresent(self.handle,C.byref(present)):raise C.WinError(C.get_last_error())
        return bool(present.value)
