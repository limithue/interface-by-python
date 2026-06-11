#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/syn_scanner_patch.py —— SYN 半连接扫描集成补丁说明
============================================================

本文件说明如何将 syn_scanner.py 集成到现有的 scanner.py 和 main_window.py 中，
使 PortScanner 类支持 protocol="syn" 分支。按以下步骤修改即可，无需重构现有代码结构。

【修改位置 1】scanner.py 顶部导入区
--------------------------------
在原有导入后添加：

    from core.syn_scanner import SynScanner

【修改位置 2】scanner.py 的 PortScanner.scan_single() 方法
--------------------------------------------------------
在 protocol == "tcp" 和 protocol == "udp" 分支后，添加 syn 分支：

        elif proto == "syn":
            # SYN 半连接扫描（Stealth Scan）
            # 有管理员权限时发送原始 SYN 包，无权限时降级为 TCP 全连接
            syn_scanner = SynScanner(timeout=self.timeout)
            state, desc = syn_scanner.scan(ip, port)
            return ScanResult(
                ip=ip,
                port=port,
                protocol=proto,
                state=state,
                service=None,          # SYN 扫描不获取 Banner（连接未建立）
                banner=None,
                error_msg=None if state != PortState.ERROR else desc,
                response_time_ms=(time.time() - start) * 1000,
            )

完整 scan_single() 方法结构示例：

    def scan_single(self, ip: str, port: int, protocol: str) -> ScanResult:
        start = time.time()
        proto = protocol.lower()
        try:
            if proto == "tcp":
                state, service, banner = scan_tcp(ip, port, self.timeout)
            elif proto == "udp":
                state, service, banner = scan_udp(ip, port, self.timeout)
            elif proto == "syn":
                syn_scanner = SynScanner(timeout=self.timeout)
                state, desc = syn_scanner.scan(ip, port)
                service = None
                banner = None
                return ScanResult(
                    ip=ip, port=port, protocol=proto, state=state,
                    service=service, banner=banner,
                    error_msg=None if state != PortState.ERROR else desc,
                    response_time_ms=(time.time() - start) * 1000,
                )
            else:
                return ScanResult(...)
            return ScanResult(...)
        except Exception as e:
            return ScanResult(...)

【修改位置 3】main_window.py 协议选择下拉框
------------------------------------------
在 _init_ui() 的协议选择区，添加 "syn" 选项：

    self.cb_proto = QComboBox()
    self.cb_proto.addItems(["tcp", "udp", "syn"])  # ← 添加 "syn"

【修改位置 4】main_window.py 启动权限检测（可选）
----------------------------------------------
在 start_scan() 方法中，扫描前检测 SYN 权限并提示：

    def start_scan(self):
        ...
        # SYN 扫描权限预检
        if proto == "syn":
            from core.syn_scanner import _check_admin
            if not _check_admin():
                QMessageBox.warning(
                    self, "权限提示",
                    "SYN 半连接扫描需要管理员权限。\n"
                    "当前为普通权限，程序将自动降级为 TCP 全连接扫描。\n"
                    "结果将标记为 [降级] 提示。"
                )
        ...

【修改位置 5】main.py CLI 参数
----------------------------
在 argparse 的 --protocol choices 中添加 "syn"：

    parser.add_argument(
        "--protocol", "-P",
        choices=["tcp", "udp", "syn"],  # ← 添加 "syn"
        default="tcp",
        help="扫描协议 [tcp]",
    )

【修改位置 6】config.py 协议列表（可选）
----------------------------------------
如果 config.py 中有协议相关常量，添加 "syn"：

    SCAN_PROTOCOLS = ["tcp", "udp", "syn"]

【完整集成后的扫描流程】
-----------------------

    用户选择协议 "syn"
        ↓
    GUI/CLI → ScanConfig(protocol="syn")
        ↓
    PortScanner.scan_single(ip, port, "syn")
        ↓
    SynScanner.scan(ip, port)
        ↓
    _check_admin()
        ├─────→ [有权限] → _send_syn_packet(ip, port)
        │                    → 构造 IP 头 (20 字节)
        │                    → 构造 TCP 头 (20 字节, Flags=SYN)
        │                    → 计算 TCP 校验和（含伪首部）
        │                    → 创建 Raw Socket (IPPROTO_TCP)
        │                    → 发送完整报文
        │                    → 接收响应
        │                    → _parse_syn_response()
        │                        → SYN+ACK → OPEN
        │                        → RST → CLOSED
        │                        → 超时 → FILTERED
        │
        └─────→ [无权限] → _tcp_connect_fallback(ip, port)
                             → 标准 TCP socket.connect()
                             → 连接成功 → OPEN [降级标记]
                             → 连接拒绝 → CLOSED [降级标记]
                             → 超时 → FILTERED [降级标记]
        ↓
    返回 ScanResult(state=OPEN/CLOSED/FILTERED/ERROR)
        ↓
    GUI 表格展示结果（绿色=OPEN，白色=CLOSED，黄色=FILTERED，红色=ERROR）

【技术亮点】
-----------
1. 手动构造 IP/TCP 头：使用 struct.pack 按 RFC 793/791 格式填充二进制报文
2. 校验和计算：遵循 RFC 1071 的 16 位累加回卷算法
3. 伪首部校验：TCP 校验和计算包含伪首部（源IP+目的IP+协议+长度）
4. 权限检测：Windows 使用 ctypes.windll.shell32.IsUserAnAdmin()
5. 自动降级：无权限时不报错退出，自动切换为 TCP 全连接，保证可用性
6. 保守策略：仅当明确收到 SYN+ACK 时判定 OPEN，降低误报率

【注意事项】
-----------
• Windows 防火墙可能拦截 Raw Socket 发送的 SYN 包，导致所有端口显示 FILTERED
• 部分杀毒软件可能将 Raw Socket 操作标记为可疑行为
• SYN 扫描无法获取 Banner 信息（连接未建立）
• 建议在虚拟机或隔离测试环境中验证 SYN 扫描功能
• 频繁发送 SYN 包可能触发防火墙 SYN Flood 防护规则

【测试验证】
-----------
1. 管理员权限运行：扫描本地回环 127.0.0.1:80，应显示 OPEN 或 CLOSED
2. 普通权限运行：应自动降级，结果含 [降级] 标记
3. 扫描不存在的主机：应显示 FILTERED（超时）
4. 扫描关闭的端口：应显示 CLOSED（收到 RST）或 FILTERED（防火墙）
"""
