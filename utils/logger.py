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
