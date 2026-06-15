#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图形界面层
职责：PyQt6 主界面，零业务逻辑，仅负责布局、事件绑定、数据展示
通过 ScanWorker（QThread）与核心引擎交互，避免界面卡顿
"""

import sys
import threading
import os
import time
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QPlainTextEdit, QProgressBar, QMessageBox, QFileDialog,
    QGroupBox, QSplitter, QStatusBar, QHeaderView, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QCheckBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor

from core.models import ScanConfig, ScanResult, PortState
from core.ip_parser import resolve_targets
from core.port_parser import resolve_ports

from core.thread_manager import ThreadManager
from utils.exporters import ExporterRegistry, ExportMeta, OverwriteStrategy
from core.scanner import PortScanner
from utils.config_manager import ConfigManager
import config


# ============================================================
# 1. GUI 覆盖确认策略（不污染 exporters 模块）
# ============================================================

class GUIPromptOverwriteStrategy(OverwriteStrategy):
    """
    GUI 模态覆盖确认策略

    此类放在 GUI 层，exporters 模块保持纯标准库，低耦合。
    """

    def __init__(self, parent_widget):
        self.parent = parent_widget

    def should_overwrite(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return True
        reply = QMessageBox.question(
            self.parent,
            "文件已存在",
            f"文件 [{os.path.basename(filepath)}] 已存在，是否覆盖？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,  # 默认选「否」
        )
        return reply == QMessageBox.StandardButton.Yes


# ============================================================
# 2. 工作线程（连接扫描器与线程管理器，转换 PyQt 信号）
# ============================================================

class ScanWorker(QThread):
    """
    扫描工作线程

    在独立 QThread 中运行 ThreadManager + PortScanner，
    通过信号将结果实时发射回主线程 GUI。
    """

    progress = pyqtSignal(int)                 # 0-100
    log_msg = pyqtSignal(str)
    result = pyqtSignal(object)                # ScanResult
    finished = pyqtSignal(list)                # List[ScanResult]
    error = pyqtSignal(str)
    stats_update = pyqtSignal(int, int, int)   # total, processed, open_count

    def __init__(
        self,
        targets: List[str],
        ports: List[int],
        scan_config: ScanConfig,
        scanner: Optional[PortScanner] = None,
        thread_mgr: Optional[ThreadManager] = None,
    ):
        super().__init__()
        self.targets = targets
        self.ports = ports
        self.scan_config = scan_config
        # 依赖注入：允许外部替换 mock 实现，便于单元测试
        self.scanner = scanner or PortScanner(scan_config.timeout)
        self.thread_mgr = thread_mgr or ThreadManager(
            scan_config.threads,
            scan_config.delay_min,
            scan_config.delay_max,
        )
        self.results: List[ScanResult] = []
        self._open_count = 0
        self._stat_lock = threading.Lock()

    def run(self) -> None:
        try:
            # 1. 构建任务并预检存活
            tasks = []
            for ip in self.targets:
                if self.scan_config.skip_offline:
                    self.log_msg.emit(f"[PING] 检测 {ip} 存活状态...")
                    if not self.scanner.ping_host(ip):
                        self.log_msg.emit(f"[SKIP] 跳过离线主机: {ip}")
                        continue
                    self.log_msg.emit(f"[ALIVE] {ip} 在线")
                for port in self.ports:
                    tasks.append((ip, port, self.scan_config.protocol))

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

    def pause(self) -> None:
        self.thread_mgr.pause()

    def resume(self) -> None:
        self.thread_mgr.resume()

    def stop(self) -> None:
        self.thread_mgr.stop()


# ============================================================
# 3. 主窗口
# ============================================================

class MainWindow(QMainWindow):
    """
    PyQt6 主窗口

    零业务逻辑，仅负责布局、事件绑定、数据展示。
    所有扫描逻辑委托给 ScanWorker。
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} v{config.VERSION}")
        self.resize(1100, 750)
        self.worker: Optional[ScanWorker] = None
        self.all_results: List[ScanResult] = []
        # 配置管理器实例化：与 GUI 生命周期绑定，但逻辑完全独立
        self.config_mgr = ConfigManager()
        self._init_ui()
        self._apply_styles()
        self._load_config_to_ui()
        self._show_compliance_dialog()

    def _init_ui(self) -> None:
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
        self.in_target.setPlaceholderText("支持: 单IP, IP段(1-100), CIDR(/24), 逗号分隔, 域名")
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
        self.sb_threads.setRange(1, config.MAX_THREADS)
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

        for b in [
            self.btn_start, self.btn_pause, self.btn_stop, self.btn_clear,
            self.btn_export_txt, self.btn_export_csv, self.btn_export_json,
        ]:
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
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.result_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.result_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
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

        # 配置实时同步
        self.chk_ping.stateChanged.connect(
            lambda: self.config_mgr.set("skip_offline", self.chk_ping.isChecked())
        )

    def _show_compliance_dialog(self) -> None:
        """启动时弹出合规提示弹窗"""
        QMessageBox.information(
            self,
            "合规提示",
            "本工具仅用于课程实训、自有局域网排查、授权测试环境。\n"
            "严格遵守《中华人民共和国网络安全法》，\n"
            "严禁未经授权扫描公网或他人网络设备。\n\n"
            "点击「确定」表示您已知晓并同意上述条款。",
        )

    def _load_config_to_ui(self) -> None:
        """将配置管理器的数据映射到 UI 控件"""
        self.chk_ping.setChecked(self.config_mgr.get("skip_offline", True))
        self.sb_threads.setValue(self.config_mgr.get("threads", config.DEFAULT_THREADS))
        self.sb_timeout.setValue(self.config_mgr.get("timeout", config.DEFAULT_TIMEOUT))
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
        """将 UI 当前状态回写配置管理器并持久化"""
        self.config_mgr.set("skip_offline", self.chk_ping.isChecked())
        self.config_mgr.set("threads", self.sb_threads.value())
        self.config_mgr.set("timeout", self.sb_timeout.value())
        self.config_mgr.set("delay", self.sb_delay.value())
        self.config_mgr.set("protocol", self.cb_proto.currentText())
        self.config_mgr.set("target", self.in_target.text())
        self.config_mgr.set("port", self.in_port.text())
        self.config_mgr.set(
            "window_geometry", self.saveGeometry().toHex().data().decode()
        )
        self.config_mgr.save()

    def _apply_styles(self) -> None:
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

    def _update_status(self, total: int, processed: int, open_count: int) -> None:
        self.status.showMessage(
            f"总任务: {total}  |  已完成: {processed}  |  开放端口: {open_count}"
        )

    def log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.appendPlainText(f"[{ts}] {msg}")

    def start_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        try:
            targets = resolve_targets(self.in_target.text())
            ports = resolve_ports(self.in_port.text())
            proto = self.cb_proto.currentText()
            threads = self.sb_threads.value()
            timeout = self.sb_timeout.value()
            delay = self.sb_delay.value()

            self.all_results.clear()
            self.result_table.setRowCount(0)
            self.log_area.clear()
            self.progress.setValue(0)

            cfg = ScanConfig(
                protocol=proto,
                threads=threads,
                timeout=timeout,
                delay_min=0,
                delay_max=delay,
                skip_offline=self.chk_ping.isChecked(),
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
                f"[INIT] 任务就绪: {len(targets)} 个IP x {len(ports)} 个端口 "
                f"= {len(targets) * len(ports)} 个任务"
            )
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", str(e))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动失败: {str(e)}")

    def handle_result(self, res: ScanResult) -> None:
        self.all_results.append(res)
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)

        items = [
            QTableWidgetItem(res.ip),
            QTableWidgetItem(str(res.port)),
            QTableWidgetItem(res.protocol.upper()),
            QTableWidgetItem(res.state.value.upper()),
            QTableWidgetItem(res.service or "unknown"),
            QTableWidgetItem(
                f"{res.response_time_ms:.1f}" if res.response_time_ms else "-"
            ),
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

    def scan_finished(self, results: List[ScanResult]) -> None:
        open_count = sum(1 for r in results if r.state == PortState.OPEN)
        self.log(f"[DONE] 扫描完成，开放端口 {open_count} 个，总记录 {len(results)} 条")
        self._set_controls_running(False)
        self.progress.setValue(100)

    def toggle_pause(self) -> None:
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

    def stop_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("[STOP] 正在终止扫描...")
            self._set_controls_running(False)

    def clear_all(self) -> None:
        self.all_results.clear()
        self.result_table.setRowCount(0)
        self.log_area.clear()
        self.progress.setValue(0)
        self._update_status(0, 0, 0)

    def export_data(self, fmt: str) -> None:
        if not self.all_results:
            QMessageBox.information(self, "提示", "暂无扫描结果可导出")
            return
        filters = {
            "txt": "文本文件 (*.txt)",
            "csv": "CSV 文件 (*.csv)",
            "json": "JSON 文件 (*.json)",
        }
        default_name = f"scan_result_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", default_name, filters.get(fmt, "All Files (*)")
        )
        if not path:
            return
        try:
            # GUI 模式：注入模态弹窗覆盖策略
            policy = GUIPromptOverwriteStrategy(self)
            meta = ExporterRegistry.export(
                self.all_results,
                path,
                fmt=fmt,
                overwrite_strategy=policy,
            )

            QMessageBox.information(
                self,
                "导出成功",
                f"已保存至:\n{meta.filepath}\n\n"
                f"• 记录数: {meta.record_count} 条\n"
                f"• 文件大小: {meta.file_size_bytes / 1024:.1f} KB\n"
                f"• 导出字段: {', '.join(meta.fields)}",
            )
            self.log(
                f"[EXPORT] {meta.format.upper()} 导出成功 | "
                f"{meta.filepath} | {meta.record_count}条 | "
                f"{meta.file_size_bytes / 1024:.1f}KB"
            )
        except FileExistsError as e:
            QMessageBox.warning(self, "导出取消", str(e))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _set_controls_running(self, running: bool) -> None:
        """扫描状态切换时统一禁用/启用输入控件，防止误操作"""
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_pause.setEnabled(running)
        self.btn_pause.setText("⏸ 暂停")
        # 扫描期间禁用所有参数输入控件（含 QCheckBox）
        for w in [
            self.in_target, self.in_port, self.cb_proto,
            self.sb_threads, self.sb_timeout, self.sb_delay, self.chk_ping,
        ]:
            w.setEnabled(not running)

    def closeEvent(self, event) -> None:
        """退出前保存配置并处理运行中的扫描线程"""
        self._save_config_from_ui()
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "确认退出", "扫描正在进行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.stop()
                self.worker.wait(2000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def run_gui() -> None:
    """启动 GUI 应用程序"""
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
