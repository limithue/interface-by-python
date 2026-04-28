exporter.py"""日志配置模块｜控制台+文件双输出，线程安全"""
import logging
import os
from config import LOG_FILE, OUTPUT_DIR

def setup_logger():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_h = logging.FileHandler(os.path.join(OUTPUT_DIR, LOG_FILE), encoding='utf-8')
    file_h.setFormatter(fmt)
    root.addHandler(file_h)
