"""Windows x64 resident DLL loader and non-debugger shared-memory transport."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import struct, time, threading
from engine_support import kernel, snapshot, ModuleEntry

SIZE=64+64*2048
STATUS={0:'send_function_returned',1:'expired',2:'superseded',3:'invalid_unit',4:'wrong_team_or_spectator',
        5:'synced_context',6:'invalid_command',7:'stale_position',8:'disabled'}

def api():
    k=kernel()
    defs={
      'Module32NextW':([W.HANDLE,C.POINTER(ModuleEntry)],W.BOOL),
      'GetModuleHandleW':([W.LPCWSTR],W.HMODULE),
      'GetProcAddress':([W.HMODULE,C.c_char_p],C.c_void_p),
      'LoadLibraryExW':([W.LPCWSTR,W.HANDLE,W.DWORD],W.HMODULE),
      'FreeLibrary':([W.HMODULE],W.BOOL),
      'VirtualAllocEx':([W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,W.DWORD],C.c_void_p),
      'VirtualFreeEx':([W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD],W.BOOL),
      'WriteProcessMemory':([W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)],W.BOOL),
      'CreateRemoteThread':([W.HANDLE,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,W.DWORD,C.c_void_p],W.HANDLE),
      'WaitForSingleObject':([W.HANDLE,W.DWORD],W.DWORD),
      'GetExitCodeThread':([W.HANDLE,C.POINTER(W.DWORD)],W.BOOL),
      'OpenFileMappingW':([W.DWORD,W.BOOL,W.LPCWSTR],W.HANDLE),
      'MapViewOfFile':([W.HANDLE,W.DWORD,W.DWORD,W.DWORD,C.c_size_t],C.c_void_p),
      'UnmapViewOfFile':([C.c_void_p],W.BOOL),
      'OpenMutexW':([W.DWORD,W.BOOL,W.LPCWSTR],W.HANDLE),
      'ReleaseMutex':([W.HANDLE],W.BOOL),
      'GetTickCount64':([],C.c_uint64),
    }
    for name,(args,result) in defs.items():
        fn=getattr(k,name);fn.argtypes=args;fn.restype=result
    return k

def modules(pid):
    k=api();h=snapshot(k,8,pid)
    try:
        entry=ModuleEntry();entry.size=C.sizeof(entry)
        ok=k.Module32FirstW(h,C.byref(entry))
        while ok:
            yield {'name':entry.name.lower(),'path':entry.path,'base':entry.base,'size':entry.image_size}
            ok=k.Module32NextW(h,C.byref(entry))
    finally:k.CloseHandle(h)

def remote_export(pid,module,symbol):
    k=api();local=k.GetModuleHandleW(module)
    address=k.GetProcAddress(local,symbol)
    if not address:raise C.WinError(C.get_last_error())
    # Resolve forwarded exports in their actual owning module, not a guessed base.
    import os
    owner=next(m for m in modules(os.getpid()) if m['base']<=address<m['base']+m['size'])
    remote=next(m for m in modules(pid) if m['name']==owner['name'])
    return remote['base']+address-owner['base']

def remote_call(k,process,address,arg):
    thread=k.CreateRemoteThread(process,None,0,address,arg,0,None)
    if not thread:raise C.WinError(C.get_last_error())
    try:
        if k.WaitForSingleObject(thread,15000)!=0:raise TimeoutError('Remote initialization still running; do not reinject')
        result=W.DWORD()
        if not k.GetExitCodeThread(thread,C.byref(result)):raise C.WinError(C.get_last_error())
        return result.value
    finally:k.CloseHandle(thread)

def inject(pid,dll):
    dll=Path(dll).resolve(); k=api()
    existing=next((m for m in modules(pid) if m['name']==dll.name.lower()),None)
    if existing:raise RuntimeError('DLL already loaded but transport unavailable; restart game instead of reinjecting')
    local=k.LoadLibraryExW(str(dll),None,1) # map only, do not run DllMain locally
    if not local:raise C.WinError(C.get_last_error())
    try:
        start=k.GetProcAddress(local,b'OpStart')
        if not start:raise RuntimeError('OpStart export missing')
        rva=start-local
    finally:k.FreeLibrary(local)
    process=k.OpenProcess(0x43a,False,pid)
    if not process:raise C.WinError(C.get_last_error())
    mem=None; completed=False
    try:
        path=str(dll).encode('utf-16-le')+b'\0\0'
        mem=k.VirtualAllocEx(process,None,len(path),0x3000,4)
        if not mem:raise C.WinError(C.get_last_error())
        done=C.c_size_t(); buf=C.create_string_buffer(path)
        if not k.WriteProcessMemory(process,mem,buf,len(path),C.byref(done)) or done.value!=len(path):raise C.WinError(C.get_last_error())
        remote_call(k,process,remote_export(pid,'kernel32.dll',b'LoadLibraryW'),mem)
        completed=True
        remote=next((m for m in modules(pid) if m['name']==dll.name.lower()),None)
        if not remote:raise RuntimeError('DLL load failed')
        result=remote_call(k,process,remote['base']+rva,None)
        if result:raise RuntimeError(f'OpStart failed: {result}; restart game before retry')
    finally:
        if mem and completed:k.VirtualFreeEx(process,mem,0,0x8000)
        k.CloseHandle(process)

class NativeClient:
    def __init__(self,pid):
        self.pid=pid;self.k=api();self.mapping=None;self.view=None;self.mutex=None
        self.local=threading.RLock();self.serial=0;self.owned=set();self.abandoned=set()
        try:
            self.mapping=self.k.OpenFileMappingW(0xf001f,False,f'Local\\AutoDodgeOP-{pid}')
            if not self.mapping:raise C.WinError(C.get_last_error())
            self.view=self.k.MapViewOfFile(self.mapping,0xf001f,0,0,SIZE)
            if not self.view:raise C.WinError(C.get_last_error())
            self.mutex=self.k.OpenMutexW(0x100001,False,f'Local\\AutoDodgeOP-Lock-{pid}')
            if not self.mutex:raise C.WinError(C.get_last_error())
            magic,version,remote_pid,ready=struct.unpack('<IIII',self.read(0,16))
            if (magic,version,remote_pid,ready)!=(0x4f504e31,1,pid,1):raise RuntimeError('Resident bridge header mismatch')
        except Exception:self.close();raise
    def read(self,offset,n):return C.string_at(self.view+offset,n)
    def write(self,offset,data):C.memmove(self.view+offset,data,len(data))
    def lock(self):
        if self.k.WaitForSingleObject(self.mutex,1000) not in (0,0x80):raise TimeoutError('Shared-memory producer lock unavailable')
    def stats(self):
        v=struct.unpack('<IIIIQQQQIIQ',self.read(0,64))
        return dict(pid=v[2],ready=bool(v[3]),heartbeat_age_ms=self.k.GetTickCount64()-v[4],updates=v[5],
                    sends=v[6],rejects=v[7],thread_id=v[8],enabled=bool(v[9]),max_drain_us=v[10])
    def cancel(self,uid):
        with self.local:
            self.lock()
            try:
                for i in range(64):
                    off=64+i*2048
                    state,_,_,unit=struct.unpack('<IIIi',self.read(off,16))
                    if state in (1,2) and (uid is None or unit==uid):self.write(off+8,struct.pack('<I',1))
            finally:self.k.ReleaseMutex(self.mutex)
    def enqueue(self,unit,commands,origin,ttl_ms=1500):
        if not 1<=len(commands)<=31:raise ValueError('Expected 1..31 commands')
        with self.local:
            self.lock()
            try:
                for i in list(self.abandoned):
                    off=64+i*2048
                    if struct.unpack('<I',self.read(off,4))[0]==3:
                        self.write(off,b'\0'*4);self.abandoned.remove(i)
                index=next((i for i in range(64) if i not in self.owned and struct.unpack('<I',self.read(64+i*2048,4))[0]==0),None)
                if index is None:raise RuntimeError('Resident request queue full')
                off=64+index*2048;self.serial=(self.serial+1)&0xffffffff
                blob=bytearray(2048)
                struct.pack_into('<IIIiQQ3fIIIQ',blob,0,0,self.serial,0,unit['unit_id'],int(unit['unit_ptr'],16),
                                 self.k.GetTickCount64()+ttl_ms,*origin,len(commands),0,0,0)
                for n,c in enumerate(commands):
                    p=c['params']
                    struct.pack_into('<iiiIIIB3x8f',blob,64+n*60,c['id'],-1,0x7fffffff,0xffffffff,len(p),0,c['options'],*(p+[0]*(8-len(p))))
                self.write(off,bytes(blob));self.owned.add(index)
                self.write(off,struct.pack('<I',1))
            finally:self.k.ReleaseMutex(self.mutex)
        return index,time.perf_counter(),time.monotonic()+ttl_ms/1000+1
    def wait(self,ticket):
        index,begin,deadline=ticket
        off=64+index*2048
        try:
            while time.monotonic()<deadline:
                if struct.unpack('<I',self.read(off,4))[0]==3:
                    status,elapsed=struct.unpack('<II',self.read(off+48,8))
                    return {'ok':status==0,'status':STATUS.get(status,f'native_error_{status}'),
                            'latency_ms':round((time.perf_counter()-begin)*1000,3),'native_us':elapsed,'backend':'resident_cpp'}
                time.sleep(.001)
            return {'ok':False,'status':'native_timeout','backend':'resident_cpp'}
        finally:
            with self.local:
                self.lock()
                try:
                    if struct.unpack('<I',self.read(off,4))[0]==3:self.write(off,b'\0'*4)
                    else:self.write(off+8,struct.pack('<I',1));self.abandoned.add(index)
                    self.owned.discard(index)
                finally:self.k.ReleaseMutex(self.mutex)
    def submit(self,unit,commands,origin,ttl_ms=1500):
        return self.wait(self.enqueue(unit,commands,origin,ttl_ms))
    def close(self):
        if self.view:self.k.UnmapViewOfFile(self.view);self.view=None
        if self.mapping:self.k.CloseHandle(self.mapping);self.mapping=None
        if self.mutex:self.k.CloseHandle(self.mutex);self.mutex=None
