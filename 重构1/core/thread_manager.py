#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线程管理模块
职责：基于 threading + queue 实现轻量级线程池
支持暂停、恢复、停止、进度查询
"""

import queue
import random
import threading
import time
from typing import Callable, List, Tuple

from core.models import PortState, ScanResult


# ============================================================
# 1. 线程池调度器
# ============================================================

class ThreadManager:
    """
    基于 threading + queue 的轻量级线程池

    支持暂停、恢复、停止，线程复用避免频繁创建销毁。
    所有共享状态均受锁保护，确保线程安全。
    """

    def __init__(
        self,
        max_workers: int,
        delay_min: float = 0.0,
        delay_max: float = 0.0,
    ):
        self.max_workers = max_workers
        self.delay_min = delay_min
        self.delay_max = delay_max

        self.task_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()

        self._total = 0
        self._processed = 0
        self._paused = False
        self._stopped = False

        self._pause_cond = threading.Condition()
        self._lock = threading.Lock()
        self._workers: List[threading.Thread] = []

    def set_total(self, n: int) -> None:
        """设置总任务数，用于进度计算"""
        with self._lock:
            self._total = n

    def progress(self) -> float:
        """返回 0.0 ~ 100.0 的进度百分比"""
        with self._lock:
            if self._total == 0:
                return 0.0
            return (self._processed / self._total) * 100.0

    def pause(self) -> None:
        """暂停扫描，工作线程进入条件等待"""
        with self._pause_cond:
            self._paused = True

    def resume(self) -> None:
        """恢复扫描，唤醒所有等待线程"""
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def stop(self) -> None:
        """
        停止扫描

        设置停止标志，清空任务队列，唤醒线程使其退出。
        """
        with self._pause_cond:
            self._stopped = True
            self._paused = False
            # 清空未处理的任务队列
            while not self.task_queue.empty():
                try:
                    self.task_queue.get_nowait()
                except queue.Empty:
                    break
            self._pause_cond.notify_all()

    def start(self, worker_func: Callable[[Tuple[str, int, str]], ScanResult]) -> None:
        """
        启动工作线程

        Args:
            worker_func: 任务处理函数，接收 (ip, port, protocol) 元组
        """
        self._workers = []
        for _ in range(self.max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                args=(worker_func,),
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    def _worker_loop(
        self,
        worker_func: Callable[[Tuple[str, int, str]], ScanResult],
    ) -> None:
        """工作线程主循环"""
        while True:
            # 检查暂停状态
            with self._pause_cond:
                while self._paused and not self._stopped:
                    self._pause_cond.wait(timeout=0.5)
                if self._stopped:
                    break

            # 获取任务
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                with self._lock:
                    if self._processed >= self._total:
                        break
                continue

            if self._stopped:
                break

            # 执行任务
            try:
                if self.delay_max > 0:
                    time.sleep(random.uniform(self.delay_min, self.delay_max))
                result = worker_func(task)
                self.result_queue.put(result)
            except Exception as e:
                # 防御：即使 worker_func 抛异常，也包装为 ERROR 结果入队
                ip, port, proto = task
                self.result_queue.put(
                    ScanResult(
                        ip=ip,
                        port=port,
                        protocol=proto,
                        state=PortState.ERROR,
                        error_msg=str(e),
                    )
                )
            finally:
                with self._lock:
                    self._processed += 1

    def wait(self) -> None:
        """等待所有工作线程结束（带超时）"""
        for t in self._workers:
            t.join(timeout=1.0)
