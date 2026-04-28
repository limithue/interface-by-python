# python接口.py 完整代码（含PortScanner类）
import socket
import threading
import time
import random
from config import DEFAULT_TIMEOUT  # 导入config中的超时配置

# TCP 端口扫描函数
def scan_tcp(ip, port, timeout=DEFAULT_TIMEOUT):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0  # 0表示端口开放
    except:
        return False

# UDP 端口扫描函数
def scan_udp(ip, port, timeout=DEFAULT_TIMEOUT):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"", (ip, port))
        sock.recvfrom(1024)
        sock.close()
        return True
    except:
        return False

# IP存活检测（简易ICMP ping）
def is_alive(ip):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(1)
        sock.sendto(b"ping", (ip, 0))
        sock.recvfrom(1024)
        sock.close()
        return True
    except:
        return False

# 多线程端口扫描类（必须完整定义，否则导入失败）
class PortScanner:
    def __init__(self, threads=10):
        # 限制线程数在1-20之间（避免线程过多）
        self.threads = max(1, min(threads, 20))
        self.open_ports = []  # 存储开放端口结果
        self.lock = threading.Lock()  # 线程锁，防止多线程写入冲突

    def _worker(self, ip, port, scan_func):
        # 单个线程的扫描逻辑
        if scan_func(ip, port):
            with self.lock:  # 加锁保证数据安全
                self.open_ports.append((ip, port, "OPEN"))
        # 随机延迟（隐蔽扫描，避免被防火墙拦截）
        time.sleep(random.uniform(0.01, 0.05))

    def start_scan(self, ip_list, port_list, protocol="tcp"):
        # 选择扫描协议（TCP/UDP）
        scan_func = scan_tcp if protocol == "tcp" else scan_udp
        thread_list = []

        # 遍历IP和端口，创建扫描线程
        for ip in ip_list:
            if not is_alive(ip):  # 先检测IP是否存活，不存活则跳过
                continue
            for port in port_list:
                t = threading.Thread(target=self._worker, args=(ip, port, scan_func))
                thread_list.append(t)

        # 分批启动线程（避免一次性创建过多线程）
        for i in range(0, len(thread_list), self.threads):
            batch = thread_list[i:i+self.threads]
            for t in batch:
                t.start()  # 启动批次内线程
            for t in batch:
                t.join()   # 等待批次内线程完成

        return self.open_ports

# 可选：测试代码（运行本文件时验证类是否可用）
if __name__ == "__main__":
    test_scanner = PortScanner(threads=5)
    test_result = test_scanner.start_scan(["127.0.0.1"], [80], protocol="tcp")
    print("测试扫描结果：", test_result)