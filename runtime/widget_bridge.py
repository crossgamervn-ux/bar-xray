"""Minimal file-IPC adapter for the AX widget; no TCP or gameplay-order endpoint."""
import argparse
import ctypes
import json
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
from engine_support import Engine, discover, ROOT
from native_client import NativeClient, inject
from ax_control import control
import file_ipc

class Session:
    def __init__(self, token):
        self.token = token
        self.lock = threading.Lock()
        self.engine = None
        self.native = None

    def close(self):
        if self.native is not None:
            self.native.close()
            self.native = None
        if self.engine is not None:
            self.engine.__exit__()
            self.engine = None

    def dispatch(self, request):
        if request.get('op') != 'ax' or request.get('token') != self.token:
            raise ValueError('Invalid AX request')
        value = request.get('value')
        if value is not None and type(value) is not bool:
            raise ValueError('AX value must be boolean')
        with self.lock:
            try:
                pids = discover()
                if len(pids) != 1:
                    self.close()
                    raise RuntimeError('Start exactly one reference-engine match')
                if self.engine is None or self.engine.pid != pids[0]:
                    self.close()
                    self.engine = Engine(pids[0])
                if self.engine.has_debugger():
                    raise RuntimeError('Detach debugger before loading resident hooks')
                if value is not None and self.native is None:
                    try:
                        self.native = NativeClient(pids[0])
                    except OSError as error:
                        if error.winerror != 2:
                            raise
                        inject(pids[0], ROOT / 'native' / 'autododge_native.dll')
                        self.native = NativeClient(pids[0])
                    deadline = time.monotonic() + 5
                    while not self.native.stats()['thread_id']:
                        if time.monotonic() > deadline:
                            raise TimeoutError('Enter a running, rendering match')
                        time.sleep(.05)
                return control(self.engine, value)
            except Exception:
                self.close()
                raise


def install(data):
    state = data / 'LuaUI/Config/ax_review'
    state.mkdir(parents=True, exist_ok=True)
    token_file = state / 'token.txt'
    token = token_file.read_text().strip() if token_file.exists() else secrets.token_hex(32)
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Unexpected local token format')
    token_file.write_text(token, encoding='ascii')
    templates = ROOT.parent / 'reference/widgets'
    for relative, template in [('LuaUI/Widgets/ax.lua', 'ax.lua'), ('LuaUI/Config/op_file_client.lua', 'op_file_client.lua')]:
        target = data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = state / (str(time.time_ns()) + '-' + target.name + '.bak')
            shutil.copy2(target, backup)
        text = (templates / template).read_text(encoding='utf-8').replace('__TOKEN__', token)
        target.write_text(text, encoding='utf-8')
    print('Installed AX widget and helper. Existing files backed up in LuaUI/Config/ax_review.')
    print('Run /luaui reload and enable AX in the widget list if necessary.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True, help='Existing BAR data directory')
    parser.add_argument('--install', action='store_true', help='Install widget/helper, generate a local token, then exit')
    args = parser.parse_args()
    if sys.platform != 'win32' or ctypes.sizeof(ctypes.c_void_p) != 8:
        parser.error('Windows and 64-bit Python required')
    data = args.data.resolve()
    if not data.is_dir():
        parser.error('--data must name an existing BAR data directory')
    if args.install:
        install(data)
        return
    token_file = data / 'LuaUI/Config/ax_review/token.txt'
    if not token_file.is_file():
        parser.error('Run once with --install first')
    session = Session(token_file.read_text().strip())
    file_ipc.CHANNELS = ('ax',)
    server = file_ipc.FileIPC(data / 'LuaUI/Config/op_ipc', session.dispatch)
    print('AX file bridge running. Do not run the old OP bridge at the same time. Ctrl+C to stop.')
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        server.pool.shutdown(wait=True, cancel_futures=True)
        session.close()

if __name__ == '__main__':
    main()
