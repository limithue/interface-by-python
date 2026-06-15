#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描引擎层
职责：提供所有网络探测函数、存活检测逻辑与端口扫描器类
线程安全、异常分层、权限兼容
"""

import os
import socket
import subprocess
import sys
import time
import random
from typing import List, Optional, Tuple

from core.models import PortState, ScanResult
import config


# ============================================================
# 1. 跨平台彩色文本
# ============================================================

def colored(text: str, color: str) -> str:
    """
    为文本添加 ANSI 颜色

    Windows 下尝试启用 VT100 模式，失败则返回原色文本
    """
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
    code = config.COLORS.get(color, config.COLORS["white"])
    reset = config.COLORS["reset"]
    return f"{code}{text}{reset}"


# ============================================================
# 2. ICMP 校验和（RFC 1071）
# ============================================================

def _checksum(source_string: bytes) -> int:
    """计算 ICMP 报文校验和"""
    total = 0
    count_to = (len(source_string) // 2) * 2
    count = 0
    while count < count_to:
        this_val = source_string[count + 1] * 256 + source_string[count]
        total += this_val
        total &= 0xFFFFFFFF
        count += 2
    if count_to < len(source_string):
        total += source_string[len(source_string) - 1]
        total &= 0xFFFFFFFF
    total = (total >> 16) + (total & 0xFFFF)
    total += (total >> 16)
    answer = ~total
    answer &= 0xFFFF
    answer = answer >> 8 | (answer << 8 & 0xFF00)
    return answer


# ============================================================
# 3. TCP 单次探测
# ============================================================

def scan_tcp_once(ip: str, port: int, timeout: float) -> Tuple[PortState, Optional[str], Optional[str]]:
    """
    单次 TCP 全连接探测

    Returns:
        (state, service, banner)

    Raises:
        无——所有异常内部消化
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            # 尝试获取服务名
            try:
                service = socket.getservbyport(port, "tcp")
            except (OSError, ValueError):
                service = config.COMMON_PORTS.get(port, "unknown")

            # 尝试抓取 Banner
            s.settimeout(1.0)
            try:
                banner = s.recv(1024).decode("utf-8", errors="ignore").strip()
            except (socket.timeout, OSError):
                banner = None

            return PortState.OPEN, service, banner
    except socket.timeout:
        return PortState.FILTERED, None, None
    except ConnectionRefusedError:
        return PortState.CLOSED, None, None
    except OSError as e:
        return PortState.ERROR, None, str(e)


# ============================================================
# 4. TCP 扫描（含二次验证）
# ============================================================

def scan_tcp(ip: str, port: int, timeout: float) -> Tuple[PortState, Optional[str], Optional[str]]:
    """
    TCP 扫描，含二次验证机制

    首次探测为 OPEN 时，延迟 50ms 后再次探测确认，
    降低防火墙瞬时放行导致的误报率。
    """
    first = scan_tcp_once(ip, port, timeout)
    if first[0] == PortState.OPEN:
        time.sleep(0.05)
        second = scan_tcp_once(ip, port, timeout)
        if second[0] == PortState.OPEN:
            return second
        # 二次探测不一致，保守标记为 FILTERED
        return PortState.FILTERED, first[1], first[2]
    return first


# ============================================================
# 5. UDP 保守探测
# ============================================================

def scan_udp(ip: str, port: int, timeout: float) -> Tuple[PortState, Optional[str], Optional[str]]:
    """
    UDP 保守探测

    策略：
      - 发送空 UDP 包
      - 收到响应 → OPEN
      - 超时无响应 → FILTERED（保守策略，可能实际开放）
      - 收到 ICMP 不可达 → CLOSED
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"", (ip, port))

        try:
            data, _ = sock.recvfrom(1024)
            try:
                service = socket.getservbyport(port, "udp")
            except (OSError, ValueError):
                service = config.COMMON_PORTS.get(port, "unknown")
            return PortState.OPEN, service, data.decode("utf-8", errors="ignore").strip()
        except socket.timeout:
            return PortState.FILTERED, None, None
    except PermissionError as e:
        return PortState.ERROR, None, f"权限不足: {e}"
    except OSError as e:
        return PortState.ERROR, None, str(e)
    finally:
        if sock:
            sock.close()


# ============================================================
# 6. 存活探测
# ============================================================

def is_alive_icmp(ip: str, timeout: float) -> Optional[bool]:
    """
    ICMP 存活探测

    Returns:
        True  → 主机在线
        False → 主机离线
        None  → 权限不足（Windows 非管理员）

    Raises:
        无——所有异常内部消化
    """
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]

        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2,
            check=False,
        )
        return result.returncode == 0
    except PermissionError:
        return None
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        return False


def is_alive_tcp(ip: str, timeout: float) -> bool:
    """
    TCP 降级存活探测

    轮询 TCP_ALIVE_PORTS，任一端口可连接即认为存活。
    关键约束：无论结果如何，必须返回 True（绝不跳过 IP）。
    """
    ports = config.TCP_ALIVE_PORTS[:]
    random.shuffle(ports)
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    # 所有端口均不可达，仍返回 True，确保不跳过该 IP
    return True


def is_alive(ip: str, timeout: float) -> bool:
    """
    统一存活探测入口

    探测顺序：
      1. ICMP ping（需管理员权限）
      2. 若权限不足（None），降级为 TCP 探测
      3. 若 ICMP 明确离线（False），仍降级为 TCP 探测
      4. TCP 探测无论结果均返回 True

    设计意图：Windows 普通权限下 100% 可运行，绝不跳过 IP。
    """
    icmp_result = is_alive_icmp(ip, timeout)
    if icmp_result is True:
        return True
    # icmp_result 为 None（权限不足）或 False（离线）均降级 TCP
    return is_alive_tcp(ip, timeout)


# ============================================================
# 7. 端口扫描器类
# ============================================================

class PortScanner:
    """
    端口扫描核心实现

    内部消化所有异常，返回统一的 ScanResult。
    支持 TCP 全连接/UDP 扫描，含服务识别与 Banner 抓取。
    """

    def __init__(self, timeout: float = config.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._icmp_available = True

    def ping_host(self, ip: str) -> bool:
        """
        ICMP 探测；无管理员权限时自动降级为 TCP 探测

        首次权限不足后设置 _icmp_available = False，避免后续重复尝试。
        """
        if not self._icmp_available:
            return is_alive_tcp(ip, self.timeout)

        result = is_alive_icmp(ip, self.timeout)
        if result is True:
            return True
        if result is None:
            self._icmp_available = False
            return is_alive_tcp(ip, self.timeout)
        # result is False
        return is_alive_tcp(ip, self.timeout)

    def scan_single(self, ip: str, port: int, protocol: str) -> ScanResult:
        """
        统一扫描入口

        记录响应时间，消化所有异常为 ERROR 状态。
        """
        start = time.time()
        proto = protocol.lower()

        try:
            if proto == "tcp":
                state, service, banner = scan_tcp(ip, port, self.timeout)
            elif proto == "udp":
                state, service, banner = scan_udp(ip, port, self.timeout)
            else:
                return ScanResult(
                    ip=ip,
                    port=port,
                    protocol=proto,
                    state=PortState.ERROR,
                    error_msg=f"未知协议: {proto}",
                    response_time_ms=(time.time() - start) * 1000,
                )
            return ScanResult(
                ip=ip,
                port=port,
                protocol=proto,
                state=state,
                service=service,
                banner=banner,
                response_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ScanResult(
                ip=ip,
                port=port,
                protocol=proto,
                state=PortState.ERROR,
                error_msg=str(e),
                response_time_ms=(time.time() - start) * 1000,
            )
