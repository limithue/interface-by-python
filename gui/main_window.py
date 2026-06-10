"""
gui/main_window.py
PyQt6 可视化界面控制
"""
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLineEdit, QPushButton, QCheckBox, QSpinBox, QTextEdit, 
                             QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QLabel)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# 确保能导入同级和上级目录模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import ConfigManager
from utils.exporters import ExporterRegistry, OverwriteStrategy
from utils.logger import ScanLogger
from core.scanner import HostScanner, PortScanner, ScanConfig
from core.thread_mgr import ThreadManager

logger = ScanLogger.get_logger("gui")

# GUI 专属覆盖策略
class PromptGUIOverwriteStrategy(OverwriteStrategy):
    def __init__(self, parent):
        self.parent = parent
    def should_overwrite(self, filepath):
        if os.path.exists(filepath):
            reply = QMessageBox.question(self.parent, '确认覆盖', 
                                         f'文件 {os.path.basename(filepath)} 已存在，是否覆盖？', 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            return reply == QMessageBox.StandardButton.Yes
        return True

class ScanWorker(QThread):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(float)
    finished_signal = pyqtSignal()

    def __init__(self, target, ports, max_threads, skip_offline):
        super().__init__()
        self.target = target
        self.ports = ports
        self.max_threads = max_threads
        self.skip_offline = skip_offline
        self.thread_mgr = ThreadManager(max_threads)
        self.host_scanner = HostScanner()
        self.port_scanner = PortScanner()

    def run(self):
        self.log_signal.emit(f"开始扫描目标: {self.target}")
        # 简化解析逻辑，实际项目中应使用 parsers 模块
        ips = [self.target] 
        ports = [80, 443, 22] if self.ports == "common" else [int(p) for p in self.ports.split(',')]
        
        total_tasks = len(ips) * len(ports)
        self.thread_mgr.start(total_tasks)

        for ip in ips:
            if self.thread_mgr.stop_event.is_set(): break
            
            if self.skip_offline and not self.host_scanner.is_alive(ip):
                self.log_signal.emit(f"[-] {ip} 离线，已跳过")
                with self.thread_mgr.lock:
                    self.thread_mgr.processed += len(ports)
                continue

            for port in ports:
                if self.thread_mgr.stop_event.is_set(): break
                self.thread_mgr.submit(self._scan_task, ip, port)

        self.thread_mgr.wait()
        self.log_signal.emit("扫描任务结束。")
        self.finished_signal.emit()

    def _scan_task(self, ip, port):
        res = self.port_scanner.scan_port(ip, port)
        if res["state"] == "open":
            self.result_signal.emit(res)
        self.progress_signal.emit(self.thread_mgr.progress())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python 网络扫描工具 v2.0")
        self.resize(800, 600)
        
        self.cfg_mgr = ConfigManager()
        self.worker = None
        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 参数输入区
        top_layout = QHBoxLayout()
        self.input_target = QLineEdit("192.168.1.1")
        self.input_ports = QLineEdit(self.cfg_mgr.config.default_ports)
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 100)
        self.spin_threads.setValue(self.cfg_mgr.config.max_threads)
        
        # 【需求修复】使用原生 QCheckBox 替代 QPushButton
        self.chk_skip_offline = QCheckBox("跳过离线IP")
        self.chk_skip_offline.setChecked(self.cfg_mgr.config.skip_offline)

        top_layout.addWidget(QLabel("目标:"))
        top_layout.addWidget(self.input_target)
        top_layout.addWidget(QLabel("端口:"))
        top_layout.addWidget(self.input_ports)
        top_layout.addWidget(QLabel("线程:"))
        top_layout.addWidget(self.spin_threads)
        top_layout.addWidget(self.chk_skip_offline)
        layout.addLayout(top_layout)

        # 控制按钮区
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("开始扫描")
        self.btn_pause = QPushButton("暂停")
        self.btn_stop = QPushButton("停止")
        self.btn_export = QPushButton("导出结果")
        
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_pause)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)

        # 结果与日志区
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["IP", "端口", "状态"])
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        layout.addWidget(self.table, 2)
        layout.addWidget(self.log_text, 1)

        # 信号绑定
        self.btn_start.clicked.connect(self.start_scan)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_scan)
        self.btn_export.clicked.connect(self.export_results)

    def load_config(self):
        self.chk_skip_offline.setChecked(self.cfg_mgr.config.skip_offline)
        self.spin_threads.setValue(self.cfg_mgr.config.max_threads)
        self.input_ports.setText(self.cfg_mgr.config.default_ports)

    def save_config(self):
        self.cfg_mgr.config.skip_offline = self.chk_skip_offline.isChecked()
        self.cfg_mgr.config.max_threads = self.spin_threads.value()
        self.cfg_mgr.config.default_ports = self.input_ports.text()
        self.cfg_mgr.save()

    def start_scan(self):
        self.save_config()
        self.table.setRowCount(0)
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.chk_skip_offline.setEnabled(False) # 扫描时锁定控件

        self.worker = ScanWorker(
            self.input_target.text(), 
            self.input_ports.text(), 
            self.spin_threads.value(),
            self.chk_skip_offline.isChecked()
        )
        self.worker.log_signal.connect(self.append_log)
        self.worker.result_signal.connect(self.add_result)
        self.worker.finished_signal.connect(self.scan_finished)
        self.worker.start()

    def toggle_pause(self):
        if self.worker and self.worker.thread_mgr:
            if self.btn_pause.text() == "暂停":
                self.worker.thread_mgr.pause()
                self.btn_pause.setText("恢复")
            else:
                self.worker.thread_mgr.resume()
                self.btn_pause.setText("暂停")

    def stop_scan(self):
        if self.worker and self.worker.thread_mgr:
            self.worker.thread_mgr.stop()

    def scan_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("暂停")
        self.chk_skip_offline.setEnabled(True) # 恢复控件

    def append_log(self, msg):
        self.log_text.append(msg)

    def add_result(self, res):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(res["ip"]))
        self.table.setItem(row, 1, QTableWidgetItem(str(res["port"])))
        self.table.setItem(row, 2, QTableWidgetItem(res["state"]))

    def export_results(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "导出结果", "", "CSV (*.csv);;JSON (*.json);;TXT (*.txt)")
        if not filepath: return

        data = []
        for row in range(self.table.rowCount()):
            data.append({
                "ip": self.table.item(row, 0).text(),
                "port": self.table.item(row, 1).text(),
                "state": self.table.item(row, 2).text()
            })
        
        strategy = PromptGUIOverwriteStrategy(self)
        if ExporterRegistry.export(data, filepath, strategy):
            QMessageBox.information(self, "成功", "导出完成！")
