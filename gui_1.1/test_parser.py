"""parser模块单元测试 — 覆盖IP/端口/校验/门面全路径

运行方式:
    python -m unittest tests.test_parser -v
    python -m pytest tests/test_parser.py -v

测试统计: 32项断言，覆盖正常路径、边界值、异常路径、配置注入
"""
import unittest
from unittest.mock import patch, MagicMock

# 被测模块
from core.parser import IPParser, PortParser, ScanInputFacade
from core.validator import TaskValidator
from core.exceptions import ParseError, ScannerError
from core.models import ParseResult


class TestIPParser(unittest.TestCase):
    """IP解析测试 — 单IP、CIDR、IP段、域名、组合、异常"""

    def test_single_ip(self):
        result = IPParser.resolve("192.168.1.1")
        self.assertEqual(result, {"192.168.1.1"})

    def test_cidr(self):
        result = IPParser.resolve("192.168.1.0/30")
        self.assertEqual(result, {"192.168.1.1", "192.168.1.2"})

    def test_ip_range_shorthand(self):
        """简写IP段: 192.168.1.1-3"""
        result = IPParser.resolve("192.168.1.1-3")
        self.assertEqual(result, {"192.168.1.1", "192.168.1.2", "192.168.1.3"})

    def test_ip_range_full_cross_subnet(self):
        """全写IP段跨网段: 192.168.1.254-192.168.2.2"""
        result = IPParser.resolve("192.168.1.254-192.168.2.2")
        self.assertEqual(len(result), 5)
        self.assertIn("192.168.2.1", result)

    def test_combined_targets(self):
        """组合目标: 单IP + CIDR"""
        result = IPParser.resolve("192.168.1.1, 10.0.0.0/31")
        self.assertEqual(len(result), 3)

    def test_domain_resolution(self):
        """域名解析 — 网络环境可能失败，允许ParseError"""
        try:
            result = IPParser.resolve("localhost")
            self.assertGreaterEqual(len(result), 1)
        except ParseError:
            self.skipTest("网络环境无法解析域名，跳过")

    def test_empty_string_raises(self):
        with self.assertRaises(ParseError) as ctx:
            IPParser.resolve("")
        self.assertIn("不能为空", str(ctx.exception))

    def test_whitespace_only_raises(self):
        with self.assertRaises(ParseError):
            IPParser.resolve("   ")

    def test_invalid_ip_raises(self):
        with self.assertRaises(ParseError) as ctx:
            IPParser.resolve("999.999.999.999")
        self.assertIn("无效IP", str(ctx.exception))

    def test_invalid_cidr_raises(self):
        with self.assertRaises(ParseError) as ctx:
            IPParser.resolve("192.168.1.0/33")
        self.assertIn("无效CIDR", str(ctx.exception))

    def test_ip_range_inverted_raises(self):
        with self.assertRaises(ParseError) as ctx:
            IPParser.resolve("192.168.1.100-1")
        self.assertIn("末段", str(ctx.exception))

    def test_ip_range_octet_overflow_raises(self):
        with self.assertRaises(ParseError):
            IPParser.resolve("192.168.1.1-300")

    def test_result_is_frozenset(self):
        """返回类型必须为不可变集合"""
        result = IPParser.resolve("127.0.0.1")
        self.assertIsInstance(result, frozenset)


class TestPortParser(unittest.TestCase):
    """端口解析测试 — common、all、单端口、段、组合、越界"""

    def test_common_ports(self):
        parser = PortParser()
        result = parser.resolve("common")
        self.assertEqual(len(result), 16)
        self.assertIn(80, result)
        self.assertIn(443, result)

    def test_all_ports(self):
        parser = PortParser()
        result = parser.resolve("all")
        self.assertEqual(len(result), 65535)

    def test_single_port(self):
        parser = PortParser()
        self.assertEqual(parser.resolve("80"), {80})

    def test_port_range(self):
        parser = PortParser()
        self.assertEqual(parser.resolve("80-82"), {80, 81, 82})

    def test_combined_common_and_custom(self):
        parser = PortParser()
        result = parser.resolve("common, 9000")
        self.assertIn(9000, result)
        self.assertIn(80, result)
        self.assertEqual(len(result), 17)

    def test_combined_all_dedup(self):
        """all已包含9000，不应重复"""
        parser = PortParser()
        result = parser.resolve("all, 9000")
        self.assertEqual(len(result), 65535)

    def test_case_insensitive(self):
        parser = PortParser()
        self.assertEqual(parser.resolve("COMMON"), parser.resolve("common"))

    def test_port_zero_raises(self):
        with self.assertRaises(ParseError):
            PortParser().resolve("0")

    def test_port_65536_raises(self):
        with self.assertRaises(ParseError):
            PortParser().resolve("65536")

    def test_port_range_overflow_raises(self):
        with self.assertRaises(ParseError):
            PortParser().resolve("65530-65536")

    def test_empty_string_raises(self):
        with self.assertRaises(ParseError):
            PortParser().resolve("")

    def test_result_is_frozenset(self):
        result = PortParser().resolve("80")
        self.assertIsInstance(result, frozenset)

    def test_instance_isolation(self):
        """实例隔离：自定义端口不污染默认实例"""
        custom = frozenset({22, 80, 443})
        parser_custom = PortParser(common_ports=custom)
        parser_default = PortParser()

        self.assertEqual(parser_custom.resolve("common"), custom)
        self.assertEqual(len(parser_default.resolve("common")), 16)


class TestTaskValidator(unittest.TestCase):
    """任务量校验测试 — 上限拦截、边界值、统计信息"""

    def test_normal_volume_passes(self):
        validator = TaskValidator(max_tasks=100)
        targets = frozenset({"192.168.1.1", "192.168.1.2"})
        ports = frozenset({80, 443})
        validator.validate(targets, ports)  # 2*2=4 <= 100, 不应抛异常

    def test_exact_boundary_passes(self):
        validator = TaskValidator(max_tasks=100000)
        targets = frozenset(f"192.168.1.{i}" for i in range(1, 101))
        ports = frozenset(range(1, 1001))
        validator.validate(targets, ports)  # 100*1000=100000

    def test_over_boundary_raises(self):
        validator = TaskValidator(max_tasks=100)
        targets = frozenset({"192.168.1.1"})
        ports = frozenset(range(1, 102))
        with self.assertRaises(ParseError) as ctx:
            validator.validate(targets, ports)
        self.assertIn("过大", str(ctx.exception))
        self.assertIn("101", str(ctx.exception))  # 1*101=101

    def test_get_stats_no_exception(self):
        validator = TaskValidator(max_tasks=10)
        targets = frozenset({"a", "b"})
        ports = frozenset({1, 2, 3, 4, 5, 6})
        stats = validator.get_stats(targets, ports)
        self.assertEqual(stats["total_tasks"], 12)
        self.assertEqual(stats["is_safe"], False)

    def test_default_max_tasks(self):
        validator = TaskValidator()
        self.assertEqual(validator.max_tasks, 100000)


class TestScanInputFacade(unittest.TestCase):
    """门面集成测试 — 端到端解析、校验、配置注入、Preview"""

    def test_end_to_end_parse(self):
        facade = ScanInputFacade()
        result = facade.parse("192.168.1.1-3", "80,443")
        self.assertIsInstance(result, ParseResult)
        self.assertEqual(result.target_count, 3)
        self.assertEqual(result.port_count, 2)
        self.assertEqual(result.total_tasks, 6)

    def test_task_volume_rejection(self):
        """核心需求：1.0.0.0/8 + 1-65535 必须拒绝启动"""
        facade = ScanInputFacade()
        with self.assertRaises(ParseError) as ctx:
            facade.parse("1.0.0.0/8", "1-65535")
        self.assertIn("过大", str(ctx.exception))

    def test_custom_common_ports_injection(self):
        custom = frozenset({22, 80, 443})
        facade = ScanInputFacade(common_ports=custom)
        result = facade.parse("127.0.0.1", "common")
        self.assertEqual(result.ports, custom)

    def test_injection_isolation(self):
        """注入不污染后续Facade实例"""
        custom = frozenset({22, 80, 443})
        facade1 = ScanInputFacade(common_ports=custom)
        facade2 = ScanInputFacade()

        r1 = facade1.parse("127.0.0.1", "common")
        r2 = facade2.parse("127.0.0.1", "common")

        self.assertEqual(len(r1.ports), 3)
        self.assertEqual(len(r2.ports), 16)

    def test_custom_validator_injection(self):
        validator = TaskValidator(max_tasks=10)
        facade = ScanInputFacade(validator=validator)
        with self.assertRaises(ParseError):
            facade.parse("192.168.1.1-2", "1-10")  # 2*10=20 > 10

    def test_preview_mode_no_exception(self):
        facade = ScanInputFacade()
        preview = facade.preview("192.168.1.1-3", "common")
        self.assertIsInstance(preview, dict)
        self.assertEqual(preview["total_tasks"], 48)
        self.assertEqual(preview["is_safe"], True)
        self.assertIn("targets", preview)
        self.assertIn("ports", preview)

    def test_preview_over_limit_no_exception(self):
        """Preview超限不应抛异常，仅标记is_safe=False"""
        facade = ScanInputFacade()
        preview = facade.preview("1.0.0.0/8", "1-65535")
        self.assertEqual(preview["is_safe"], False)
        self.assertGreater(preview["total_tasks"], 100000)

    def test_exception_is_scanner_error_subclass(self):
        """ParseError必须继承ScannerError，保证GUI层统一捕获"""
        facade = ScanInputFacade()
        with self.assertRaises(ScannerError):
            facade.parse("", "80")

    def test_result_immutable(self):
        """ParseResult不可变，防止多线程修改"""
        facade = ScanInputFacade()
        result = facade.parse("127.0.0.1", "80")
        with self.assertRaises(AttributeError):
            result.targets = {"10.0.0.1"}


if __name__ == "__main__":
    unittest.main(verbosity=2)
