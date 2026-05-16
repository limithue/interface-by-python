# ============================================================
# config.py - 全局配置与常量定义
# 职责：集中管理端口映射、默认参数、颜色代码
# ============================================================

# 常用端口服务映射（扩展至28个常见服务）
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 135: "MS-RPC",
    139: "NetBIOS-SSN", 443: "HTTPS", 445: "SMB",
    1433: "MSSQL", 1521: "Oracle-TNS", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 6379: "Redis",
    8080: "HTTP-Proxy", 8443: "HTTPS-Alt", 9200: "Elasticsearch",
    27017: "MongoDB", 5000: "UPnP/Flask", 5900: "VNC",
    993: "IMAPS", 995: "POP3S", 1080: "SOCKS",
    143: "IMAP", 2049: "NFS"
}

# TCP 降级存活探测端口（普通权限时使用）
# 优先选择企业内网高概率开放的端口
TCP_ALIVE_PORTS = [80, 443, 22, 3389, 445, 139, 21, 25]

# 默认参数
DEFAULT_TIMEOUT = 1.0       # 单次探测超时（秒）
DEFAULT_THREADS = 10        # 默认并发线程数
MAX_THREADS = 20            # 最大并发上限（防止资源耗尽）

# ANSI 转义颜色代码（Windows 需启用 VT100）
COLORS = {
    "RED": "\033[91m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "MAGENTA": "\033[95m",
    "CYAN": "\033[96m",
    "WHITE": "\033[97m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m"
}