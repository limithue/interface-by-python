#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高内聚低耦合重构版 PyQt6 端口扫描器
职责拆分：
  - models      : 数据契约 (ScanResult / PortState / ScanConfig)
  - parsers     : 输入解析 (IPParser / PortParser)
  - scanner     : 扫描实现 (PortScanner) —— 仅依赖 socket/subprocess
  - thread_mgr  : 并发调度 (ThreadManager) —— 仅依赖 threading/queue
  - exporters   : 导出策略 (Txt/Csv/Json + Registry) —— 仅依赖标准库
  - worker      : 工作线程 (ScanWorker) —— 连接扫描器与线程管理器，转换 PyQt 信号
  - gui         : 界面层 (MainWindow) —— 仅依赖 PyQt6
  - config_mgr  : 配置持久化 (ConfigManager) —— 仅依赖标准库，与 GUI 解耦
"""

import sys
import os
import time
import json
import csv
import socket
import subprocess
import threading
import queue
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Optional, Callable, Tuple
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QPlainTextEdit, QProgressBar, QMessageBox, QFileDialog,
    QGroupBox, QSplitter, QStatusBar, QHeaderView, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QCheckBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor


# ============================================================
# 1. 数据模型层（高内聚：所有模块共享同一数据契约）
# ============================================================

class PortState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"
    ERROR = "error"


@dataclass(frozen=True)
class ScanResult:
    """扫描结果不可变数据对象，消除元组/字典混用风险"""
    ip: str
    port: int
    protocol: str
    state: PortState
    service: Optional[str] = None
    banner: Optional[str] = None
    error_msg: Optional[str] = None
    response_time_ms: Optional[float] = None


@dataclass
class ScanConfig:
    """扫描运行时配置，替代散落的局部参数"""
    protocol: str
    threads: int
    timeout: int
    delay_min: float
    delay_max: float
    skip_offline: bool


class AppConfig:
    """全局静态常量（无需热更新）"""
    VERSION = "2.0.0"
    APP_NAME = "Port Scanner"
    DEFAULT_THREADS = 10
    DEFAULT_TIMEOUT = 2
    MAX_THREADS = 20          # 任务书约束


# ============================================================
# 2. 配置管理层（高内聚低耦合：封装持久化，GUI 无感文件 IO）
# ============================================================

class ConfigManager:
    """
    配置持久化管理器
    - 职责单一：仅负责配置的读写与默认值回退
    - 低耦合：不依赖任何 GUI / 网络 / 扫描模块
    - 高内聚：所有配置键名、默认值、序列化逻辑集中在此
    """

    DEFAULTS = {
        "skip_offline": True,
        "threads": AppConfig.DEFAULT_THREADS,
        "timeout": AppConfig.DEFAULT_TIMEOUT,
        "delay": 0,
        "protocol": "tcp",
        "target": "127.0.0.1,192.168.1.1-10",
        "port": "common",
        "window_geometry": None,
    }

    def __init__(self, filepath: str = "scanner_config.json"):
        self._filepath = filepath
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """从 JSON 加载配置；文件缺失或损坏时回退到默认值"""
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # 合并策略：以默认值为基础，用已存值覆盖
                self._data = {**self.DEFAULTS, **loaded}
            except (json.JSONDecodeError, OSError, TypeError):
                self._data = self.DEFAULTS.copy()
        else:
            self._data = self.DEFAULTS.copy()

    def save(self) -> None:
        """原子化写入配置，异常静默处理避免阻塞 GUI 关闭"""
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 无写权限时不阻塞退出流程

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value


# ============================================================
# 3. 解析器层（低耦合：纯函数，无 GUI / 网络依赖）
# ============================================================

class IPParser:
    @staticmethod
    def resolve_targets(text: str) -> List[str]:
        if not text or not text.strip():
            raise ValueError("目标IP不能为空")
        targets = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            # IP 段：192.168.1.10-20
            if "-" in part and all(c.isdigit() or c in ".-" for c in part):
                base, end = part.rsplit("-", 1)
                prefix, start = base.rsplit(".", 1)
                for i in range(int(start), int(end) + 1):
                    targets.append(f"{prefix}.{i}")
            else:
                # 域名或单 IP：预检解析能力
                try:
                    socket.getaddrinfo(part, None)
                    targets.append(part)
                except socket.gaierror:
                    raise ValueError(f"无法解析目标: {part}")
        # 去重并保序
        return list(dict.fromkeys(targets))


class PortParser:
    COMMON = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
              3389, 3306, 5432, 8080, 8443]

    @staticmethod
    def resolve_ports(text: str) -> List[int]:
        text = text.strip().lower()
        if text == "common":
            return PortParser.COMMON[:]
        ports = []
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                ports.extend(range(int(s), int(e) + 1))
            else:
                ports.append(int(part))
        ports = sorted({p for p in ports if 1 <= p <= 65535})
        if not ports:
            raise ValueError("无有效端口")
        return ports


# ============================================================
# 4. 扫描器层（高内聚：只负责 socket 探测与服务识别）
# ============================================================

class PortScanner:
    """端口扫描核心实现，返回统一的 ScanResult，内部消化所有异常"""

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
        self._icmp_available = True

    def ping_host(self, ip: str) -> bool:
        """ICMP 探测；无管理员权限时自动降级为 TCP 探测"""
        if not self._icmp_available:
            return self._tcp_ping(ip)
        try:
            if sys.platform == "win32":
                cmd = ["ping", "-n", "1", "-w", "1000", ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", ip]
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, check=False
            )
            return result.returncode == 0
        except (PermissionError, OSError):
            self._icmp_available = False
            return self._tcp_ping(ip)
        except Exception:
            return False

    def _tcp_ping(self, ip: str, port: int = 80) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=self.timeout):
                return True
        except Exception:
            return False

    def scan_single(self, ip: str, port: int, protocol: str) -> ScanResult:
        start = time.time()
        proto = protocol.lower()
        try:
            if proto == "tcp":
                state, service, banner = self._scan_tcp(ip, port)
            elif proto == "udp":
                state, service, banner = self._scan_udp(ip, port)
            else:
                return ScanResult(
                    ip=ip, port=port, protocol=proto, state=PortState.ERROR,
                    error_msg=f"未知协议: {proto}",
                    response_time_ms=(time.time() - start) * 1000
                )
            return ScanResult(
                ip=ip, port=port, protocol=proto, state=state,
                service=service, banner=banner,
                response_time_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return ScanResult(
                ip=ip, port=port, protocol=proto, state=PortState.ERROR,
                error_msg=str(e),
                response_time_ms=(time.time() - start) * 1000
            )

    def _scan_tcp(self, ip: str, port: int) -> Tuple[PortState, Optional[str], Optional[str]]:
        try:
            with socket.create_connection((ip, port), timeout=self.timeout) as s:
                service = self._identify_service(port, "tcp")
                s.settimeout(1.0)
                try:
                    banner = s.recv(1024).decode("utf-8", errors="ignore").strip()
                except Exception:
                    banner = None
                return PortState.OPEN, service, banner
        except socket.timeout:
            return PortState.FILTERED, None, None
        except ConnectionRefusedError:
            return PortState.CLOSED, None, None
        except Exception as e:
            return PortState.ERROR, None, str(e)

    def _scan_udp(self, ip: str, port: int) -> Tuple[PortState, Optional[str], Optional[str]]:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.sendto(b"", (ip, port))
            try:
                data, _ = sock.recvfrom(1024)
                return PortState.OPEN, self._identify_service(port, "udp"), data.decode("utf-8", errors="ignore").strip()
            except socket.timeout:
                # UDP 无响应保守标记为 OPEN（可能开放也可能是过滤，由上层判断）
                return PortState.OPEN, self._identify_service(port, "udp"), None
        except Exception as e:
            return PortState.ERROR, None, str(e)
        finally:
            if sock:
                sock.close()

    def _identify_service(self, port: int, protocol: str) -> str:
        try:
            return socket.getservbyport(port, protocol)
        except (OSError, ValueError):
            fallback = {
                3306: "mysql", 5432: "postgresql", 6379: "redis",
                8080: "http-proxy", 8443: "https-alt", 27017: "mongodb"
            }
            return fallback.get(port, "unknown")


# ============================================================
# 5. 线程管理层（高内聚：只负责任务队列与并发控制）
# ============================================================

class ThreadManager:
    """基于 threading + queue 的轻量级线程池，支持暂停/恢复/停止"""

    def __init__(self, max_workers: int, delay_min: float = 0.0, delay_max: float = 0.0):
        self.max_workers = max_workers
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.task_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self._total = 0
        self._processed = 0
        self._paused = False
        self._stopped = False
        self._pause_cond = threading.Condition()
        self._lock = threading.Lock()
        self._workers: List[threading.Thread] = []

    def set_total(self, n: int):
        self._total = n

    def progress(self) -> float:
        with self._lock:
            if self._total == 0:
                return 0.0
            return (self._processed / self._total) * 100

    def pause(self):
        with self._pause_cond:
            self._paused = True

    def resume(self):
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def stop(self):
        with self._pause_cond:
            self._stopped = True
            self._paused = False
            while not self.task_queue.empty():
                try:
                    self.task_queue.get_nowait()
                except queue.Empty:
                    break
            self._pause_cond.notify_all()

    def start(self, worker_func: Callable[[Tuple], ScanResult]):
        self._workers = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, args=(worker_func,), daemon=True)
            t.start()
            self._workers.append(t)

    def _worker_loop(self, worker_func: Callable[[Tuple], ScanResult]):
        while True:
            with self._pause_cond:
                while self._paused and not self._stopped:
                    self._pause_cond.wait(timeout=0.5)
                if self._stopped:
                    break

            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                with self._lock:
                    if self._processed >= self._total:
                        break
                continue

            if self._stopped:
                break

            try:
                if self.delay_max > 0:
                    time.sleep(random.uniform(self.delay_min, self.delay_max))
                result = worker_func(task)
                self.result_queue.put(result)
            except Exception as e:
                # 防御：即使 worker_func 抛异常，也包装为 ERROR 结果入队
                ip, port, proto = task
                self.result_queue.put(
                    ScanResult(ip=ip, port=port, protocol=proto,
                               state=PortState.ERROR, error_msg=str(e))
                )
            finally:
                with self._lock:
                    self._processed += 1

    def wait(self):
        for t in self._workers:
            t.join(timeout=1.0)


# ============================================================
# 6. 导出器层（低耦合：策略模式，新增格式无需修改 GUI）
# ============================================================

class IExporter(ABC):
    @abstractmethod
    def export(self, results: List[ScanResult], filepath: str) -> str:
        pass

    @abstractmethod
    def extension(self) -> str:
        pass


class TxtExporter(IExporter):
    def extension(self) -> str:
        return ".txt"

    def export(self, results: List[ScanResult], filepath: str) -> str:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"扫描报告 — 生成时间: {datetime.now()}\n")
            f.write("-" * 70 + "\n")
            for r in results:
                svc = f" ({r.service})" if r.service else ""
                f.write(f"{r.ip}:{r.port}/{r.protocol} [{r.state.value.upper()}]{svc}")
                if r.error_msg:
                    f.write(f" | 错误: {r.error_msg}")
                f.write("\n")
        return filepath


class CsvExporter(IExporter):
    def extension(self) -> str:
        return ".csv"

    def export(self, results: List[ScanResult], filepath: str) -> str:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["IP", "Port", "Protocol", "State", "Service", "Banner", "Error", "Time(ms)"])
            for r in results:
                writer.writerow([
                    r.ip, r.port, r.protocol, r.state.value,
                    r.service or "", r.banner or "", r.error_msg or "",
                    f"{r.response_time_ms:.2f}" if r.response_time_ms else ""
                ])
        return filepath


class JsonExporter(IExporter):
    def extension(self) -> str:
        return ".json"

    def export(self, results: List[ScanResult], filepath: str) -> str:
        data = [{**asdict(r), "state": r.state.value} for r in results]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath


class ExporterRegistry:
    """导出器注册中心，GUI 通过格式名调用，无需关心具体类"""
    _exporters = {
        "txt": TxtExporter(),
        "csv": CsvExporter(),
        "json": JsonExporter(),
    }

    @classmethod
    def export(cls, results: List[ScanResult], filepath: str, fmt: str) -> str:
        fmt = fmt.lower().lstrip(".")
        exporter = cls._exporters.get(fmt)
        if not exporter:
            raise ValueError(f"不支持的导出格式: {fmt}")
        if not filepath.endswith(exporter.extension()):
            filepath += exporter.extension()
        return exporter.export(results, filepath)


# ============================================================
# 7. 工作线程层（控制层：连接扫描器与线程管理器，转换信号）
# ============================================================

class ScanWorker(QThread):
    progress = pyqtSignal(int)                 # 0-100
    log_msg = pyqtSignal(str)
    result = pyqtSignal(object)              # ScanResult
    finished = pyqtSignal(list)              # List[ScanResult]
    error = pyqtSignal(str)
    stats_update = pyqtSignal(int, int, int) # total, processed, open_count

    def __init__(self, targets: List[str], ports: List[int], config: ScanConfig,
                 scanner: Optional[PortScanner] = None,
                 thread_mgr: Optional[ThreadManager] = None):
        super().__init__()
        self.targets = targets
        self.ports = ports
        self.config = config
        # 依赖注入：允许外部替换 mock 实现，便于单元测试
        self.scanner = scanner or PortScanner(config.timeout)
        self.thread_mgr = thread_mgr or ThreadManager(
            config.threads, config.delay_min, config.delay_max
        )
        self.results: List[ScanResult] = []
        self._open_count = 0
        self._stat_lock = threading.Lock()

    def run(self):
        try:
            # 1. 构建任务并预检存活
            tasks = []
            for ip in self.targets:
                if self.config.skip_offline:
                    self.log_msg.emit(f"[PING] 检测 {ip} 存活状态...")
                    if not self.scanner.ping_host(ip):
                        self.log_msg.emit(f"[SKIP] 跳过离线主机: {ip}")
                        continue
                    self.log_msg.emit(f"[ALIVE] {ip} 在线")
                for port in self.ports:
                    tasks.append((ip, port, self.config.protocol))

            if not tasks:
                self.log_msg.emit("[WARN] 无有效扫描任务")
                self.finished.emit([])
                return

            total = len(tasks)
            self.thread_mgr.set_total(total)
            self.stats_update.emit(total, 0, 0)

            # 2. 填充队列
            for task in tasks:
                self.thread_mgr.task_queue.put(task)

            # 3. 启动工作线程
            self.thread_mgr.start(self._worker_func)

            # 4. 轮询结果（主循环在 QThread 中，不阻塞 GUI）
            processed = 0
            while True:
                if self.thread_mgr._stopped:
                    self.log_msg.emit("[STOP] 扫描被用户终止")
                    break

                while not self.thread_mgr.result_queue.empty():
                    res: ScanResult = self.thread_mgr.result_queue.get_nowait()
                    self.result.emit(res)
                    self.results.append(res)
                    processed += 1

                    if res.state == PortState.OPEN:
                        with self._stat_lock:
                            self._open_count += 1
                        self.log_msg.emit(
                            f"[OPEN] {res.ip}:{res.port} ({res.service or 'unknown'}) "
                            f"{res.response_time_ms:.1f}ms"
                        )
                    elif res.state == PortState.ERROR and res.error_msg:
                        self.log_msg.emit(f"[ERROR] {res.ip}:{res.port} -> {res.error_msg}")

                    self.stats_update.emit(total, processed, self._open_count)

                prog = self.thread_mgr.progress()
                self.progress.emit(int(prog))

                # 完成判定：已处理数达到总数且任务队列为空
                if self.thread_mgr._processed >= total and self.thread_mgr.task_queue.empty():
                    break
                time.sleep(0.1)

            self.thread_mgr.wait()
            self.progress.emit(100)
            self.finished.emit(self.results)

        except Exception as e:
            self.error.emit(str(e))

    def _worker_func(self, task: Tuple[str, int, str]) -> ScanResult:
        ip, port, proto = task
        return self.scanner.scan_single(ip, port, proto)

    def pause(self):
        self.thread_mgr.pause()

    def resume(self):
        self.thread_mgr.resume()

    def stop(self):
        self.thread_mgr.stop()


# ============================================================
# 8. GUI 层（表现层：零业务逻辑，只负责布局、绑定、展示）
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{AppConfig.APP_NAME} v{AppConfig.VERSION}")
        self.resize(1100, 750)
        self.worker: Optional[ScanWorker] = None
        self.all_results: List[ScanResult] = []
        # 配置管理器实例化：与 GUI 生命周期绑定，但逻辑完全独立
        self.config_mgr = ConfigManager()
        self._init_ui()
        self._apply_styles()
        self._load_config_to_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- 输入参数组 ---
        input_group = QGroupBox("扫描参数")
        input_layout = QVBoxLayout()

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("目标IP:"))
        self.in_target = QLineEdit()
        self.in_target.setPlaceholderText("支持: 单IP, IP段(1-100), 逗号分隔, 域名")
        h1.addWidget(self.in_target)
        input_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("端口:"))
        self.in_port = QLineEdit()
        self.in_port.setPlaceholderText("common, 80, 1-1000, 22,80,443")
        h2.addWidget(self.in_port)
        h2.addWidget(QLabel("协议:"))
        self.cb_proto = QComboBox()
        self.cb_proto.addItems(["tcp", "udp"])
        h2.addWidget(self.cb_proto)
        input_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("线程:"))
        self.sb_threads = QSpinBox()
        self.sb_threads.setRange(1, AppConfig.MAX_THREADS)
        h3.addWidget(self.sb_threads)

        h3.addWidget(QLabel("超时(s):"))
        self.sb_timeout = QSpinBox()
        self.sb_timeout.setRange(1, 10)
        h3.addWidget(self.sb_timeout)

        h3.addWidget(QLabel("随机延迟(s):"))
        self.sb_delay = QSpinBox()
        self.sb_delay.setRange(0, 5)
        self.sb_delay.setToolTip("每任务随机延迟 0~N 秒，降低被防火墙拦截概率")
        h3.addWidget(self.sb_delay)

        # === 核心修改：QPushButton(setCheckable) → QCheckBox ===
        self.chk_ping = QCheckBox("跳过离线IP")
        self.chk_ping.setToolTip("无管理员权限时将自动降级为 TCP 探测")
        h3.addWidget(self.chk_ping)
        h3.addStretch()
        input_layout.addLayout(h3)

        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)

        # --- 控制按钮 ---
        ctrl = QWidget()
        ctrl_layout = QHBoxLayout(ctrl)
        self.btn_start = QPushButton("▶ 开始扫描")
        self.btn_pause = QPushButton("⏸ 暂停")
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_clear = QPushButton("🗑 清空结果")

        self.btn_export_txt = QPushButton("导出 TXT")
        self.btn_export_csv = QPushButton("导出 CSV")
        self.btn_export_json = QPushButton("导出 JSON")

        for b in [self.btn_start, self.btn_pause, self.btn_stop, self.btn_clear,
                  self.btn_export_txt, self.btn_export_csv, self.btn_export_json]:
            ctrl_layout.addWidget(b)
        ctrl_layout.addStretch()
        main_layout.addWidget(ctrl)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        main_layout.addWidget(self.progress)

        # --- 结果表格 + 日志 分割区 ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(7)
        self.result_table.setHorizontalHeaderLabels(
            ["IP地址", "端口", "协议", "状态", "服务", "耗时(ms)", "错误信息"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.result_table)

        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 10))
        self.log_area.setMaximumBlockCount(2000)
        splitter.addWidget(self.log_area)
        splitter.setSizes([350, 350])

        main_layout.addWidget(splitter)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_status(0, 0, 0)

        # --- 事件绑定 ---
        self.btn_start.clicked.connect(self.start_scan)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_scan)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_export_txt.clicked.connect(lambda: self.export_data("txt"))
        self.btn_export_csv.clicked.connect(lambda: self.export_data("csv"))
        self.btn_export_json.clicked.connect(lambda: self.export_data("json"))

        # 配置实时同步：用户手动修改参数后自动写回配置对象（不立即刷盘，退出时统一保存）
        self.chk_ping.stateChanged.connect(lambda: self.config_mgr.set("skip_offline", self.chk_ping.isChecked()))

    def _load_config_to_ui(self) -> None:
        """
        高内聚：将配置管理器的数据映射到 UI 控件
        低耦合：仅依赖 ConfigManager.get，不触及文件系统
        """
        self.chk_ping.setChecked(self.config_mgr.get("skip_offline", True))
        self.sb_threads.setValue(self.config_mgr.get("threads", AppConfig.DEFAULT_THREADS))
        self.sb_timeout.setValue(self.config_mgr.get("timeout", AppConfig.DEFAULT_TIMEOUT))
        self.sb_delay.setValue(self.config_mgr.get("delay", 0))
        self.in_target.setText(self.config_mgr.get("target", "127.0.0.1,192.168.1.1-10"))
        self.in_port.setText(self.config_mgr.get("port", "common"))

        proto = self.config_mgr.get("protocol", "tcp")
        idx = self.cb_proto.findText(proto)
        if idx >= 0:
            self.cb_proto.setCurrentIndex(idx)

        # 窗口几何恢复
        geo = self.config_mgr.get("window_geometry")
        if geo:
            self.restoreGeometry(bytes.fromhex(geo))

    def _save_config_from_ui(self) -> None:
        """
        高内聚：将 UI 当前状态回写配置管理器并持久化
        低耦合：GUI 只负责收集控件值，具体序列化由 ConfigManager 处理
        """
        self.config_mgr.set("skip_offline", self.chk_ping.isChecked())
        self.config_mgr.set("threads", self.sb_threads.value())
        self.config_mgr.set("timeout", self.sb_timeout.value())
        self.config_mgr.set("delay", self.sb_delay.value())
        self.config_mgr.set("protocol", self.cb_proto.currentText())
        self.config_mgr.set("target", self.in_target.text())
        self.config_mgr.set("port", self.in_port.text())
        self.config_mgr.set("window_geometry", self.saveGeometry().toHex().data().decode())
        self.config_mgr.save()

    def _apply_styles(self):
        self.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #cccccc; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton { padding: 6px 14px; }
            QLineEdit, QComboBox, QSpinBox { padding: 4px; }
            QTableWidget { gridline-color: #d0d0d0; }
            QHeaderView::section { background-color: #f0f0f0; padding: 4px; border: 1px solid #d0d0d0; }
            QCheckBox { spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)

    def _update_status(self, total: int, processed: int, open_count: int):
        self.status.showMessage(
            f"总任务: {total}  |  已完成: {processed}  |  开放端口: {open_count}"
        )

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.appendPlainText(f"[{ts}] {msg}")

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            targets = IPParser.resolve_targets(self.in_target.text())
            ports = PortParser.resolve_ports(self.in_port.text())
            proto = self.cb_proto.currentText()
            threads = self.sb_threads.value()
            timeout = self.sb_timeout.value()
            delay = self.sb_delay.value()

            self.all_results.clear()
            self.result_table.setRowCount(0)
            self.log_area.clear()
            self.progress.setValue(0)

            cfg = ScanConfig(
                protocol=proto, threads=threads, timeout=timeout,
                delay_min=0, delay_max=delay,
                skip_offline=self.chk_ping.isChecked()
            )

            self.worker = ScanWorker(targets, ports, cfg)
            self.worker.progress.connect(self.progress.setValue)
            self.worker.log_msg.connect(self.log)
            self.worker.result.connect(self.handle_result)
            self.worker.finished.connect(self.scan_finished)
            self.worker.error.connect(self.log)
            self.worker.stats_update.connect(self._update_status)
            self.worker.start()

            self._set_controls_running(True)
            self.log(
                f"[INIT] 任务就绪: {len(targets)} 个IP × {len(ports)} 个端口 "
                f"= {len(targets) * len(ports)} 个任务"
            )
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", str(e))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动失败: {str(e)}")

    def handle_result(self, res: ScanResult):
        self.all_results.append(res)
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)

        items = [
            QTableWidgetItem(res.ip),
            QTableWidgetItem(str(res.port)),
            QTableWidgetItem(res.protocol.upper()),
            QTableWidgetItem(res.state.value.upper()),
            QTableWidgetItem(res.service or "unknown"),
            QTableWidgetItem(f"{res.response_time_ms:.1f}" if res.response_time_ms else "-"),
            QTableWidgetItem(res.error_msg or ""),
        ]

        bg_map = {
            PortState.OPEN: QColor(200, 255, 200),
            PortState.CLOSED: QColor(255, 255, 255),
            PortState.FILTERED: QColor(255, 255, 200),
            PortState.ERROR: QColor(255, 200, 200),
        }
        bg = bg_map.get(res.state, QColor(255, 255, 255))
        for col, item in enumerate(items):
            item.setBackground(bg)
            self.result_table.setItem(row, col, item)

    def scan_finished(self, results: List[ScanResult]):
        open_count = sum(1 for r in results if r.state == PortState.OPEN)
        self.log(f"[DONE] 扫描完成，开放端口 {open_count} 个，总记录 {len(results)} 条")
        self._set_controls_running(False)
        self.progress.setValue(100)

    def toggle_pause(self):
        if not self.worker or not self.worker.isRunning():
            return
        if self.btn_pause.text().startswith("⏸"):
            self.worker.pause()
            self.btn_pause.setText("▶ 恢复")
            self.log("[PAUSE] 扫描已暂停")
        else:
            self.worker.resume()
            self.btn_pause.setText("⏸ 暂停")
            self.log("[RESUME] 扫描已恢复")

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("[STOP] 正在终止扫描...")
            self._set_controls_running(False)

    def clear_all(self):
        self.all_results.clear()
        self.result_table.setRowCount(0)
        self.log_area.clear()
        self.progress.setValue(0)
        self._update_status(0, 0, 0)

    def export_data(self, fmt: str):
        if not self.all_results:
            QMessageBox.information(self, "提示", "暂无扫描结果可导出")
            return
        filters = {
            "txt": "文本文件 (*.txt)",
            "csv": "CSV 文件 (*.csv)",
            "json": "JSON 文件 (*.json)"
        }
        default_name = f"scan_result_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", default_name, filters.get(fmt, "All Files (*)")
        )
        if not path:
            return
        try:
            saved = ExporterRegistry.export(self.all_results, path, fmt)
            QMessageBox.information(self, "导出成功", f"已保存至:\n{saved}")
            self.log(f"[EXPORT] 已导出 {fmt.upper()}: {saved}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _set_controls_running(self, running: bool):
        """扫描状态切换时统一禁用/启用输入控件，防止误操作"""
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_pause.setEnabled(running)
        self.btn_pause.setText("⏸ 暂停")
        # 扫描期间禁用所有参数输入控件（含 QCheckBox）
        for w in [self.in_target, self.in_port, self.cb_proto,
                  self.sb_threads, self.sb_timeout, self.sb_delay, self.chk_ping]:
            w.setEnabled(not running)

    def closeEvent(self, event):
        """退出前保存配置并处理运行中的扫描线程"""
        self._save_config_from_ui()
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "确认退出", "扫描正在进行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.stop()
                self.worker.wait(2000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()