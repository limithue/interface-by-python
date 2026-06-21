#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一入口模块
职责：支持 CLI 命令行与 GUI 可视化双模式启动
处理参数解析、合规提示、扫描调度、结果展示、报告导出
"""

import argparse
import ctypes
import os
import sys
import time
from datetime import datetime
from typing import List

import config
from core.ip_parser import resolve_targets
from core.port_parser import resolve_ports
from core.models import ScanConfig, ScanResult, PortState
from core.scanner import PortScanner, colored, is_alive
from core.thread_manager import ThreadManager
from utils.exporters import (
    ExporterRegistry,
    ExportError,
    PromptCLIOverwriteStrategy,
)


# ============================================================
# 1. 权限检测
# ============================================================

def check_admin() -> bool:
    """
    跨平台权限检测

    Windows: 使用 ctypes.windll.shell32.IsUserAnAdmin
    Linux/macOS: 使用 os.getuid() == 0
    """
    try:
        if sys.platform == "win32":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.getuid() == 0
    except Exception:
        return False


# ============================================================
# 2. 合规提示
# ============================================================

def compliance_prompt() -> None:
    """
    强制合规提示

    控制台输出品红色声明，等待用户输入 yes 确认。
    输入非 yes 则退出程序。
    GUI 模式（无控制台/stdin）下自动跳过。
    """
    # 检测是否处于交互式控制台环境
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            print(colored("[INFO] 非交互环境，跳过控制台合规提示", "yellow"))
            return
    except Exception:
        print(colored("[INFO] 非交互环境，跳过控制台合规提示", "yellow"))
        return

    print(colored("=" * 70, "magenta"))
    print(colored("合规提示 | Compliance Notice", "magenta"))
    print(colored("=" * 70, "magenta"))
    print(config.COMPLIANCE_TEXT)
    print(colored("=" * 70, "magenta"))

    try:
        choice = input(
            colored("请输入 'yes' 确认您已阅读并同意上述条款: ", "yellow")
        ).strip().lower()
    except (EOFError, KeyboardInterrupt, RuntimeError):
        print(colored("\n输入中断，程序退出。", "red"))
        sys.exit(1)

    if choice != "yes":
        print(colored("未确认合规条款，程序退出。", "red"))
        sys.exit(0)
def parse_ip(text: str) -> List[str]:
    """调用 IPParser.resolve_targets，限制 CIDR 大小"""
    return resolve_targets(text)


def parse_ports(text: str) -> List[int]:
    """调用 PortParser.resolve_ports"""
    return resolve_ports(text)


# ============================================================
# 4. 进度条
# ============================================================

def print_progress(current: int, total: int, width: int = 50) -> None:
    """
    原生进度条，无第三方库

    Args:
        current: 已完成任务数
        total: 总任务数
        width: 进度条宽度（字符数）
    """
    if total == 0:
        return
    percent = current / total
    filled = int(width * percent)
    bar = "█" * filled + "-" * (width - filled)
    print(
        f"\r[{bar}] {percent * 100:.1f}% ({current}/{total})",
        end="",
        flush=True,
    )
    if current >= total:
        print()  # 换行


# ============================================================
# 5. 报告导出
# ============================================================

def save_report(
    results: List[ScanResult],
    filepath: str,
    fmt: str,
) -> None:
    """
    导出扫描报告，自动附加合规声明

    Args:
        results: 扫描结果列表
        filepath: 输出文件路径
        fmt: 导出格式（txt/csv/json）

    Raises:
        ExportError: 导出失败
    """
    # 先导出结果
    meta = ExporterRegistry.export(
        results,
        filepath,
        fmt=fmt,
        overwrite_strategy=PromptCLIOverwriteStrategy(),
        output_dir=config.OUTPUT_DIR,
    )

    # 追加合规声明
    with open(meta.filepath, "a", encoding="utf-8") as f:
        f.write(config.COMPLIANCE_TEXT)

    print(colored(f"\n✓ 报告已保存: {meta.filepath}", "green"))
    print(f"  格式: {meta.format}")
    print(f"  记录: {meta.record_count}")
    print(f"  大小: {meta.file_size_bytes} bytes")


# ============================================================
# 6. CLI 扫描流程
# ============================================================

def cli_scan(
    targets: List[str],
    ports: List[int],
    scan_config: ScanConfig,
) -> List[ScanResult]:
    """
    命令行模式扫描流程

    Args:
        targets: 目标 IP 列表
        ports: 目标端口列表
        scan_config: 扫描配置

    Returns:
        扫描结果列表
    """
    scanner = PortScanner(scan_config.timeout)
    thread_mgr = ThreadManager(
        scan_config.threads,
        scan_config.delay_min,
        scan_config.delay_max,
    )

    # 构建任务
    tasks = []
    for ip in targets:
        if scan_config.skip_offline:
            print(f"[PING] 检测 {ip} 存活状态...")
            if not scanner.ping_host(ip):
                print(f"[SKIP] 跳过离线主机: {ip}")
                continue
            print(f"[ALIVE] {ip} 在线")
        for port in ports:
            tasks.append((ip, port, scan_config.protocol))

    if not tasks:
        print(colored("[WARN] 无有效扫描任务", "yellow"))
        return []

    total = len(tasks)
    thread_mgr.set_total(total)

    # 大任务量确认
    if total > 1000:
        print(colored(f"\n⚠ 警告: 扫描任务量较大 ({total} 个任务)", "yellow"))
        # 非交互环境自动继续
        if sys.stdin is None or not sys.stdin.isatty():
            print(colored("[INFO] 非交互环境，自动继续扫描", "yellow"))
        else:
            try:
                confirm = input(
                    colored("确认继续扫描? 请输入 'yes': ", "yellow")
                ).strip().lower()
            except (EOFError, KeyboardInterrupt, RuntimeError):
                print(colored("\n扫描已取消。", "red"))
                return []
            if confirm != "yes":
                print(colored("扫描已取消。", "red"))
                return []
    print(f"\n[INIT] 任务就绪: {len(targets)} 个IP x {len(ports)} 个端口 = {total} 个任务")
    print(f"[INFO] 线程: {scan_config.threads} | 超时: {scan_config.timeout}s | 协议: {scan_config.protocol}")
    print(colored("=" * 70, "cyan"))

    # 填充队列
    for task in tasks:
        thread_mgr.task_queue.put(task)

    # 启动扫描
    results: List[ScanResult] = []
    processed = 0
    open_count = 0

    def worker_func(task):
        return scanner.scan_single(*task)

    thread_mgr.start(worker_func)

    print("\n扫描中...")
    try:
        while True:
            # 轮询结果
            while not thread_mgr.result_queue.empty():
                res: ScanResult = thread_mgr.result_queue.get_nowait()
                results.append(res)
                processed += 1

                if res.state == PortState.OPEN:
                    open_count += 1
                    print(
                        f"\r{colored('[OPEN]', 'green')} {res.ip}:{res.port} "
                        f"({res.service or 'unknown'}) {res.response_time_ms:.1f}ms"
                    )
                elif res.state == PortState.ERROR and res.error_msg:
                    print(f"\r{colored('[ERROR]', 'red')} {res.ip}:{res.port} -> {res.error_msg}")

                print_progress(processed, total)

            # 完成判定
            if thread_mgr._processed >= total and thread_mgr.task_queue.empty():
                break
            time.sleep(0.1)

    except KeyboardInterrupt:
        print(colored("\n\n[!] 收到中断信号，正在停止扫描...", "yellow"))
        thread_mgr.stop()

    thread_mgr.wait()
    print_progress(total, total)

    print(colored("=" * 70, "cyan"))
    print(f"[DONE] 扫描完成，开放端口 {open_count} 个，总记录 {len(results)} 条")

    return results


# ============================================================
# 7. 交互式向导
# ============================================================

def interactive_wizard() -> tuple:
    """
    交互式向导模式

    引导用户逐步输入扫描参数。
    非交互环境（无 stdin）下直接报错退出，提示使用命令行参数。

    Returns:
        (targets, ports, scan_config)
    """
    # 检测交互环境
    if sys.stdin is None or not sys.stdin.isatty():
        print(colored("\n[ERROR] 交互式向导需要控制台输入，但当前环境无 stdin。", "red"))
        print(colored("请使用命令行参数启动，例如:", "yellow"))
        print(colored("  main.exe --target 192.168.1.1 --ports 80,443 --format txt", "cyan"))
        print(colored("  main.exe --gui  # 启动 GUI 模式", "cyan"))
        sys.exit(1)

    print(colored("\n" + "=" * 70, "cyan"))
    print(colored("  Port Scanner v" + config.VERSION + " - 交互式向导", "cyan"))
    print(colored("=" * 70, "cyan"))
    # 目标
    while True:
        target_input = input("\n目标 IP/域名 (支持: 单IP, IP段, CIDR, 逗号分隔): ").strip()
        try:
            targets = parse_ip(target_input)
            break
        except ValueError as e:
            print(colored(f"错误: {e}", "red"))

    # 端口
    while True:
        port_input = input("端口 (支持: common, 单端口, 端口段, 逗号分隔) [common]: ").strip() or "common"
        try:
            ports = parse_ports(port_input)
            break
        except ValueError as e:
            print(colored(f"错误: {e}", "red"))

    # 协议
    proto = input("协议 (tcp/udp) [tcp]: ").strip().lower() or "tcp"

    # 线程
    threads_str = input(f"线程数 (1-{config.MAX_THREADS}) [{config.DEFAULT_THREADS}]: ").strip()
    threads = int(threads_str) if threads_str else config.DEFAULT_THREADS
    threads = max(1, min(threads, config.MAX_THREADS))

    # 超时
    timeout_str = input(f"超时秒数 (1-10) [{config.DEFAULT_TIMEOUT}]: ").strip()
    timeout = int(timeout_str) if timeout_str else int(config.DEFAULT_TIMEOUT)
    timeout = max(1, min(timeout, 10))

    # 延迟
    delay_str = input("随机延迟秒数 (0-5) [0]: ").strip()
    delay = int(delay_str) if delay_str else 0
    delay = max(0, min(delay, 5))

    # 跳过离线
    skip_str = input("跳过离线IP? (y/n) [y]: ").strip().lower()
    skip_offline = skip_str != "n"

    scan_config = ScanConfig(
        protocol=proto,
        threads=threads,
        timeout=timeout,
        delay_min=0,
        delay_max=delay,
        skip_offline=skip_offline,
    )

    return targets, ports, scan_config


# ============================================================
# 8. 主函数
# ============================================================

def main() -> None:
    """
    主入口函数

    流程：权限检测 → 合规提示 → 参数解析 → 大任务确认 → 扫描 → 展示 → 导出
    """
    parser = argparse.ArgumentParser(
        description=f"{config.APP_NAME} v{config.VERSION} - Windows 轻量级端口扫描工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=config.COMPLIANCE_TEXT,
    )
    parser.add_argument(
        "--target", "-T",
        help="目标 IP/域名 (支持: 单IP, IP段, CIDR, 逗号分隔)",
    )
    parser.add_argument(
        "--ports", "-p",
        default="common",
        help="端口 (支持: common, 单端口, 端口段, 逗号分隔) [common]",
    )
    parser.add_argument(
        "--protocol", "-P",
        choices=["tcp", "udp"],
        default="tcp",
        help="扫描协议 [tcp]",
    )
    parser.add_argument(
        "--threads", "-t",
        type=int,
        default=config.DEFAULT_THREADS,
        help=f"并发线程数 (1-{config.MAX_THREADS}) [{config.DEFAULT_THREADS}]",
    )
    parser.add_argument(
        "--timeout", "-o",
        type=int,
        default=int(config.DEFAULT_TIMEOUT),
        help="单次探测超时秒数 (1-10) [1]",
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=0,
        help="随机延迟秒数 (0-5) [0]",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["txt", "csv", "json"],
        default="txt",
        help="导出格式 [txt]",
    )
    parser.add_argument(
        "--output", "-O",
        help="输出文件路径",
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="启动 GUI 模式",
    )
    parser.add_argument(
        "--no-compliance",
        action="store_true",
        help="跳过合规提示（仅限自动化脚本）",
    )

    args = parser.parse_args()

    # GUI 模式
    if args.gui:
        try:
            from gui.main_window import run_gui
            run_gui()
        except ImportError as e:
            print(colored(f"GUI 模式需要 PyQt6: {e}", "red"))
            sys.exit(1)
        return

    # 权限检测
    is_admin = check_admin()
    if is_admin:
        print(colored("[INFO] 当前以管理员权限运行", "green"))
    else:
        print(colored("[INFO] 当前为普通权限，ICMP 探测将自动降级为 TCP", "yellow"))

    # 合规提示
    if not args.no_compliance:
        compliance_prompt()

    # 参数解析
    if args.target:
        # 命令行模式
        try:
            targets = parse_ip(args.target)
        except ValueError as e:
            print(colored(f"目标解析错误: {e}", "red"))
            sys.exit(1)

        try:
            ports = parse_ports(args.ports)
        except ValueError as e:
            print(colored(f"端口解析错误: {e}", "red"))
            sys.exit(1)

        threads = max(1, min(args.threads, config.MAX_THREADS))
        timeout = max(1, min(args.timeout, 10))
        delay = max(0, min(args.delay, 5))

        scan_config = ScanConfig(
            protocol=args.protocol,
            threads=threads,
            timeout=timeout,
            delay_min=0,
            delay_max=delay,
            skip_offline=True,
        )
    else:
        # 交互式向导
        targets, ports, scan_config = interactive_wizard()

    # 扫描
    results = cli_scan(targets, ports, scan_config)

    if not results:
        print(colored("\n无扫描结果，程序结束。", "yellow"))
        return

    # 结果展示
    print(colored("\n" + "=" * 70, "cyan"))
    print(colored("扫描结果汇总", "cyan"))
    print(colored("=" * 70, "cyan"))

    open_results = [r for r in results if r.state == PortState.OPEN]
    if open_results:
        print(colored(f"\n开放端口 ({len(open_results)} 个):", "green"))
        for r in open_results:
            print(f"  {r.ip}:{r.port}/{r.protocol}  [{r.service or 'unknown'}]")
    else:
        print(colored("\n未发现开放端口。", "yellow"))

    # 导出报告
    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"scan_report_{timestamp}.{args.format}"

    try:
        save_report(results, output_path, args.format)
    except ExportError as e:
        print(colored(f"导出失败: {e}", "red"))
    except Exception as e:
        print(colored(f"未知错误: {e}", "red"))

    print(colored("\n程序正常结束。", "green"))


if __name__ == "__main__":
    main()
