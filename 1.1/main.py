# ============================================================
# main.py - 交互入口与结果展示层
# 职责：输入解析、扫描调度、着色输出、报告导出、权限提示
# ============================================================

import socket
import ipaddress
import os
import sys
import time
from datetime import datetime
from python接口 import PortScanner, colored, is_alive_icmp
from config import COMMON_PORTS, DEFAULT_THREADS, COLORS


def parse_ip(target):
    """
    IP 解析：支持单 IP、域名、C 段网段（如 192.168.1.0/24）
    返回: IP 字符串列表
    """
    target = target.strip()
    ip_list = []

    # 1. 尝试作为 CIDR 网段解析
    if '/' in target:
        try:
            network = ipaddress.ip_network(target, strict=False)
            # 安全限制：禁止 /15 及以下超大网段
            if network.prefixlen < 16:
                print(colored("❌ 网段过大，仅支持 /16 及以上（如 192.168.0.0/16）", "RED"))
                return []
            # 遍历主机地址（排除网络地址和广播地址）
            for ip in network.hosts():
                ip_list.append(str(ip))
            return ip_list
        except ValueError as e:
            print(colored(f"❌ 网段格式错误: {e}", "RED"))
            return []

    # 2. 尝试作为纯 IP 地址解析
    try:
        ip_obj = ipaddress.ip_address(target)
        return [str(ip_obj)]
    except ValueError:
        pass

    # 3. 尝试作为域名解析
    try:
        resolved = socket.gethostbyname(target)
        return [resolved]
    except socket.gaierror:
        print(colored(f"❌ IP/域名 {target} 解析失败，请检查网络或拼写", "RED"))
        return []


def parse_ports(port_str):
    """
    端口解析：支持 common / 单个端口 / 端口段（如 1-100）
    返回: 端口整数列表
    """
    port_str = port_str.strip()
    ports = []

    if port_str.lower() == "common":
        ports = sorted(list(set(COMMON_PORTS.keys())))
    elif "-" in port_str:
        try:
            start, end = port_str.split("-")
            start, end = int(start), int(end)
            if not (1 <= start <= 65535 and 1 <= end <= 65535):
                print(colored("❌ 端口需在 1-65535 之间", "RED"))
                return []
            if start > end:
                start, end = end, start
            ports = list(range(start, end + 1))
        except ValueError:
            print(colored("❌ 端口段格式错误（正确示例：1-100）", "RED"))
            return []
    elif port_str.isdigit():
        port = int(port_str)
        if 1 <= port <= 65535:
            ports = [port]
        else:
            print(colored("❌ 端口需在 1-65535 之间", "RED"))
            return []
    else:
        print(colored("❌ 端口格式错误（正确示例：common / 80 / 1-100）", "RED"))
        return []

    return ports


def print_progress(current, total):
    """原生进度条（\r 回车刷新同一行，无第三方库）"""
    percent = (current / total) * 100
    bar_len = 30
    filled = int(bar_len * current / total)
    bar = '█' * filled + '░' * (bar_len - filled)
    text = f"\r{colored('进度', 'CYAN')}: [{bar}] {current}/{total} ({percent:.1f}%)"
    print(text, end='', flush=True)


def save_report(target, port_str, protocol, results, duration):
    """将扫描结果导出为 TXT 报告文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"scan_report_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("        端口扫描工具 - 扫描报告\n")
        f.write("=" * 60 + "\n")
        f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"扫描目标: {target}\n")
        f.write(f"端口范围: {port_str}\n")
        f.write(f"扫描协议: {protocol.upper()}\n")
        f.write(f"扫描耗时: {duration:.2f} 秒\n")
        f.write(f"开放端口数: {len(results)}\n")
        f.write("-" * 60 + "\n")
        f.write("扫描结果详情:\n")
        f.write("-" * 60 + "\n")

        if results:
            for ip, port, status in results:
                service = COMMON_PORTS.get(port, "未知服务")
                f.write(f"[{status}] {ip}:{port}  ({service})\n")
        else:
            f.write("未发现开放端口\n")

        f.write("=" * 60 + "\n")
        f.write("合规声明: 本工具仅用于授权内网安全测试\n")
        f.write("         严禁用于未授权网络扫描\n")
        f.write("=" * 60 + "\n")

    return filename


def check_admin():
    """检测当前是否以管理员/Root 权限运行"""
    if os.name == 'nt':
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    # Linux/macOS
    return os.getuid() == 0 if hasattr(os, 'getuid') else True


def main():
    # Windows 启用 VT100 颜色支持
    if os.name == 'nt':
        os.system('')

    # 标题
    print(colored("=" * 60, "CYAN"))
    print(colored("    Windows 轻量级多线程端口扫描工具（授权内网使用）", "CYAN"))
    print(colored("=" * 60, "CYAN"))

    # 权限状态提示
    is_admin = check_admin()
    if is_admin:
        print(colored("[✓] 当前以管理员权限运行，ICMP 存活检测可用", "GREEN"))
    else:
        print(colored("[!] 当前为普通权限，ICMP 存活检测将自动降级为 TCP 探测", "YELLOW"))
        print(colored("    （不影响扫描结果，仅改变存活预检方式）", "YELLOW"))
    print()

    # 用户输入
    target = input("请输入目标 IP / 域名 / C段（如 192.168.1.0/24）：").strip()
    port_str = input("请输入端口（common / 80 / 1-100）：").strip()
    proto_input = input("请选择协议（tcp / udp，默认 tcp）：").strip().lower()
    protocol = proto_input if proto_input in ["tcp", "udp"] else "tcp"

    # 解析目标与端口
    ip_list = parse_ip(target)
    port_list = parse_ports(port_str)

    if not ip_list:
        print(colored("\n❌ 目标解析失败，退出扫描", "RED"))
        return
    if not port_list:
        print(colored("\n❌ 端口解析失败，退出扫描", "RED"))
        return

    # 大任务量安全警告
    total_tasks = len(ip_list) * len(port_list)
    if total_tasks > 100000:
        print()
        confirm = input(
            colored(f"⚠️  扫描任务量高达 {total_tasks} 个，确认继续？(y/n)：", "YELLOW")
        ).strip().lower()
        if confirm not in ['y', 'yes']:
            print(colored("已取消扫描", "YELLOW"))
            return

    # 扫描信息汇总
    print(f"\n{colored('🔍 扫描信息', 'BLUE')}:")
    print(f"  目标地址: {target}")
    print(f"  IP 数量:  {len(ip_list)} 个")
    print(f"  端口范围: {port_str} ({len(port_list)} 个端口)")
    print(f"  扫描协议: {protocol.upper()}")
    print(f"  并发线程: {DEFAULT_THREADS} (最大 {MAX_THREADS})")
    print(f"  总任务量: {total_tasks} 个探测")
    print(f"\n{colored('开始扫描...', 'GREEN')}")
    print(colored("（按 Ctrl+C 可随时中断扫描）", "MAGENTA"))
    print()

    # 启动扫描
    scanner = PortScanner(threads=DEFAULT_THREADS)
    start_time = time.time()

    try:
        result = scanner.start_scan(
            ip_list,
            port_list,
            protocol=protocol,
            progress_callback=print_progress if total_tasks > 50 else None
        )
        # 清除进度条残留
        if total_tasks > 50:
            print("\r" + " " * 70 + "\r", end='')
    except KeyboardInterrupt:
        print("\n")
        print(colored("[!] 扫描已被用户中断，正在安全退出...", "YELLOW"))
        result = scanner.open_ports  # 获取已扫描到的部分结果

    duration = time.time() - start_time

    # 结果展示
    print(colored("\n" + "=" * 60, "CYAN"))
    print(colored("                    扫描结果", "CYAN"))
    print(colored("=" * 60, "CYAN"))

    if result:
        print(colored(
            f"✅ 共发现 {len(result)} 个开放端口（耗时 {duration:.2f} 秒）",
            "GREEN"
        ))
        print()
        for ip, port, status in result:
            service = COMMON_PORTS.get(port, "未知服务")
            print(
                f"  {colored('✅', 'GREEN')} "
                f"{ip}:{colored(str(port), 'YELLOW')}  "
                f"{colored(status, 'GREEN')}  ({service})"
            )
    else:
        print(colored(
            f"❌ 未发现开放端口（耗时 {duration:.2f} 秒）",
            "RED"
        ))

    print(colored("=" * 60, "CYAN"))

    # 报告导出
    if result:
        print()
        save_choice = input("是否保存扫描报告？(y/n，默认 y)：").strip().lower()
        if save_choice in ['', 'y', 'yes']:
            fname = save_report(target, port_str, protocol, result, duration)
            print(colored(f"[✓] 报告已保存至当前目录: {fname}", "GREEN"))

    # 合规提示
    print()
    print(colored(
        "[!] 合规提示：本工具仅用于授权内网安全测试，严禁非法使用",
        "MAGENTA"
    ))
    print(colored(
        "    任何未经授权的网络扫描行为均可能违反法律法规",
        "MAGENTA"
    ))


if __name__ == "__main__":
    main()