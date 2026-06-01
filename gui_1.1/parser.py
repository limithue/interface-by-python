"""解析引擎层 — IP/端口字符串解析（高内聚·零外部依赖）"""
import ipaddress
import re
import socket
from typing import FrozenSet, Set, List, Optional

from core.models import ParseResult
from core.exceptions import ParseError
from core.validator import TaskValidator

# 模块级默认配置
_DEFAULT_COMMON_PORTS: FrozenSet[int] = frozenset({
    21, 22, 23, 25, 53, 80, 110, 135, 139, 443,
    445, 3306, 3389, 5432, 6379, 8080
})


class IPParser:
    """IP解析器 — 支持单IP、CIDR、IP段（简写/全写）、域名"""

    _DOMAIN_RE = re.compile(
        r"^(?=.{1,253}$)"
        r"(?!-)[a-zA-Z0-9-]{1,63}(?<!-)"
        r"(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*"
        r"\.[a-zA-Z]{2,}$",
        re.ASCII
    )

    @classmethod
    def resolve(cls, target_str: str) -> FrozenSet[str]:
        if not target_str or not target_str.strip():
            raise ParseError("目标地址不能为空", target_str)

        targets: Set[str] = set()
        for token in (t.strip() for t in target_str.split(",") if t.strip()):
            targets.update(cls._parse_token(token))
        return frozenset(targets)

    @classmethod
    def _parse_token(cls, token: str) -> Set[str]:
        if cls._DOMAIN_RE.match(token):
            return {cls._resolve_domain(token)}
        if "/" in token:
            return cls._parse_cidr(token)
        if "-" in token:
            return set(cls._parse_range(token))
        return {cls._parse_single_ip(token)}

    @staticmethod
    def _resolve_domain(domain: str) -> str:
        try:
            return socket.gethostbyname(domain)
        except socket.gaierror as e:
            raise ParseError(f"域名解析失败: {domain}", domain) from e

    @staticmethod
    def _parse_cidr(cidr: str) -> Set[str]:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            return {str(ip) for ip in net.hosts()}
        except ValueError as e:
            raise ParseError(f"无效CIDR格式: {cidr}", cidr) from e

    @staticmethod
    def _parse_single_ip(ip: str) -> str:
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError as e:
            raise ParseError(f"无效IP格式: {ip}", ip) from e

    @staticmethod
    def _parse_range(token: str) -> List[str]:
        parts = token.split("-")
        if len(parts) != 2:
            raise ParseError(f"IP段格式错误（应为 start-end）: {token}", token)

        start_ip, end_part = parts[0].strip(), parts[1].strip()

        try:
            start = ipaddress.ip_address(start_ip)
        except ValueError:
            raise ParseError(f"IP段起始地址无效: {start_ip}", token)

        if end_part.isdigit():
            octets = list(map(int, start_ip.split(".")))
            end_octet = int(end_part)
            if not (0 <= end_octet <= 255):
                raise ParseError(f"IP段末段越界: {end_octet}", token)
            if end_octet < octets[-1]:
                raise ParseError(
                    f"IP段末段({end_octet})必须>=起始末段({octets[-1]})", token
                )
            return [
                f"{octets[0]}.{octets[1]}.{octets[2]}.{i}"
                for i in range(octets[-1], end_octet + 1)
            ]

        try:
            end = ipaddress.ip_address(end_part)
        except ValueError:
            raise ParseError(f"IP段结束地址无效: {end_part}", token)

        if end < start:
            raise ParseError(f"IP段起止倒置: {start} > {end}", token)

        ips: List[str] = []
        current, end_int = int(start), int(end)
        while current <= end_int:
            ips.append(str(ipaddress.ip_address(current)))
            current += 1
        return ips


class PortParser:
    """端口解析器 — 支持单端口、端口段、common、all及组合

    实例级配置：每个解析器实例可拥有独立的common_ports，
    不修改类属性，避免全局状态污染。
    """

    DEFAULT_COMMON_PORTS: FrozenSet[int] = _DEFAULT_COMMON_PORTS
    ALL_PORTS: FrozenSet[int] = frozenset(range(1, 65536))

    def __init__(self, common_ports: Optional[FrozenSet[int]] = None):
        self._common_ports = common_ports if common_ports is not None else self.DEFAULT_COMMON_PORTS

    def resolve(self, port_str: str) -> FrozenSet[int]:
        if not port_str or not port_str.strip():
            raise ParseError("端口不能为空", port_str)

        port_str = port_str.strip().lower()

        if port_str == "all":
            return self.ALL_PORTS
        if port_str == "common":
            return self._common_ports

        ports: Set[int] = set()
        for token in (t.strip() for t in port_str.split(",") if t.strip()):
            token_lower = token.lower()
            if token_lower == "common":
                ports.update(self._common_ports)
            elif token_lower == "all":
                ports.update(self.ALL_PORTS)
            else:
                ports.update(self._parse_numeric_token(token))

        return frozenset(ports)

    def _parse_numeric_token(self, token: str) -> Set[int]:
        if "-" in token:
            start, end = map(int, token.split("-"))
            if not (1 <= start <= end <= 65535):
                raise ParseError(
                    f"端口范围越界: {token}（有效范围 1-65535）", token
                )
            return set(range(start, end + 1))

        val = int(token)
        if not (1 <= val <= 65535):
            raise ParseError(f"端口越界: {token}（有效范围 1-65535）", token)
        return {val}


class ScanInputFacade:
    """扫描输入门面 — 隐藏IP/Port/Validator协作细节

    低耦合设计：Facade持有独立的PortParser实例，
    配置注入不污染全局类属性。
    """

    def __init__(
        self,
        validator: TaskValidator = None,
        common_ports: Optional[FrozenSet[int]] = None
    ):
        self._validator = validator or TaskValidator()
        self._port_parser = PortParser(common_ports=common_ports)

    def parse(self, target_str: str, port_str: str) -> ParseResult:
        """对外唯一接口：解析 -> 校验 -> 返回不可变契约"""
        targets = IPParser.resolve(target_str)
        ports = self._port_parser.resolve(port_str)
        self._validator.validate(targets, ports)
        return ParseResult(targets=targets, ports=ports)

    def preview(self, target_str: str, port_str: str) -> dict:
        """预览模式：不触发上限异常，用于GUI实时估算"""
        targets = IPParser.resolve(target_str)
        ports = self._port_parser.resolve(port_str)
        stats = self._validator.get_stats(targets, ports)
        return {
            "targets": list(targets)[:5] + (["..."] if len(targets) > 5 else []),
            "ports": list(ports)[:5] + (["..."] if len(ports) > 5 else []),
            **stats
        }
