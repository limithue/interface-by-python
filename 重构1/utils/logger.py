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


"""
utils/logger.py
高内聚、线程安全的日志管理模块
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

class ScanLogger:
    _loggers = {}

    @classmethod
    def get_logger(cls, name="portscanner", level=logging.INFO, log_dir="logs"):
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 【S-1 修复】：清空已有 Handler，防止多次调用导致日志重复输出
        if logger.hasHandlers():
            logger.handlers.clear()

        # 控制台 Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

        # 【G-1 修复】：使用 RotatingFileHandler 实现日志轮转 (10MB/5个备份)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"scan_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

        # 【S-2 修复】：阻止日志向 root logger 传播，避免污染第三方库(如PyQt6)日志
        logger.propagate = False 

        cls._loggers[name] = logger
        return logger

# 全局默认实例
logger = ScanLogger.get_logger()
