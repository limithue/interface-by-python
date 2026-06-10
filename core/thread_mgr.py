"""
core/thread_mgr.py
修复 progress 缩进致命错误与 wait() 死锁风险
"""
import threading
from concurrent.futures import ThreadPoolExecutor

class ThreadManager:
    def __init__(self, max_workers=20):
        self._max_workers = max_workers
        self._executor = None
        self._lock = threading.Lock()
        self._total = 0
        self._processed = 0
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行

    def start(self, total_tasks):
        self._total = total_tasks
        self._processed = 0
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    def submit(self, fn, *args, **kwargs):
        if self._executor and not self._stop_event.is_set():
            return self._executor.submit(self._wrapper, fn, *args, **kwargs)

    def _wrapper(self, fn, *args, **kwargs):
        self._pause_event.wait()  # 暂停控制
        if self._stop_event.is_set():
            return None
        try:
            return fn(*args, **kwargs)
        finally:
            with self._lock:
                self._processed += 1

    # 【F-1 修复】：确保 progress 方法正确缩进在类内部
    def progress(self) -> float:
        with self._lock:
            if self._total == 0:
                return 0.0
            return (self._processed / self._total) * 100.0

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()  # 解除暂停以允许线程退出
        if self._executor:
            # cancel_futures=True (Python 3.9+) 取消尚未开始的任务
            self._executor.shutdown(wait=False, cancel_futures=True)

    # 【S-1 修复】：安全的 wait 机制，避免 GUI 主线程死锁
    def wait(self, timeout=None):
        if self._executor:
            self._executor.shutdown(wait=True)
