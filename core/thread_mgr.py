"""线程调度模块｜任务队列、并发控制、随机延迟、安全启停"""
import threading
import queue
import time
import random
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class ThreadManager:
    def __init__(self, max_workers: int = 10, delay_min: float = 0.05, delay_max: float = 0.3):
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.max_workers = max_workers
        self.delay_range = (delay_min, delay_max)
        self._pause_event = threading.Event()
        self._pause_event.set()  # 默认运行
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._processed = 0
        self._total = 0

    def set_total(self, total: int):
        self._total = total

    def add_task(self, task: tuple):
        self.task_queue.put(task)

    def pause(self): self._pause_event.clear()
    def resume(self): self._pause_event.set()
    def stop(self):
        self._stop_event.set()
        self._pause_event.set()

    def start(self, worker_func: Callable[[tuple], Any]):
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker, args=(worker_func,), name=f"Worker-{i}", daemon=True)
            t.start()

    def wait(self) -> bool:
        self.task_queue.join()
        return not self._stop_event.is_set()

    def _worker(self, func: Callable):
        while not self._stop_event.is_set():
            self._pause_event.wait()
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                result = func(task)
                self.result_queue.put(result)
            except Exception as e:
                self.result_queue.put(('error', task, str(e)))
            finally:
                self.task_queue.task_done()
                with self._lock:
                    self._processed += 1
                time.sleep(random.uniform(*self.delay_range))

    def progress(self) -> float:
        return self._processed / max(self._total, 1) * 100
