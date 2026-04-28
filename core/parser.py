"""IP与端口解析模块｜支持单IP、CIDR、IP段、域名、自定义/常用端口"""
import ipaddress
import socket
import re
from typing import Set

class IPParser:
    @staticmethod
    def resolve_targets(target_str: str) -> Set[str]:
        targets = set()
        for t in target_str.split(','):
            t = t.strip()
            if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', t):
                try:
                    targets.add(socket.gethostbyname(t))
                except socket.gaierror as e:
                    raise ValueError(f"域名解析失败: {t} -> {e}")
            elif '/' in t:
                try:
                    net = ipaddress.ip_network(t, strict=False)
                    targets.update(str(ip) for ip in net.hosts())
                except ValueError as e:
                    raise ValueError(f"无效CIDR格式: {t}")
            elif '-' in t and t.count('.') == 6:
                start, end = t.split('-')
                targets.update(IPParser._ip_range(start.strip(), end.strip()))
            else:
                try:
                    ipaddress.ip_address(t)
                    targets.add(t)
                except ValueError:
                    raise ValueError(f"无效IP格式: {t}")
        return targets

    @staticmethod
    def _ip_range(start: str, end: str) -> list:
        s_oct = list(map(int, start.split('.')))
        e_oct = list(map(int, end.split('.')))
        if s_oct[:3] != e_oct[:3]:
            raise ValueError("IP段起止前三段必须一致")
        return [f"{s_oct[0]}.{s_oct[1]}.{s_oct[2]}.{i}" for i in range(s_oct[3], e_oct[3]+1)]

class PortParser:
    @staticmethod
    def resolve_ports(port_str: str) -> Set[int]:
        if port_str.lower() == 'all':
            return set(range(1, 65536))
        if port_str.lower() == 'common':
            from config import COMMON_PORTS
            return COMMON_PORTS.copy()
        
        ports = set()
        for p in port_str.split(','):
            p = p.strip()
            if '-' in p:
                start, end = map(int, p.split('-'))
                if not (1 <= start <= end <= 65535):
                    raise ValueError(f"端口范围越界: {p}")
                ports.update(range(start, end+1))
            else:
                val = int(p)
                if not (1 <= val <= 65535):
                    raise ValueError(f"端口越界: {p}")
                ports.add(val)
        return ports
