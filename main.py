import socket
# 导入核心扫描类（注意文件名对应）
from python接口 import PortScanner
from config import COMMON_PORTS, DEFAULT_THREADS


# IP解析：支持域名/单IP
def parse_ip(target):
    try:
        return [socket.gethostbyname(target)]
    except socket.gaierror:
        print(f"❌ IP/域名 {target} 解析失败")
        return []


# 端口解析：支持common/单个端口/端口段
def parse_ports(port_str):
    ports = []
    if port_str.lower() == "common":
        ports = list(COMMON_PORTS.keys())
    elif "-" in port_str:
        try:
            start, end = port_str.split("-")
            ports = list(range(int(start), int(end) + 1))
        except:
            print("❌ 端口段格式错误（示例：1-100）")
    elif port_str.isdigit():
        port = int(port_str)
        if 1 <= port <= 65535:
            ports = [port]
        else:
            print("❌ 端口需在1-65535之间")
    else:
        print("❌ 端口格式错误（示例：common/80/1-100）")
    return ports


# 主交互逻辑
def main():
    print("===== Windows轻量级端口扫描工具（仅授权内网使用）=====")
    target = input("请输入目标IP/域名：").strip()
    port_str = input("请输入端口（common/80/1-100）：").strip()

    # 解析IP和端口
    ip_list = parse_ip(target)
    port_list = parse_ports(port_str)

    if not ip_list or not port_list:
        print("❌ 输入无效，退出扫描")
        return

    # 启动扫描
    scanner = PortScanner(threads=DEFAULT_THREADS)
    print(f"\n🔍 开始扫描 {target} 的端口 {port_str}...")
    result = scanner.start_scan(ip_list, port_list, protocol="tcp")

    # 输出结果
    print("\n===== 扫描结果 =====")
    if result:
        for ip, port, status in result:
            service = COMMON_PORTS.get(port, "未知服务")
            print(f"✅ {ip}:{port} - {status} ({service})")
    else:
        print("❌ 未发现开放端口")


if __name__ == "__main__":
    main()