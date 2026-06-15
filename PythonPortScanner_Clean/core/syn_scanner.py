#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/syn_scanner.py —— SYN 半连接扫描模块（Stealth Scan）
===========================================================

职责：
  • 基于 Python 标准库实现 TCP SYN 半连接扫描（Stealth Scan）
  • 手动构造 IP 头 + TCP 头，设置 TCP Flags = SYN (0x02)
  • 发送 SYN 包后监听响应，依据 RFC 793 判定端口状态
  • 无管理员权限时自动降级为 TCP 全连接扫描
  • 与 PortScanner 通过 protocol="syn" 分支集成，零第三方依赖

设计原则：
  • 高内聚：所有 SYN 扫描逻辑集中在此模块（报文构造、发送、解析、降级）
  • 低耦合：仅暴露 SynScanner 类与 scan_syn() 函数，不依赖 GUI/主程序
  • 零副作用：不修改全局状态，不依赖外部配置
  • 防御性编程：所有异常内部消化，返回统一 PortState 枚举

扫描原理（三次握手 vs 半连接）：
  正常三次握手（日志记录）：
    客户端 ──SYN──→ 服务端
    客户端 ←─SYN+ACK─ 服务端
    客户端 ──ACK──→ 服务端  ← 连接建立，日志留痕

  SYN 半连接（隐蔽扫描）：
    客户端 ──SYN──→ 服务端
    客户端 ←─SYN+ACK─ 服务端  → 判定 OPEN，不回 ACK
    客户端 ←─RST──── 服务端  → 判定 CLOSED
    无响应 / 超时          → 判定 FILTERED

  优势：不完成三次握手，服务端不记录完整连接日志，隐蔽性高
  劣势：Windows 需管理员权限；无法获取 Banner；可能被防火墙拦截 SYN 包

合规声明：
  本模块仅限授权内网安全测试使用，严禁用于未授权网络扫描。
"""

import socket
import struct
import random
import time
import sys
import os
from typing import Tuple, Optional

from core.models import PortState


# ============================================================
# 1. 校验和计算（RFC 1071）
# ============================================================

def _checksum(source: bytes) -> int:
    """
    计算 16 位校验和（RFC 1071 标准算法）

    算法：将数据按 16 位字累加，溢出回卷，取反。
    用于 IP 头和 TCP 头的校验和字段计算。

    Args:
        source: 待计算校验和的字节数据

    Returns:
        16 位校验和整数（0~65535）
    """
    if len(source) % 2 == 1:
        source += b'\x00'
    s = 0
    for i in range(0, len(source), 2):
        word = (source[i] << 8) + source[i + 1]
        s += word
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


# ============================================================
# 2. IP 头构造（20 字节，无选项）
# ============================================================

def _build_ip_header(src_ip: str, dst_ip: str, payload_len: int) -> bytes:
    """
    构造 IPv4 头（RFC 791）

    字段结构（20 字节）：
      Version(4) + IHL(4) = 0x45  (IPv4, 头长 20 字节)
      TOS(8) = 0x00  (普通服务)
      Total Length(16) = IP 头(20) + TCP 头(20) + 数据
      Identification(16) = 随机值（用于分片重组）
      Flags(3) + Fragment Offset(13) = 0x4000  (DF=1, 不分片)
      TTL(8) = 64  (常见默认值)
      Protocol(8) = 6  (TCP)
      Header Checksum(16) = 待计算
      Source IP(32) = 本机 IP
      Destination IP(32) = 目标 IP

    Args:
        src_ip: 源 IP 地址（点分字符串）
        dst_ip: 目标 IP 地址（点分字符串）
        payload_len: TCP 头 + 数据的长度

    Returns:
        20 字节 IP 头
    """
    version_ihl = 0x45       # IPv4, IHL=5 (20字节)
    tos = 0x00
    total_length = 20 + payload_len
    identification = random.randint(0, 65535)
    flags_offset = 0x4000    # DF=1 (Don't Fragment)
    ttl = 64
    protocol = socket.IPPROTO_TCP  # 6
    checksum_placeholder = 0

    src = struct.pack('!4B', *[int(x) for x in src_ip.split('.')])
    dst = struct.pack('!4B', *[int(x) for x in dst_ip.split('.')])

    # 先构造无校验和的 IP 头
    header = struct.pack(
        '!BBHHHBBH',
        version_ihl, tos, total_length,
        identification, flags_offset,
        ttl, protocol, checksum_placeholder
    ) + src + dst

    # 计算并回填校验和
    cs = _checksum(header)
    header = struct.pack(
        '!BBHHHBBH',
        version_ihl, tos, total_length,
        identification, flags_offset,
        ttl, protocol, cs
    ) + src + dst

    return header


# ============================================================
# 3. TCP 头构造（20 字节，无选项）
# ============================================================

def _build_tcp_header(
    src_port: int,
    dst_port: int,
    seq_num: int,
    ack_num: int = 0,
    flags: int = 0x02,  # SYN = 0x02
    window: int = 65535,
) -> bytes:
    """
    构造 TCP 头（RFC 793）

    字段结构（20 字节）：
      Source Port(16)      = 随机源端口
      Destination Port(16) = 目标端口
      Sequence Number(32)  = 随机序列号
      Ack Number(32)       = 0 (SYN 包无确认号)
      Data Offset(4) + Reserved(6) + Flags(6) = 0x5002 (头长20字节, SYN标志)
      Window Size(16)      = 65535
      Checksum(16)         = 待计算（伪首部参与）
      Urgent Pointer(16)   = 0

    Args:
        src_port: 源端口号（随机生成）
        dst_port: 目标端口号
        seq_num: TCP 序列号（随机生成）
        ack_num: TCP 确认号（SYN 包为 0）
        flags: TCP 标志位（SYN=0x02）
        window: 窗口大小

    Returns:
        20 字节 TCP 头（无校验和，需后续回填）
    """
    data_offset = (20 // 4) << 4  # 头长 20 字节 → Data Offset = 5 → 5<<4 = 0x50
    doff_reserved = data_offset
    checksum_placeholder = 0
    urgent = 0

    header = struct.pack(
        '!HHIIBBHHH',
        src_port, dst_port,
        seq_num, ack_num,
        doff_reserved, flags,
        window, checksum_placeholder, urgent
    )

    return header


# ============================================================
# 4. 伪首部与 TCP 校验和计算
# ============================================================

def _build_pseudo_header(src_ip: str, dst_ip: str, tcp_len: int) -> bytes:
    """
    构造 TCP 校验和计算用的伪首部（12 字节）

    伪首部结构：
      Source IP(32) + Destination IP(32) + 保留(8) + Protocol(8) + TCP Length(16)

    注意：伪首部仅用于校验和计算，不实际发送。
    这是 TCP/IP 协议栈的设计要求（RFC 793）。

    Args:
        src_ip: 源 IP 地址
        dst_ip: 目标 IP 地址
        tcp_len: TCP 头 + 数据的长度

    Returns:
        12 字节伪首部
    """
    src = struct.pack('!4B', *[int(x) for x in src_ip.split('.')])
    dst = struct.pack('!4B', *[int(x) for x in dst_ip.split('.')])
    reserved = 0
    protocol = socket.IPPROTO_TCP  # 6
    return src + dst + struct.pack('!BBH', reserved, protocol, tcp_len)


def _calc_tcp_checksum(src_ip: str, dst_ip: str, tcp_header: bytes, data: bytes = b'') -> int:
    """
    计算 TCP 校验和（含伪首部）

    根据 RFC 793，TCP 校验和必须覆盖：
      伪首部（12 字节）+ TCP 头（20 字节）+ TCP 数据（可选）

    Args:
        src_ip: 源 IP 地址
        dst_ip: 目标 IP 地址
        tcp_header: TCP 头字节（可含占位校验和）
        data: TCP 数据（SYN 扫描通常为空）

    Returns:
        16 位校验和整数
    """
    pseudo = _build_pseudo_header(src_ip, dst_ip, len(tcp_header) + len(data))
    return _checksum(pseudo + tcp_header + data)


# ============================================================
# 5. 获取本机出口 IP 地址
# ============================================================

def _get_local_ip() -> str:
    """
    获取本机出口 IP 地址

    策略：通过 UDP 连接外部地址（不实际发送数据）获取本机网卡 IP。
    失败时回退到 127.0.0.1。

    Returns:
        本机 IP 地址字符串（点分格式）
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ============================================================
# 6. SYN 包发送与响应接收
# ============================================================

def _send_syn_packet(
    dst_ip: str,
    dst_port: int,
    timeout: float = 2.0,
) -> Tuple[Optional[bytes], Optional[Tuple[str, int]]]:
    """
    发送 TCP SYN 包并等待响应

    实现流程：
      1. 获取本机出口 IP
      2. 生成随机源端口和序列号
      3. 构造 TCP 头（无校验和）
      4. 计算 TCP 校验和（含伪首部）
      5. 回填校验和到 TCP 头
      6. 构造 IP 头
      7. 组装完整报文（IP 头 + TCP 头）
      8. 创建 Raw Socket (IPPROTO_TCP)
      9. 发送报文
      10. 非阻塞接收响应
      11. 关闭 Socket

    Args:
        dst_ip: 目标 IP 地址
        dst_port: 目标端口号
        timeout: 接收超时秒数

    Returns:
        (响应数据, (源IP, 源端口)) 或 (None, None) 表示超时/无响应

    Raises:
        PermissionError: 无管理员权限（Windows Raw Socket 限制）
        OSError: 网络接口不可用
    """
    src_ip = _get_local_ip()
    src_port = random.randint(30000, 60000)
    seq_num = random.randint(0, 0xFFFFFFFF)

    # 构造 TCP 头（先无校验和）
    tcp_header = _build_tcp_header(src_port, dst_port, seq_num, flags=0x02)
    tcp_checksum = _calc_tcp_checksum(src_ip, dst_ip, tcp_header)

    # 回填校验和（偏移 16 字节处，2 字节）
    tcp_header = tcp_header[:16] + struct.pack('!H', tcp_checksum) + tcp_header[18:]

    # 构造 IP 头
    ip_header = _build_ip_header(src_ip, dst_ip, len(tcp_header))

    # 完整报文
    packet = ip_header + tcp_header

    # 创建 Raw Socket 并发送
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    except PermissionError as e:
        raise PermissionError(
            "创建 Raw Socket 失败：Windows 下 SYN 扫描需要管理员权限。"
            "请以管理员身份运行程序，或改用 TCP 全连接扫描。"
        ) from e

    try:
        sock.settimeout(timeout)
        sock.sendto(packet, (dst_ip, 0))

        # 接收响应
        try:
            response, addr = sock.recvfrom(65535)
            return response, addr
        except socket.timeout:
            return None, None
    finally:
        sock.close()


# ============================================================
# 7. 响应报文解析
# ============================================================

def _parse_syn_response(response: bytes) -> Tuple[PortState, str]:
    """
    解析 SYN 扫描的响应报文，判定端口状态

    响应报文结构：
      [IP 头(20字节)] [TCP 头(20字节)] [数据]

    判定逻辑（保守策略）：
      • TCP Flags 含 SYN+ACK (0x12) → OPEN（端口开放，服务就绪）
      • TCP Flags 含 RST (0x04)     → CLOSED（端口关闭，无服务监听）
      • 其他 / 无响应 / 超时         → FILTERED（防火墙拦截或网络不可达）

    Args:
        response: 接收到的原始报文字节

    Returns:
        (PortState, 状态描述字符串)
    """
    if not response or len(response) < 40:
        return PortState.FILTERED, "响应报文过短或无效，可能为防火墙丢弃"

    # 跳过 IP 头（假设无选项，固定 20 字节）
    tcp_header = response[20:40]

    # 解析 TCP 标志位（偏移 13 字节处）
    flags = tcp_header[13]

    # 判断标志位
    syn_flag = flags & 0x02
    ack_flag = flags & 0x10
    rst_flag = flags & 0x04

    if syn_flag and ack_flag:
        return PortState.OPEN, "收到 SYN+ACK，端口开放（半连接未建立）"
    elif rst_flag:
        return PortState.CLOSED, "收到 RST，端口关闭"
    else:
        return PortState.FILTERED, f"收到异常响应 (Flags=0x{flags:02X})，可能为防火墙拦截"


# ============================================================
# 8. TCP 全连接降级扫描（无管理员权限时使用）
# ============================================================

def _tcp_connect_fallback(ip: str, port: int, timeout: float) -> Tuple[PortState, str]:
    """
    TCP 全连接扫描降级方案

    当无管理员权限无法创建 Raw Socket 时，使用标准 TCP 全连接探测。
    作为 SYN 扫描的降级方案，保证程序在普通权限下仍可运行。

    Args:
        ip: 目标 IP 地址
        port: 目标端口号
        timeout: 连接超时秒数

    Returns:
        (PortState, 状态描述字符串)
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return PortState.OPEN, "[降级] 无管理员权限，使用 TCP 全连接扫描确认开放"
    except socket.timeout:
        return PortState.FILTERED, "[降级] TCP 全连接超时，端口可能过滤或关闭"
    except ConnectionRefusedError:
        return PortState.CLOSED, "[降级] TCP 全连接被拒绝，端口关闭"
    except OSError as e:
        return PortState.ERROR, f"[降级] TCP 全连接错误: {e}"


# ============================================================
# 9. 权限检测
# ============================================================

def _check_admin() -> bool:
    """
    检测当前是否以管理员/Root 权限运行

    Windows: 使用 ctypes.windll.shell32.IsUserAnAdmin
    Linux/macOS: 使用 os.getuid() == 0

    Returns:
        bool: 是否为管理员权限
    """
    try:
        if sys.platform == "win32":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.getuid() == 0
    except Exception:
        return False


# ============================================================
# 10. 对外接口：SynScanner 类
# ============================================================

class SynScanner:
    """
    SYN 半连接扫描器

    封装 SYN 扫描的完整流程，提供与 PortScanner 一致的接口。
    无管理员权限时自动降级为 TCP 全连接扫描。

    使用示例：
        scanner = SynScanner(timeout=1.5)
        state, desc = scanner.scan("192.168.1.1", 80)
        print(f"状态: {state.value}, 说明: {desc}")

    集成方式（PortScanner.scan_single）：
        elif proto == "syn":
            syn_scanner = SynScanner(timeout=self.timeout)
            state, desc = syn_scanner.scan(ip, port)
            return ScanResult(..., state=state, ...)
    """

    def __init__(self, timeout: float = 1.0):
        """
        初始化 SYN 扫描器

        Args:
            timeout: 单次探测超时秒数
        """
        self.timeout = timeout
        self._has_admin = _check_admin()

    def scan(self, ip: str, port: int) -> Tuple[PortState, str]:
        """
        执行 SYN 半连接扫描

        流程：
          1. 检测管理员权限
          2. 有权限：发送 SYN 包 → 解析响应 → 返回状态
          3. 无权限：降级为 TCP 全连接扫描 → 返回状态

        Args:
            ip: 目标 IP 地址
            port: 目标端口号

        Returns:
            (PortState, 状态描述字符串)
        """
        if not self._has_admin:
            # 无管理员权限，直接降级
            return _tcp_connect_fallback(ip, port, self.timeout)

        try:
            response, addr = _send_syn_packet(ip, port, self.timeout)
            if response is None:
                return PortState.FILTERED, "SYN 扫描超时，端口可能被过滤或防火墙拦截"
            return _parse_syn_response(response)
        except PermissionError:
            # 权限不足（理论上 _check_admin 已过滤，防御性编程）
            self._has_admin = False
            return _tcp_connect_fallback(ip, port, self.timeout)
        except OSError as e:
            return PortState.ERROR, f"网络错误: {e}"
        except Exception as e:
            return PortState.ERROR, f"SYN 扫描异常: {e}"


# ============================================================
# 11. 便捷函数
# ============================================================

def scan_syn(ip: str, port: int, timeout: float = 1.0) -> Tuple[PortState, str]:
    """
    SYN 扫描便捷函数（与 scan_tcp / scan_udp 对称）

    Args:
        ip: 目标 IP 地址
        port: 目标端口号
        timeout: 超时秒数

    Returns:
        (PortState, 描述字符串)
    """
    scanner = SynScanner(timeout=timeout)
    return scanner.scan(ip, port)


# ============================================================
# 12. 单元测试入口
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SYN 半连接扫描模块测试")
    print("=" * 70)

    scanner = SynScanner(timeout=1.5)
    print(f"管理员权限: {scanner._has_admin}")
    print()

    # 测试本地回环（127.0.0.1）
    test_ip = "127.0.0.1"
    test_ports = [80, 443, 22, 3306]

    for port in test_ports:
        print(f"扫描 {test_ip}:{port} ...", end=" ")
        state, desc = scanner.scan(test_ip, port)
        status_map = {
            PortState.OPEN: "开放",
            PortState.CLOSED: "关闭",
            PortState.FILTERED: "过滤",
            PortState.ERROR: "错误",
        }
        print(f"[{status_map.get(state, '未知')}] {desc}")
        time.sleep(0.5)  # 避免过快扫描

    print()
    print("=" * 70)
    print("测试完成")
