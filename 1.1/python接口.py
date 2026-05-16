# ============================================================
# python接口.py - 扫描核心引擎（线程池版）
# 职责：TCP/UDP探测、存活检测、线程池调度、结果聚合
# ============================================================

import socket
import threading
import time
import random
import struct
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    DEFAULT_TIMEOUT, DEFAULT_THREADS, MAX_THREADS,
    COMMON_PORTS, TCP_ALIVE_PORTS, COLORS
)


def colored(text, color="WHITE"):
    """跨平台彩色文本封装（Windows 自动启用 VT100 支持）"""
    if os.name == 'nt':
        os.system('')  # 激活 Windows 10+ VT100 序列
    code = COLORS.get(color.upper(), COLORS["WHITE"])
    reset = COLORS["RESET"]
    return f"{code}{text}{reset}"


# ==================== 校验和计算 ====================
def _checksum(source_string):
    """计算 ICMP 报文校验和（RFC 1071）"""
    s = 0
    count_to = (len(source_string) // 2) * 2
    for count in range(0, count_to, 2):
        this_val = source_string[count + 1] * 256 + source_string[count]
        s = s + this_val
        s = s & 0xffffffff
    if count_to < len(source_string):
        s = s + source_string[len(source_string) - 1]
        s = s & 0xffffffff
    s = (s >> 16) + (s & 0xffff)
    s = s + (s >> 16)
    answer = ~s
    answer = answer & 0xffff
    answer = answer >> 8 | (answer << 8 & 0xff00)
    return answer


# ==================== TCP 探测层 ====================
def scan_tcp_once(ip, port, timeout=DEFAULT_TIMEOUT):
    """单次 TCP 全连接探测；返回 True/False"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((ip, port))
        return result == 0
    except (socket.timeout, OSError, ConnectionRefusedError):
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def scan_tcp(ip, port, timeout=DEFAULT_TIMEOUT, verify=True):
    """
    TCP 端口扫描（含二次验证）
    机制：首次探测开放后，随机延迟 0.1~0.3s 再次验证，
          两次均通过才确认 OPEN，显著降低瞬态误报。
    """
    first = scan_tcp_once(ip, port, timeout)
    if not first:
        return False
    if verify:
        time.sleep(random.uniform(0.1, 0.3))
        second = scan_tcp_once(ip, port, timeout)
        return second
    return first


# ==================== UDP 探测层 ====================
def scan_udp(ip, port, timeout=DEFAULT_TIMEOUT):
    """
    UDP 端口扫描（保守策略，降低误报）
    机制：发送 8 字节探测载荷，仅当明确收到 UDP 响应数据时判定 OPEN；
          超时或异常均视为不确定，保守返回 False。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"\x00" * 8, (ip, port))
        try:
            sock.recvfrom(1024)
            sock.close()
            return True  # 明确收到响应，确认开放
        except socket.timeout:
            sock.close()
            return False  # 保守策略：超时视为不确定，不报告开放
    except (OSError, PermissionError):
        return False


# ==================== 存活检测层 ====================
def is_alive_icmp(ip, timeout=1.5):
    """
    ICMP Echo Request 存活探测
    返回:
        True  -> 收到 Echo Reply，确认存活
        False -> 超时，可能不存活
        None  -> 权限不足（Windows 非管理员），需降级
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(timeout)

        # 构造 ICMP Echo Request (Type=8, Code=0)
        pid = os.getpid() & 0xFFFF
        header = struct.pack('!BBHHH', 8, 0, 0, pid, 1)
        data = b'alive'
        cs = _checksum(header + data)
        header = struct.pack('!BBHHH', 8, 0, cs, pid, 1)
        packet = header + data

        sock.sendto(packet, (ip, 0))
        try:
            sock.recvfrom(1024)
            sock.close()
            return True
        except socket.timeout:
            sock.close()
            return False
    except PermissionError:
        return None  # 权限不足，触发降级
    except OSError:
        return None  # 系统不支持 RAW Socket


def is_alive_tcp(ip, timeout=DEFAULT_TIMEOUT):
    """
    TCP 降级存活探测（普通权限方案）
    机制：轮询探测 TCP_ALIVE_PORTS 列表，任一端口开放即判定存活；
          即使全部失败，也返回 True（绝不误判跳过 IP）。
    """
    for port in TCP_ALIVE_PORTS:
        if scan_tcp_once(ip, port, timeout):
            return True
        time.sleep(random.uniform(0.02, 0.05))
    return True  # 绝不误判跳过


def is_alive(ip):
    """
    统一存活检测入口
    策略：先尝试 ICMP；权限不足或探测失败时，无缝降级 TCP 探测。
    """
    result = is_alive_icmp(ip)
    if result is True:
        return True
    # ICMP 权限不足(result=None) 或 超时(result=False)，均降级 TCP
    return is_alive_tcp(ip)


# ==================== 线程池扫描器 ====================
class PortScanner:
    """
    基于 ThreadPoolExecutor 的多线程端口扫描器
    优势：
      - 彻底抛弃"每端口一线程"模型，内存占用下降 90%+
      - 线程数严格限制在 1~MAX_THREADS，扫 1-65535 不崩溃
      - 内置 stop_event，支持 Ctrl+C 安全中断
    """

    def __init__(self, threads=10):
        self.threads = max(1, min(threads, MAX_THREADS))
        self.open_ports = []          # 开放端口结果列表
        self.lock = threading.Lock()  # 结果写入锁
        self.stop_event = threading.Event()
        self.scanned_count = 0
        self.total_count = 0

    def _worker(self, ip, port, scan_func):
        """单个扫描任务单元"""
        if self.stop_event.is_set():
            return None
        try:
            is_open = scan_func(ip, port)
            if is_open:
                with self.lock:
                    self.open_ports.append((ip, port, "OPEN"))
            # 加长随机延迟 0.05~0.25s，降低扫描特征，提升隐蔽性
            time.sleep(random.uniform(0.05, 0.25))
        except Exception:
            # 忽略单个任务异常，防止单点故障中断全局扫描
            pass

        with self.lock:
            self.scanned_count += 1
        return None

    def start_scan(self, ip_list, port_list, protocol="tcp", progress_callback=None):
        """
        启动线程池扫描
        :param ip_list: 目标 IP 字符串列表
        :param port_list: 目标端口整数列表
        :param protocol: "tcp" 或 "udp"
        :param progress_callback: 进度回调函数(current, total)
        :return: [(ip, port, "OPEN"), ...]
        """
        scan_func = scan_tcp if protocol == "tcp" else scan_udp
        self.total_count = len(ip_list) * len(port_list)
        self.scanned_count = 0

        # 预检存活（仅记录状态，绝不跳过任何 IP）
        alive_map = {}
        for ip in ip_list:
            alive_map[ip] = is_alive(ip)

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for ip in ip_list:
                for port in port_list:
                    if self.stop_event.is_set():
                        break
                    future = executor.submit(self._worker, ip, port, scan_func)
                    futures[future] = (ip, port)

            # 等待任务完成，同时支持 KeyboardInterrupt 中断
            completed = 0
            try:
                for future in as_completed(futures):
                    if self.stop_event.is_set():
                        for f in futures:
                            f.cancel()
                        break
                    completed += 1
                    if progress_callback and self.total_count > 0:
                        progress_callback(completed, self.total_count)
            except KeyboardInterrupt:
                self.stop_event.set()
                for f in futures:
                    f.cancel()
                raise  # 向上抛出，由 main.py 统一处理

        # 去重并排序（防止多线程重复写入同一端口）
        with self.lock:
            unique = sorted(
                list(set(self.open_ports)),
                key=lambda x: (x[0], x[1])
            )
            self.open_ports = unique

        return self.open_ports