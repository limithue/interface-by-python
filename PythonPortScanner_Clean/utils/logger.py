#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志管理模块
职责：基于 logging 标准库实现实时日志记录与文件导出
支持控制台与文件双输出，线程安全
"""

import logging
import os
from datetime import datetime
from typing import Optional


# ============================================================
# 1. 日志管理器
# ============================================================

class ScanLogger:
    """
    扫描工具日志管理器

    配置 logging.Logger，支持 DEBUG/INFO/WARNING/ERROR 级别。
    文件处理器按时间戳命名，格式包含时间、级别、消息。
    """

    _instances: dict = {}

    def __init__(
        self,
        name: str = "port_scanner",
        level: int = logging.INFO,
        log_dir: str = "./logs",
        console_output: bool = True,
    ):
        self.name = name
        self.log_dir = log_dir
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.propagate = False  # 防止污染 root logger

        # 避免重复添加 Handler
        if self._logger.handlers:
            return

        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)

        # 文件处理器
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"{name}_{timestamp}.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # 格式
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

        # 控制台处理器
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    @classmethod
    def get_logger(
        cls,
        name: str = "port_scanner",
        level: int = logging.INFO,
        log_dir: str = "./logs",
        console_output: bool = True,
    ) -> "ScanLogger":
        """获取或创建日志管理器实例（单例模式）"""
        if name not in cls._instances:
            cls._instances[name] = cls(name, level, log_dir, console_output)
        return cls._instances[name]

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)

    def set_level(self, level: int) -> None:
        """运行时切换日志级别"""
        self._logger.setLevel(level)
        for handler in self._logger.handlers:
            handler.setLevel(level)
