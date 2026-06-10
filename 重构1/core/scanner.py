"""
core/scanner.py
核心网络探测模块 (ICMP/TCP降级、端口扫描、二次验证)
"""
import socket
import struct
import time
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from utils.logger import ScanLogger

logger = ScanLogger.get_logger("scanner")

@dataclass
class ScanConfig:
    icmp_timeout: float = 1.0
    tcp_timeout: float = 1.0
    fallback_ports: List[int] = field(default_factory=lambda: [80, 443, 22, 3389, 445])
    verify_delay_min: float = 0.1
    verify_delay_max: float = 0.3

class HostScanner:
    def __init__(self, config: Optional[ScanConfig] = None):
        self.config = config or ScanConfig()

    def is_alive(self, ip: str) -> bool:
        icmp_result = self._icmp_probe(ip)
        if icmp_result is True: return True
        if icmp_result is None: return self._tcp_fallback_probe(ip)
        return False

    def _icmp_probe(self, ip: str) -> Optional[bool]:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.settimeout(self.config.icmp_timeout)
            header = struct.pack('bbHHh', 8, 0, 0, 1, 1)
            sock.sendto(header + b'ping', (ip, 0))
            sock.recvfrom(1024)
            return True
        except (PermissionError, OSError) as e:
            err_str = str(e).lower()
            if "10013" in err_str or "permission" in err_str or "access" in err_str:
                return None
            return False
        except socket.timeout:
            return False
        finally:
            if sock: sock.close()

    def _tcp_fallback_probe(self, ip: str) -> bool:
        for port in self.config.fallback_ports:
            try:
                # 【S-2 修复】使用 with 语句防止 Socket 泄漏
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(self.config.tcp_timeout)
                    if sock.connect_ex((ip, port)) in (0, 10061, 111):
                        return True
            except (socket.timeout, OSError):
                continue
        return False

class PortScanner:
    def __init__(self, config: Optional[ScanConfig] = None):
        self.config = config or ScanConfig()

    def scan_port(self, ip: str, port: int) -> Dict[str, Any]:
        state = "closed"
        # 【S-2 修复】使用 with 语句确保 Socket 必定关闭
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.config.tcp_timeout)
                if sock.connect_ex((ip, port)) == 0:
                    state = "open"
        except Exception:
            state = "filtered"
            
        # 【S-3 修复】二次验证机制：过滤瞬态误报
        if state == "open":
            delay = random.uniform(self.config.verify_delay_min, self.config.verify_delay_max)
            time.sleep(delay)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(self.config.tcp_timeout)
                    if sock.connect_ex((ip, port)) != 0:
                        state = "filtered" 
            except Exception:
                state = "filtered"
                
        return {"ip": ip, "port": port, "state": state}
