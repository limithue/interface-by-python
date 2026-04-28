"""全局配置模块｜版本、默认参数、端口服务映射"""
VERSION = "1.0.0"
DEFAULT_THREADS = 10
DEFAULT_TIMEOUT = 2.0
MIN_DELAY = 0.05
MAX_DELAY = 0.3
COMMON_PORTS = {21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3306, 3389, 5432, 6379, 8080}

PORT_SERVICES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP",
    110: "POP3", 135: "RPC", 139: "NetBIOS", 443: "HTTPS", 445: "SMB",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 6379: "Redis", 8080: "HTTP-Alt"
}

LOG_FILE = "scan.log"
OUTPUT_DIR = "scan_results"
