#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP 解析模块
职责：支持单 IP、IP 段、CIDR、域名全格式解析
纯函数设计，无 GUI / 网络 / 文件依赖
"""

import re
import socket
from typing import List


# ============================================================
# 1. 正则与常量
# ============================================================

_IP_PATTERN = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)
_CIDR_PATTERN = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/(\d{1,2})$"
)
_MAX_CIDR_PREFIX = 16   # 限制最大网段 /16
_MAX_RANGE_SIZE = 256   # 单段 IP 范围最大 256 个


# ============================================================
# 2. 辅助函数
# ============================================================

def _ip_to_int(ip: str) -> int:
    """将 IPv4 点分字符串转为 32 位整数"""
    parts = [int(p) for p in ip.split(".")]
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def _int_to_ip(n: int) -> str:
    """将 32 位整数转为 IPv4 点分字符串"""
    return f"{(n >> 24) & 0xff}.{(n >> 16) & 0xff}.{(n >> 8) & 0xff}.{n & 0xff}"


def _expand_cidr(cidr: str) -> List[str]:
    """
    将 CIDR 展开为 IP 列表

    Args:
        cidr: 如 "192.168.1.0/24"

    Returns:
        IP 字符串列表

    Raises:
        ValueError: 格式错误或前缀小于 _MAX_CIDR_PREFIX
    """
    match = _CIDR_PATTERN.match(cidr)
    if not match:
        raise ValueError(f"CIDR 格式错误: {cidr}")

    ip_str, prefix_str = match.groups()
    prefix = int(prefix_str)

    if prefix < _MAX_CIDR_PREFIX:
        raise ValueError(
            f"CIDR 前缀 /{prefix} 超出最大允许范围 /{_MAX_CIDR_PREFIX}，"
            f"防止误扫大网段"
        )
    if prefix > 32:
        raise ValueError(f"CIDR 前缀 /{prefix} 非法，最大为 /32")

    # 验证 IP 格式
    ip_int = _ip_to_int(ip_str)
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    network = ip_int & mask
    host_bits = 32 - prefix
    total = 1 << host_bits

    return [_int_to_ip(network + i) for i in range(total)]


def _expand_range(ip_range: str) -> List[str]:
    """
    将 IP 段（如 192.168.1.1-100）展开为列表

    Args:
        ip_range: 点分 IP 前缀 + 起始-结束，如 "192.168.1.10-20"

    Returns:
        IP 字符串列表

    Raises:
        ValueError: 格式错误或范围过大
    """
    if "-" not in ip_range:
        raise ValueError(f"IP 段格式错误（缺少 '-'）: {ip_range}")

    base_ip, end_part = ip_range.rsplit("-", 1)
    if "." not in base_ip:
        raise ValueError(f"IP 段格式错误: {ip_range}")

    prefix, start_part = base_ip.rsplit(".", 1)
    start = int(start_part)
    end = int(end_part)

    if end < start:
        raise ValueError(f"IP 段结束值小于起始值: {ip_range}")
    if (end - start + 1) > _MAX_RANGE_SIZE:
        raise ValueError(
            f"IP 段范围 {end - start + 1} 超出最大 {_MAX_RANGE_SIZE}"
        )

    return [f"{prefix}.{i}" for i in range(start, end + 1)]


# ============================================================
# 3. 主解析入口
# ============================================================

def resolve_targets(text: str) -> List[str]:
    """
    解析目标字符串，支持多种格式混合输入

    支持格式：
      - 单 IP: 192.168.1.1
      - IP 段: 192.168.1.10-20
      - CIDR: 192.168.1.0/24
      - 域名: example.com
      - 逗号分隔混合: 192.168.1.1,10.0.0.1-10,172.16.0.0/24

    Args:
        text: 用户输入的目标字符串

    Returns:
        去重且保序的 IP 字符串列表

    Raises:
        ValueError: 空输入、格式错误、无法解析域名
    """
    if not text or not text.strip():
        raise ValueError("目标 IP/域名不能为空")

    targets: List[str] = []

    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        # CIDR 检测
        if "/" in part:
            targets.extend(_expand_cidr(part))
            continue

        # IP 段检测
        if "-" in part and _IP_PATTERN.match(part.split("-")[0]):
            targets.extend(_expand_range(part))
            continue

        # 单 IP 或域名检测
        if _IP_PATTERN.match(part):
            # 简单验证每段 0-255
            groups = _IP_PATTERN.match(part).groups()
            if all(0 <= int(g) <= 255 for g in groups):
                targets.append(part)
            else:
                raise ValueError(f"IP 地址段超出 0-255: {part}")
        else:
            # 域名解析预检
            try:
                socket.getaddrinfo(part, None)
                targets.append(part)
            except socket.gaierror as e:
                raise ValueError(f"无法解析目标: {part}") from e

    # 去重并保序
    return list(dict.fromkeys(targets))
