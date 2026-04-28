"""PyQt6 GUI 模块｜参数输入、线程绑定、进度/结果展示、启停控制"""
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, 
                             QPlainTextEdit, QProgressBar, QMessageBox, QFileDialog)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont

from core.parser import IPParser, PortParser
from core.scanner import PortScanner
from core.thread_mgr import ThreadManager
from utils.exporter import export_results
import config

class ScanWorker(QThread):
    progress = pyqtSignal(float)
    log_msg = pyqtSignal(str)
    result = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, targets, ports, protocol, threads, timeout, delay_min, delay_max, skip_offline):
        super().__init__()
        self.targets = targets
        self.ports = ports
        self.protocol = protocol
        self.threads = threads
        self.timeout = timeout
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.skip_offline = skip_offline
        self._scanner = PortScanner(timeout)
        self._mgr = ThreadManager(threads, delay_min, delay_max)
        self.results = []

    def run(self):
        try:
            tasks = []
            for ip in self.targets:
                if self.skip_offline and not self._scanner.ping_host(ip):
                    self.log_msg.emit(f"[INFO] 跳过离线主机: {ip}")
                    continue
                for port in self.ports:
                    tasks.append((ip, port, self.protocol))

            self._mgr.set_total(len(tasks))
            if not tasks:
                self.log_msg.emit("[WARN] 无有效扫描任务")
                self.finished.emit([])
                return

            def worker_func(task):
                ip, port, proto = task
                res = self._scanner.scan_single(ip, port, proto)
                return res

            self._mgr.start(worker_func)
            
            # 轮询结果队列
            import time
            while self._mgr.task_queue.qsize() > 0 or self._mgr._processed < len(tasks):
                while not self._mgr.result_queue.empty():
                    res = self._mgr.result_queue.get_nowait()
                    if res[0] == 'error':
                        self.log_msg.emit(f"[ERROR] {res[1]} -> {res[2]}")
                    else:
                        self.result.emit(res)
                        self.results.append(res)
                        if res['state'] == 'open':
                            self.log_msg.emit(f"[OPEN] {res['ip']}:{res['port']} ({res['service']})")
                self.progress.emit(self._mgr.progress())
                time.sleep(0.2)
            
            self._mgr.wait()
            self.finished.emit(self.results)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Windows Port Scanner v{config.VERSION}")
        self.resize(850, 600)
        self.worker = None
        self.all_results = []
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 输入区
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("目标IP:"))
        self.in_target = QLineEdit("127.0.0.1,192.168.1.10-20")
        h1.addWidget(self.in_target)
        layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("端口:"))
        self.in_port = QLineEdit("common")
        h2.addWidget(self.in_port)
        h2.addWidget(QLabel("协议:"))
        self.cb_proto = QComboBox()
        self.cb_proto.addItems(["tcp", "udp"])
        h2.addWidget(self.cb_proto)
        layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("线程:"))
        self.sb_threads = QSpinBox()
        self.sb_threads.setRange(1, 50)
        self.sb_threads.setValue(config.DEFAULT_THREADS)
        h3.addWidget(self.sb_threads)
        h3.addWidget(QLabel("超时(s):"))
        self.sb_timeout = QSpinBox()
        self.sb_timeout.setRange(1, 10)
        self.sb_timeout.setValue(int(config.DEFAULT_TIMEOUT))
        h3.addWidget(self.sb_timeout)
        self.chk_ping = QPushButton("跳过离线IP")
        self.chk_ping.setCheckable(True)
        self.chk_ping.setChecked(True)
        h3.addWidget(self.chk_ping)
        layout.addLayout(h3)

        # 控制区
        h4 = QHBoxLayout()
        self.btn_start = QPushButton("开始扫描")
        self.btn_pause = QPushButton("暂停")
        self.btn_stop = QPushButton("停止")
        self.btn_export = QPushButton("导出结果")
        for b in [self.btn_start, self.btn_pause, self.btn_stop, self.btn_export]:
            h4.addWidget(b)
        layout.addLayout(h4)

        # 进度条
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # 结果展示
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_area)

        # 绑定事件
        self.btn_start.clicked.connect(self.start_scan)
        self.btn_pause.clicked.connect(self.pause_scan)
        self.btn_stop.clicked.connect(self.stop_scan)
        self.btn_export.clicked.connect(self.export_data)

    def log(self, msg: str):
        self.log_area.appendPlainText(f"[{self.log_area.document().blockCount():04}] {msg}")

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            targets = IPParser.resolve_targets(self.in_target.text())
            ports = PortParser.resolve_ports(self.in_port.text())
            proto = self.cb_proto.currentText()
            threads = self.sb_threads.value()
            timeout = self.sb_timeout.value()
            self.all_results = []
            self.log_area.clear()
            self.progress.setValue(0)

            self.worker = ScanWorker(targets, ports, proto, threads, timeout, 0.05, 0.3, self.chk_ping.isChecked())
            self.worker.progress.connect(self.progress.setValue)
            self.worker.log_msg.connect(self.log)
            self.worker.result.connect(self.handle_result)
            self.worker.finished.connect(self.scan_finished)
            self.worker.error.connect(self.log)
            self.worker.start()
            self.btn_start.setEnabled(False)
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", str(e))

    def handle_result(self, res: dict):
        self.all_results.append(res)

    def scan_finished(self, results):
        self.log(f"[DONE] 扫描完成，共发现 {len([r for r in results if r['state']=='open'])} 个开放端口")
        self.btn_start.setEnabled(True)
        self.progress.setValue(100)

    def pause_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker._mgr.pause()
            self.log("[PAUSE] 扫描已暂停")

    def resume_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker._mgr.resume()
            self.log("[RESUME] 扫描已恢复")

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker._mgr.stop()
            self.log("[STOP] 正在终止扫描...")
            self.btn_start.setEnabled(True)

    def export_data(self):
        if not self.all_results:
            QMessageBox.information(self, "提示", "暂无扫描结果可导出")
            return
        fmt = "csv" if self.sender().text() == "导出CSV" else "txt"
        path = export_results(self.all_results, fmt)
        QMessageBox.information(self, "导出成功", f"已保存至: {path}")
