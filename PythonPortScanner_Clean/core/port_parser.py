#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端口解析模块
职责：支持 common、单端口、端口段、离散端口全格式解析
纯函数设计，与 IP 解析层对称
"""

from typing import List


# ============================================================
# 1. 常用端口列表（与 config.COMMON_PORTS 键一致）
# ============================================================

COMMON_PORTS_LIST = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
    993, 995, 1080, 1433, 1521, 2049, 3306, 3389,
    5000, 5432, 5900, 5901, 6379, 6667, 8080, 8443,
    27017, 3307,
]


# ============================================================
# 2. 主解析入口
# ============================================================

def resolve_ports(text: str) -> List[int]:
    """
    解析端口字符串，支持多种格式混合输入

    支持格式：
      - common: 返回内置常用端口列表
      - 单端口: 80
      - 端口段: 1-1000
      - 离散端口: 22,80,443
      - 混合: common,8080,9000-9100

    Args:
        text: 用户输入的端口字符串

    Returns:
        去重并排序的端口列表（已过滤 1-65535 范围外值）

    Raises:
        ValueError: 空输入或无有效端口
    """
    text = text.strip().lower()
    if not text:
        raise ValueError("端口输入不能为空")

    if text == "common":
        return COMMON_PORTS_LIST[:]

    ports: set = set()

    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            # 端口段
            try:
                start_str, end_str = part.split("-", 1)
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    raise ValueError(f"端口段起始大于结束: {part}")
                for p in range(start, end + 1):
                    if 1 <= p <= 65535:
                        ports.add(p)
            except ValueError as e:
                if "端口段" in str(e):
                    raise
                raise ValueError(f"端口段格式错误: {part}") from e
        else:
            # 单端口
            try:
                p = int(part)
                if 1 <= p <= 65535:
                    ports.add(p)
            except ValueError as e:
                raise ValueError(f"无效端口号: {part}") from e

    if not ports:
        raise ValueError("无有效端口，请输入 1-65535 范围内的端口")

    return sorted(ports)
