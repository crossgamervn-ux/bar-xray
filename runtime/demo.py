"""Standalone wrapper around the retained AX implementation; no HTTP/file server."""
import argparse
import ctypes
import json
import sys
import time
from engine_support import Engine, discover, ROOT
from native_client import NativeClient, inject
from ax_control import control

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['status', 'on', 'off'])
    parser.add_argument('--pid', type=int, help='Select the test process explicitly')
    args = parser.parse_args()
    if sys.platform != 'win32' or ctypes.sizeof(ctypes.c_void_p) != 8:
        parser.error('Windows with 64-bit Python is required')
    pids = [args.pid] if args.pid else discover()
    if len(pids) != 1:
        parser.error('Start exactly one reference-engine match, or specify --pid')
    with Engine(pids[0]) as engine:
        # Engine verifies the complete executable hash before memory access.
        if engine.has_debugger():
            raise RuntimeError('Detach debugger before using resident hooks')
        if args.mode == 'status':
            print(json.dumps(control(engine), indent=2))
            return
        client = None
        try:
            try:
                client = NativeClient(engine.pid)
            except OSError as error:
                if error.winerror != 2:
                    raise
                inject(engine.pid, ROOT / 'native' / 'autododge_native.dll')
                client = NativeClient(engine.pid)
            deadline = time.monotonic() + 5
            while not client.stats()['thread_id']:
                if time.monotonic() > deadline:
                    raise TimeoutError('Engine callback has not established its thread; enter a running match')
                time.sleep(.05)
            print(json.dumps(control(engine, args.mode == 'on'), indent=2))
        finally:
            if client is not None:
                client.close()

if __name__ == '__main__':
    main()
