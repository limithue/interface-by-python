"""
utils/logger.py
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from utils.path_helper import get_data_path

class ScanLogger:
    _loggers = {}

    @classmethod
    def get_logger(cls, name="portscanner", level=logging.INFO):
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        if logger.hasHandlers():
            logger.handlers.clear()

        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

        # 【关键修复 2】：使用 get_data_path 确保日志写在 EXE 真实同级目录
        log_file = get_data_path(f"logs/scan_{datetime.now().strftime('%Y%m%d')}.log")
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

        logger.propagate = False 
        cls._loggers[name] = logger
        return logger

logger = ScanLogger.get_logger()
