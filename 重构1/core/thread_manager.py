"""
core/thread_mgr.py
线程池管理与状态控制
"""
import threading
from concurrent.futures import ThreadPoolExecutor

class ThreadManager:
    def __init__(self, max_workers=20):
        self.max_workers = max_workers
        self.executor = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.lock = threading.Lock()
        self.total = 0
        self.processed = 0

    def start(self, total_tasks: int):
        self.total = total_tasks
        self.processed = 0
        self.stop_event.clear()
        self.pause_event.set()
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def submit(self, fn, *args, **kwargs):
        if self.executor and not self.stop_event.is_set():
            return self.executor.submit(self._wrapper, fn, *args, **kwargs)

    def _wrapper(self, fn, *args, **kwargs):
        self.pause_event.wait()
        if self.stop_event.is_set():
            return None
        try:
            return fn(*args, **kwargs)
        finally:
            with self.lock:
                self.processed += 1

    # 【F-1 修复】确保 progress 方法正确缩进在类内部
    def progress(self) -> float:
        with self.lock:
            if self.total == 0:
                return 0.0
            return (self.processed / self.total) * 100.0

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    # 【S-1 修复】安全的 wait 机制，避免死锁
    def wait(self):
        if self.executor:
            self.executor.shutdown(wait=True)
