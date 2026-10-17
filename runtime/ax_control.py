"""AX loopback endpoint backed by the main-thread C++ view-refresh v2 DLL."""
import ctypes as C
from ctypes import wintypes as W
import struct
import threading
import time
from engine_support import ROOT
from native_client import api, inject

LOCK = threading.Lock()

def snapshot(engine):
    gu = engine.q(engine.q(engine.base + 0x169d440))
    ui = engine.q(engine.base + 0x18d2660)
    if not gu or not ui:
        raise RuntimeError('Enter a match first')
    context = engine.q(engine.q(engine.q(ui + 0x50) + 0x20) + 0x18)
    return {'ok': True, 'status': 'ready', 'value': bool(engine.read(gu + 0x31, 1)[0]),
            'full_read': bool(engine.read(context + 0x29, 1)[0]),
            'read_ally_team': engine.i(context + 0x34),
            'ctrl_team': engine.i(context + 0x2c),
            'pid': engine.pid, 'backend': 'cpp_v2'}

def control(engine, value=None):
    if value is not None and type(value) is not bool:
        raise ValueError('AX value must be boolean')
    before = snapshot(engine)
    if value is None:
        return before
    k = api()
    k.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
    k.CreateMutexW.restype = W.HANDLE
    mutex = k.CreateMutexW(None, False, f'Local\\ViewRefresh2-Control-{engine.pid}')
    if not mutex:
        raise C.WinError(C.get_last_error())
    h = v = None
    held = False
    with LOCK:
        try:
            if k.WaitForSingleObject(mutex, 1000) not in (0, 0x80):
                raise RuntimeError('AX is busy')
            held = True
            name = f'Local\\ViewRefresh2-{engine.pid}'
            h = k.OpenFileMappingW(0xf001f, False, name)
            if not h:
                if C.get_last_error() != 2:
                    raise C.WinError(C.get_last_error())
                inject(engine.pid, ROOT/'native'/'view_refresh_v2.dll')
                h = k.OpenFileMappingW(0xf001f, False, name)
            if not h:
                raise C.WinError(C.get_last_error())
            v = k.MapViewOfFile(h, 0xf001f, 0, 0, 64)
            if not v:
                raise C.WinError(C.get_last_error())
            magic, version, pid, ready, state = struct.unpack('<5I', C.string_at(v, 20))
            if (magic, version, pid, ready) != (0x56523131, 2, engine.pid, 1):
                raise RuntimeError('AX native header mismatch')
            if state in (1, 2):
                raise RuntimeError('AX request pending')
            C.memmove(v + 20, struct.pack('<I', int(value)), 4)
            C.memmove(v + 32, struct.pack('<Q', k.GetTickCount64() + 3000), 8)
            C.memmove(v + 16, struct.pack('<I', 1), 4)
            end = time.monotonic() + 4
            while time.monotonic() < end:
                if struct.unpack('<I', C.string_at(v + 16, 4))[0] == 3:
                    break
                time.sleep(.005)
            else:
                raise TimeoutError('AX render callback timed out')
            fields = struct.unpack('<8IQ4IQ', C.string_at(v, 64))
            if fields[6]:
                raise RuntimeError(f'AX native status {fields[6]}')
            result = snapshot(engine)
            if result['value'] != value or result['full_read'] != value:
                raise RuntimeError('AX view state readback mismatch')
            result.update(thread=fields[7], invalid_icons_before=fields[9],
                          invalid_icons_after=fields[10], units=fields[11])
            return result
        finally:
            if v:
                k.UnmapViewOfFile(v)
            if h:
                k.CloseHandle(h)
            if held:
                k.ReleaseMutex(mutex)
            k.CloseHandle(mutex)

def execute(session, value=None):
    return control(session.engine, value)
