#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据契约层
职责：定义所有模块共享的不可变数据对象与配置结构
消除元组/字典混用风险，为动态字段导出提供标准化接口
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ============================================================
# 1. 端口状态枚举
# ============================================================

class PortState(Enum):
    """端口探测结果状态"""
    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"
    ERROR = "error"


# ============================================================
# 2. 扫描结果不可变数据对象
# ============================================================

@dataclass(frozen=True)
class ScanResult:
    """
    单次端口扫描结果

    Attributes:
        ip: 目标 IP 地址
        port: 目标端口号
        protocol: 协议类型（tcp/udp）
        state: 端口状态
        service: 识别到的服务名（可选）
        banner: 抓取到的 Banner 信息（可选）
        error_msg: 异常时的错误描述（可选）
        response_time_ms: 响应耗时毫秒（可选）
    """
    ip: str
    port: int
    protocol: str
    state: PortState
    service: Optional[str] = None
    banner: Optional[str] = None
    error_msg: Optional[str] = None
    response_time_ms: Optional[float] = None


# ============================================================
# 3. 扫描运行时配置
# ============================================================

@dataclass
class ScanConfig:
    """
    扫描任务运行时配置

    Attributes:
        protocol: 扫描协议（tcp/udp）
        threads: 并发线程数（1~20）
        timeout: 单次探测超时秒数
        delay_min: 随机延迟下限秒数
        delay_max: 随机延迟上限秒数
        skip_offline: 是否跳过 ICMP 探测离线的 IP
    """
    protocol: str
    threads: int
    timeout: int
    delay_min: float
    delay_max: float
    skip_offline: bool
