"""Bounded JSON mailboxes. Transport only: existing dispatch validates all commands."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

CHANNELS = ('ax', 'ak', 'dodge', 'autoheal', 'aa', 'fleet', 'capture', 'reclaim', 'airraid')
LIMIT = 262144


class PollTimer:
    """Private high-resolution timer; does not change global Windows timer resolution."""
    def __init__(self):
        self.handle = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            self.ctypes = ctypes
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateWaitableTimerExW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self.kernel.CreateWaitableTimerExW.restype = wintypes.HANDLE
            self.kernel.SetWaitableTimer.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong), wintypes.LONG, wintypes.LPVOID, wintypes.LPVOID, wintypes.BOOL]
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.CreateWaitableTimerExW(None, None, 2, 0x1F0003)

    def wait(self, seconds):
        if self.handle:
            due = self.ctypes.c_longlong(-max(1, int(seconds * 10_000_000)))
            if self.kernel.SetWaitableTimer(self.handle, self.ctypes.byref(due), 0, None, None, False):
                self.kernel.WaitForSingleObject(self.handle, 1000)
                return
        time.sleep(seconds)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class FileIPC:
    def __init__(self, root, dispatch, interval=.003):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.dispatch = dispatch
        self.interval = interval
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix='op-file')
        self.seen = {}
        self.pending = {}
        self.completed = {channel: [] for channel in CHANNELS}
        # Never replay a command left on disk by an earlier bridge process.
        for channel in CHANNELS:
            try:
                self.seen[channel] = self.signature(self.path(channel, 'request'))
            except OSError:
                pass

    def path(self, channel, kind):
        return self.root / f'{channel}.{kind}.json'

    @staticmethod
    def signature(path):
        s = path.stat()
        return s.st_mtime_ns, s.st_size, s.st_ino

    def call(self, body):
        try:
            return self.dispatch(body)
        except Exception as exc:
            return {'ok': False, 'status': 'error', 'error': str(exc)}

    def tick(self):
        for channel in CHANNELS:
            pending = self.pending.get(channel)
            if pending:
                envelope, futures = pending
                if not all(f.done() for _, f in futures):
                    continue
                result = {'session': envelope['session'], 'batch': envelope['batch'],
                          'results': {str(i): f.result() for i, f in futures}}
                path = self.path(channel, 'response')
                try:
                    tmp = path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False), encoding='utf-8')
                    os.replace(tmp, path)
                except OSError:
                    continue  # Reader may momentarily hold the Windows file; retry next tick.
                del self.pending[channel]
            path = self.path(channel, 'request')
            try:
                sig = self.signature(path)
                if sig == self.seen.get(channel):
                    continue
                with path.open('rb') as file:
                    raw = file.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    self.seen[channel] = sig
                    continue
                envelope = json.loads(raw)
                if not isinstance(envelope, dict):
                    raise ValueError('Invalid envelope')
                items = envelope['items']
                if (envelope.get('version') != 1 or not isinstance(envelope['session'], str)
                        or len(envelope['session']) > 128 or type(envelope['batch']) is not int
                        or not isinstance(items, list) or not 1 <= len(items) <= 32):
                    raise ValueError('Invalid envelope')
                ids = set()
                for item in items:
                    if not isinstance(item, dict) or type(item['id']) is not int or item['id'] in ids or not isinstance(item['body'], dict):
                        raise ValueError('Invalid request')
                    ids.add(item['id'])
                    body = item['body']
                    if (channel == 'ax' and body.get('op') != 'ax') or (channel != 'ax' and body.get('channel', 'dodge') != channel):
                        raise ValueError('Channel mismatch')
                self.seen[channel] = sig
                key = (envelope['session'], envelope['batch'])
                if key in self.completed[channel]:
                    continue
                # Old offline commands must not execute after reconnect.
                if time.time_ns() - sig[0] > 3_000_000_000:
                    continue
                self.completed[channel].append(key)
                self.completed[channel] = self.completed[channel][-64:]
                self.pending[channel] = envelope, [(item['id'], self.pool.submit(self.call, item['body'])) for item in items]
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def run(self):
        timer = PollTimer()
        try:
            while not self.stop.is_set():
                self.tick()
                timer.wait(self.interval)
        finally:
            timer.close()

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
