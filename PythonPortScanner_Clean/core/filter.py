#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/filter.py —— 扫描目标黑白名单过滤模块
===============================================

职责：
  • 在解析后、扫描前对目标 IP 和端口进行过滤
  • 支持黑名单（默认禁止）和白名单（明确许可）两种模式
  • 白名单优先策略：命中白名单即放行，即使同时命中黑名单
  • 内置系统保留地址/端口兜底 + 外部 JSON 配置自定义规则
  • 防止误扫敏感地址（广播、组播、系统保留端口等）

设计原则：
  • 高内聚：所有过滤逻辑集中在此模块，不泄露到 GUI/扫描器
  • 低耦合：接收不可变集合，返回不可变结果，零外部依赖
  • 可配置：实例级注入规则，不修改全局类属性
  • 可反馈：返回详细过滤日志，供 GUI 展示给用户

合规声明：
  黑名单过滤旨在防止误操作扫描系统保留地址，不构成对扫描行为的限制或鼓励。
"""

import json
import ipaddress
import os
from typing import Set, FrozenSet, Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field


# ============================================================
# 1. 内置默认黑名单（系统保留地址与端口，不可删除）
# ============================================================

# 系统保留 IP 地址（RFC 3330 / RFC 5735）
_DEFAULT_IP_BLACKLIST: FrozenSet[str] = frozenset({
    # 广播地址
    "255.255.255.255",
    # 组播地址段（224.0.0.0/4）
    "224.0.0.0", "224.0.0.1", "224.0.0.2", "239.255.255.255",
    # 链路本地广播
    "169.254.255.255",
    # 有限广播（部分系统）
    "0.0.0.0",
})

# 系统保留端口（IANA 特殊用途端口）
_DEFAULT_PORT_BLACKLIST: FrozenSet[int] = frozenset({
    0,      # 保留
    7,      # Echo（反射攻击风险）
    9,      # Discard
    13,     # Daytime
    17,     # Quote of the Day
    19,     # Chargen（放大攻击风险）
    37,     # Time
    111,    # RPCbind（历史漏洞）
    512,    # exec（rlogin 系列，高风险）
    513,    # login
    514,    # shell / syslog
    515,    # printer
    540,    # uucp
    1080,   # SOCKS（代理滥用风险，可选）
})


# ============================================================
# 2. 过滤日志记录
# ============================================================

@dataclass(frozen=True)
class FilterLog:
    """单条过滤记录（不可变）"""
    item: str           # 被过滤的 IP 或端口字符串
    item_type: str      # "ip" 或 "port"
    reason: str         # 过滤原因
    rule_source: str    # 规则来源: "builtin"(内置) / "config"(配置) / "whitelist"(白名单覆盖)


@dataclass(frozen=True)
class FilterResult:
    """
    过滤结果不可变数据契约

    下游扫描器仅使用 allowed_targets 和 allowed_ports，
    blocked_logs 供 GUI 展示过滤详情。
    """
    allowed_targets: FrozenSet[str]
    allowed_ports: FrozenSet[int]
    blocked_logs: Tuple[FilterLog, ...]
    total_input_targets: int
    total_input_ports: int

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_logs)

    @property
    def allowed_target_count(self) -> int:
        return len(self.allowed_targets)

    @property
    def allowed_port_count(self) -> int:
        return len(self.allowed_ports)

    def summary(self) -> str:
        """生成过滤摘要，供 GUI 日志展示"""
        lines = [
            f"[FILTER] 输入目标: {self.total_input_targets} 个 → 允许: {self.allowed_target_count} 个",
            f"[FILTER] 输入端口: {self.total_input_ports} 个 → 允许: {self.allowed_port_count} 个",
        ]
        if self.blocked_logs:
            lines.append(f"[FILTER] 已过滤 {self.blocked_count} 项:")
            # 按类型分组展示
            ip_logs = [l for l in self.blocked_logs if l.item_type == "ip"]
            port_logs = [l for l in self.blocked_logs if l.item_type == "port"]
            if ip_logs:
                lines.append(f"  IP 过滤 ({len(ip_logs)} 个):")
                for log in ip_logs[:5]:
                    lines.append(f"    - {log.item}: {log.reason}")
                if len(ip_logs) > 5:
                    lines.append(f"    ... 等共 {len(ip_logs)} 个")
            if port_logs:
                lines.append(f"  端口过滤 ({len(port_logs)} 个):")
                for log in port_logs[:5]:
                    lines.append(f"    - {log.item}: {log.reason}")
                if len(port_logs) > 5:
                    lines.append(f"    ... 等共 {len(port_logs)} 个")
        return "\n".join(lines)


# ============================================================
# 3. 规则加载器（外部 JSON 配置）
# ============================================================

class RuleLoader:
    """
    规则加载器

    职责：从外部 JSON 文件加载用户自定义黑白名单规则。
    与 ScanFilter 解耦，可独立测试。
    """

    DEFAULT_CONFIG_PATH = "scan_rules.json"

    @classmethod
    def load(cls, filepath: Optional[str] = None) -> Dict[str, Any]:
        """
        从 JSON 文件加载规则

        Returns:
            {
                "ip_blacklist": ["192.168.1.1", "10.0.0.0/8"],
                "port_blacklist": [3389, 445],
                "ip_whitelist": ["192.168.1.10"],
                "port_whitelist": [80, 443],
            }
        """
        path = filepath or cls.DEFAULT_CONFIG_PATH
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "ip_blacklist": set(data.get("ip_blacklist", [])),
                "port_blacklist": set(data.get("port_blacklist", [])),
                "ip_whitelist": set(data.get("ip_whitelist", [])),
                "port_whitelist": set(data.get("port_whitelist", [])),
            }
        except (json.JSONDecodeError, OSError):
            return {}

    @classmethod
    def save(
        cls,
        ip_blacklist: Optional[Set[str]] = None,
        port_blacklist: Optional[Set[int]] = None,
        ip_whitelist: Optional[Set[str]] = None,
        port_whitelist: Optional[Set[int]] = None,
        filepath: Optional[str] = None,
    ) -> None:
        """保存规则到 JSON 文件"""
        path = filepath or cls.DEFAULT_CONFIG_PATH
        data = {
            "ip_blacklist": sorted(ip_blacklist or set()),
            "port_blacklist": sorted(port_blacklist or set()),
            "ip_whitelist": sorted(ip_whitelist or set()),
            "port_whitelist": sorted(port_whitelist or set()),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 无写权限时静默失败


# ============================================================
# 4. 扫描过滤器（核心类）
# ============================================================

class ScanFilter:
    """
    扫描目标过滤器

    策略规则（优先级从高到低）：
      1. 白名单命中 → 直接放行（即使同时命中黑名单）
      2. 内置黑名单命中 → 拒绝（系统保留地址/端口，不可覆盖）
      3. 自定义黑名单命中 → 拒绝
      4. 以上均未命中 → 放行

    使用示例：
        # 基础用法（仅内置规则）
        filter = ScanFilter()
        result = filter.apply(targets, ports)
        print(result.summary())
        # 使用 result.allowed_targets / result.allowed_ports 进行扫描

        # 加载外部配置
        filter = ScanFilter.load_from_config("my_rules.json")
        result = filter.apply(targets, ports)

        # 动态增删（GUI 实时生效）
        filter.add_ip_blacklist("192.168.1.1")
        filter.add_port_whitelist(8080)
        filter.save_config()  # 持久化到 JSON
    """

    def __init__(
        self,
        ip_blacklist: Optional[Set[str]] = None,
        port_blacklist: Optional[Set[int]] = None,
        ip_whitelist: Optional[Set[str]] = None,
        port_whitelist: Optional[Set[int]] = None,
        use_builtin_defaults: bool = True,
    ):
        """
        初始化过滤器

        Args:
            ip_blacklist: 用户自定义 IP 黑名单
            port_blacklist: 用户自定义端口黑名单
            ip_whitelist: 用户自定义 IP 白名单
            port_whitelist: 用户自定义端口白名单
            use_builtin_defaults: 是否启用内置默认黑名单（系统保留地址/端口）
        """
        self._builtin_ip_blacklist = _DEFAULT_IP_BLACKLIST if use_builtin_defaults else frozenset()
        self._builtin_port_blacklist = _DEFAULT_PORT_BLACKLIST if use_builtin_defaults else frozenset()

        self._custom_ip_blacklist: Set[str] = set(ip_blacklist or set())
        self._custom_port_blacklist: Set[int] = set(port_blacklist or set())
        self._custom_ip_whitelist: Set[str] = set(ip_whitelist or set())
        self._custom_port_whitelist: Set[int] = set(port_whitelist or set())

        self._use_builtin = use_builtin_defaults

    # -------------------- 类方法：从配置加载 --------------------

    @classmethod
    def load_from_config(cls, filepath: Optional[str] = None) -> "ScanFilter":
        """从 JSON 配置文件加载规则并创建过滤器实例"""
        rules = RuleLoader.load(filepath)
        return cls(
            ip_blacklist=rules.get("ip_blacklist"),
            port_blacklist=rules.get("port_blacklist"),
            ip_whitelist=rules.get("ip_whitelist"),
            port_whitelist=rules.get("port_whitelist"),
        )

    # -------------------- 动态增删接口（GUI 调用） --------------------

    def add_ip_blacklist(self, ip: str) -> None:
        """动态添加 IP 黑名单"""
        self._custom_ip_blacklist.add(ip)

    def remove_ip_blacklist(self, ip: str) -> None:
        """移除 IP 黑名单"""
        self._custom_ip_blacklist.discard(ip)

    def add_port_blacklist(self, port: int) -> None:
        """动态添加端口黑名单"""
        self._custom_port_blacklist.add(port)

    def remove_port_blacklist(self, port: int) -> None:
        """移除端口黑名单"""
        self._custom_port_blacklist.discard(port)

    def add_ip_whitelist(self, ip: str) -> None:
        """动态添加 IP 白名单"""
        self._custom_ip_whitelist.add(ip)

    def remove_ip_whitelist(self, ip: str) -> None:
        """移除 IP 白名单"""
        self._custom_ip_whitelist.discard(ip)

    def add_port_whitelist(self, port: int) -> None:
        """动态添加端口白名单"""
        self._custom_port_whitelist.add(port)

    def remove_port_whitelist(self, port: int) -> None:
        """移除端口白名单"""
        self._custom_port_whitelist.discard(port)

    def clear_custom_rules(self) -> None:
        """清空所有自定义规则（保留内置默认）"""
        self._custom_ip_blacklist.clear()
        self._custom_port_blacklist.clear()
        self._custom_ip_whitelist.clear()
        self._custom_port_whitelist.clear()

    # -------------------- 规则查询接口 --------------------

    @property
    def all_ip_blacklist(self) -> FrozenSet[str]:
        """获取完整 IP 黑名单（内置 + 自定义）"""
        return self._builtin_ip_blacklist | frozenset(self._custom_ip_blacklist)

    @property
    def all_port_blacklist(self) -> FrozenSet[int]:
        """获取完整端口黑名单（内置 + 自定义）"""
        return self._builtin_port_blacklist | frozenset(self._custom_port_blacklist)

    @property
    def ip_whitelist(self) -> FrozenSet[str]:
        """获取 IP 白名单"""
        return frozenset(self._custom_ip_whitelist)

    @property
    def port_whitelist(self) -> FrozenSet[int]:
        """获取端口白名单"""
        return frozenset(self._custom_port_whitelist)

    # -------------------- 持久化 --------------------

    def save_config(self, filepath: Optional[str] = None) -> None:
        """将当前自定义规则保存到 JSON 文件"""
        RuleLoader.save(
            ip_blacklist=self._custom_ip_blacklist,
            port_blacklist=self._custom_port_blacklist,
            ip_whitelist=self._custom_ip_whitelist,
            port_whitelist=self._custom_port_whitelist,
            filepath=filepath,
        )

    # -------------------- 核心过滤逻辑 --------------------

    def _is_ip_blocked(self, ip: str) -> Tuple[bool, str, str]:
        """
        判断单个 IP 是否被过滤

        Returns:
            (是否被阻, 原因, 规则来源)
        """
        # 1. 白名单优先（最高优先级）
        if ip in self._custom_ip_whitelist:
            return False, "命中白名单，放行", "whitelist"

        # 2. 内置黑名单检查
        if ip in self._builtin_ip_blacklist:
            return True, "系统保留地址，禁止扫描", "builtin"

        # 3. 检查是否为组播/广播/保留地址（CIDR 匹配）
        try:
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_multicast:
                return True, "组播地址禁止扫描", "builtin"
            if ip_obj.is_reserved:
                return True, "保留地址禁止扫描", "builtin"
            if ip_obj == ipaddress.ip_address("255.255.255.255"):
                return True, "广播地址禁止扫描", "builtin"
            if ip_obj.is_loopback and self._use_builtin:
                # 回环地址可选拦截，当前不强制
                pass
        except ValueError:
            pass  # 域名等无法解析为 IP 的，跳过此项检查

        # 4. 自定义黑名单检查
        if ip in self._custom_ip_blacklist:
            return True, "用户自定义黑名单", "config"

        # 5. 放行
        return False, "", ""

    def _is_port_blocked(self, port: int) -> Tuple[bool, str, str]:
        """
        判断单个端口是否被过滤

        Returns:
            (是否被阻, 原因, 规则来源)
        """
        # 1. 白名单优先
        if port in self._custom_port_whitelist:
            return False, "命中白名单，放行", "whitelist"

        # 2. 内置黑名单
        if port in self._builtin_port_blacklist:
            return True, "系统保留端口，禁止扫描", "builtin"

        # 3. 自定义黑名单
        if port in self._custom_port_blacklist:
            return True, "用户自定义黑名单", "config"

        # 4. 放行
        return False, "", ""

    def apply(
        self,
        targets: FrozenSet[str],
        ports: FrozenSet[int],
    ) -> FilterResult:
        """
        执行过滤

        Args:
            targets: 解析后的目标 IP/域名集合（不可变）
            ports: 解析后的端口集合（不可变）

        Returns:
            FilterResult 过滤结果（不可变）
        """
        logs: List[FilterLog] = []
        allowed_targets: Set[str] = set()
        allowed_ports: Set[int] = set()

        # 过滤目标
        for target in targets:
            is_blocked, reason, source = self._is_ip_blocked(target)
            if is_blocked:
                logs.append(FilterLog(
                    item=target,
                    item_type="ip",
                    reason=reason,
                    rule_source=source,
                ))
            else:
                allowed_targets.add(target)

        # 过滤端口
        for port in ports:
            is_blocked, reason, source = self._is_port_blocked(port)
            if is_blocked:
                logs.append(FilterLog(
                    item=str(port),
                    item_type="port",
                    reason=reason,
                    rule_source=source,
                ))
            else:
                allowed_ports.add(port)

        return FilterResult(
            allowed_targets=frozenset(allowed_targets),
            allowed_ports=frozenset(allowed_ports),
            blocked_logs=tuple(logs),
            total_input_targets=len(targets),
            total_input_ports=len(ports),
        )


# ============================================================
# 5. 便捷函数
# ============================================================

def apply_filter(
    targets: FrozenSet[str],
    ports: FrozenSet[int],
    config_path: Optional[str] = None,
) -> FilterResult:
    """
    便捷过滤函数

    从配置文件加载规则并执行过滤，适合 CLI/GUI 一键调用。

    Args:
        targets: 目标 IP 集合
        ports: 端口集合
        config_path: 规则配置文件路径，None 则使用默认路径

    Returns:
        FilterResult
    """
    filter_obj = ScanFilter.load_from_config(config_path)
    return filter_obj.apply(targets, ports)


# ============================================================
# 6. 单元测试入口
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("扫描过滤器单元测试")
    print("=" * 70)

    # 测试 1：内置黑名单
    print("\n[测试 1] 内置黑名单过滤")
    targets = frozenset({
        "192.168.1.1",      # 普通地址 → 放行
        "224.0.0.1",        # 组播地址 → 内置黑名单
        "255.255.255.255",  # 广播地址 → 内置黑名单
        "10.0.0.1",         # 普通地址 → 放行
    })
    ports = frozenset({80, 443, 7, 111, 3306})
    result = ScanFilter().apply(targets, ports)
    print(result.summary())
    assert result.allowed_target_count == 2
    assert result.allowed_port_count == 3  # 80, 443, 3306
    print("✓ 通过")

    # 测试 2：自定义黑名单
    print("\n[测试 2] 自定义黑名单")
    result2 = ScanFilter(
        ip_blacklist={"192.168.1.1"},
        port_blacklist={3306},
        use_builtin_defaults=False,
    ).apply(targets, ports)
    print(result2.summary())
    assert "192.168.1.1" not in result2.allowed_targets
    assert 3306 not in result2.allowed_ports
    print("✓ 通过")

    # 测试 3：白名单优先（核心策略）
    print("\n[测试 3] 白名单优先策略（同时命中黑白名单）")
    result3 = ScanFilter(
        ip_blacklist={"192.168.1.1"},
        ip_whitelist={"192.168.1.1"},  # 白名单应覆盖黑名单
        use_builtin_defaults=False,
    ).apply(frozenset({"192.168.1.1"}), frozenset({80}))
    print(result3.summary())
    assert "192.168.1.1" in result3.allowed_targets  # 白名单优先，应放行
    assert result3.blocked_count == 0
    print("✓ 通过")

    # 测试 4：配置文件加载
    print("\n[测试 4] 配置文件加载与保存")
    test_filter = ScanFilter(
        ip_blacklist={"10.0.0.99"},
        port_whitelist={22, 80},
    )
    test_filter.save_config("_test_rules.json")
    loaded = ScanFilter.load_from_config("_test_rules.json")
    result4 = loaded.apply(
        frozenset({"10.0.0.99", "192.168.1.1"}),
        frozenset({22, 443, 7}),
    )
    print(result4.summary())
    assert "10.0.0.99" not in result4.allowed_targets
    assert 22 in result4.allowed_ports      # 白名单放行
    assert 443 in result4.allowed_ports      # 未命中黑白名单 → 放行
    assert 7 not in result4.allowed_ports    # 内置黑名单
    print("✓ 通过")

    # 清理测试文件
    if os.path.exists("_test_rules.json"):
        os.remove("_test_rules.json")

    print("\n" + "=" * 70)
    print("全部测试通过！")
