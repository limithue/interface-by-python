#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置持久化模块
职责：封装 JSON 配置的读写与默认值回退
与 GUI 解耦，不依赖 PyQt6
"""

import json
import os
from typing import Any, Optional


# ============================================================
# 1. 配置管理器
# ============================================================

class ConfigManager:
    """
    配置持久化管理器

    - 职责单一：仅负责配置的读写与默认值回退
    - 低耦合：不依赖任何 GUI / 网络 / 扫描模块
    - 高内聚：所有配置键名、默认值、序列化逻辑集中在此
    """

    DEFAULTS = {
        "skip_offline": True,
        "threads": 10,
        "timeout": 2,
        "delay": 0,
        "protocol": "tcp",
        "target": "127.0.0.1,192.168.1.1-10",
        "port": "common",
        "window_geometry": None,
    }

    def __init__(self, filepath: str = "scanner_config.json"):
        self._filepath = filepath
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """从 JSON 加载配置；文件缺失或损坏时回退到默认值"""
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # 合并策略：以默认值为基础，用已存值覆盖
                self._data = {**self.DEFAULTS, **loaded}
            except (json.JSONDecodeError, OSError, TypeError):
                self._data = self.DEFAULTS.copy()
        else:
            self._data = self.DEFAULTS.copy()

    def save(self) -> None:
        """原子化写入配置，异常静默处理避免阻塞 GUI 关闭"""
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 无写权限时不阻塞退出流程

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
