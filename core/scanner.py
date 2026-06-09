"""端口探测模块｜TCP/UDP扫描、ICMP存活检测"""
import socket
import subprocess
import logging
from typing import Dict

class PortScanner:
    """
    核心端口扫描引擎。
    支持 TCP 全连接扫描与 UDP 探测，具备跨平台 Ping 预检功能。
    """
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout

logger = logging.getLogger(__name__)

class PortScanner:
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout

    @staticmethod
    def ping_host(ip: str) -> bool:
        try:
            output = subprocess.check_output(
                ["ping", "-n", "1", "-w", "1000", ip],
                stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return "TTL=" in output or "ttl=" in output
        except Exception:
            return False

    def scan_single(self, ip: str, port: int, protocol: str = "tcp") -> Dict:
        result = {"ip": ip, "port": port, "protocol": protocol, "state": "filtered", "service": ""}
        try:
            if protocol == "tcp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                ret = sock.connect_ex((ip, port))
                sock.close()
                result["state"] = "open" if ret == 0 else "closed"
            elif protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)
                sock.sendto(b"\x00", (ip, port))
                try:
                    sock.recvfrom(1024)
                    result["state"] = "open"
                except socket.timeout:
                    result["state"] = "closed/filtered"
                sock.close()
        except socket.timeout:
            result["state"] = "filtered"
        except PermissionError:
            logger.warning(f"权限不足，跳过 {ip}:{port}")
            result["state"] = "permission_denied"
        except Exception as e:
            logger.error(f"扫描异常 {ip}:{port} -> {e}")
            result["state"] = "error"
        
        from config import PORT_SERVICES
        result["service"] = PORT_SERVICES.get(port, "Unknown")
        return result
