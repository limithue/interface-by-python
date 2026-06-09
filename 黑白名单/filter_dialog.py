#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/filter_dialog.py —— 黑白名单管理对话框
=============================================

职责：
  • 提供可视化界面管理黑白名单规则
  • 支持添加/删除 IP 和端口规则
  • 实时同步到 ScanFilter 实例并持久化到 JSON
  • 与 MainWindow 通过信号通信，零直接耦合

设计原则：
  • 高内聚：所有规则管理 UI 逻辑集中在此对话框
  • 低耦合：不直接操作 MainWindow，通过回调/信号传递变更
  • 可复用：可作为独立对话框被任何模块调用
"""

from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QTabWidget, QWidget, QSpinBox, QGroupBox, QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.filter import ScanFilter


class FilterDialog(QDialog):
    """
    黑白名单管理对话框

    信号：
      rules_changed: 当规则发生变更时发射，携带当前 ScanFilter 实例
    """

    rules_changed = pyqtSignal(object)  # 发射 ScanFilter 实例

    def __init__(
        self,
        filter_instance: Optional[ScanFilter] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("扫描规则管理 — 黑白名单")
        self.resize(600, 500)

        # 持有 ScanFilter 实例（深拷贝避免污染外部状态）
        self.filter = filter_instance or ScanFilter()

        self._init_ui()
        self._load_rules_to_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # 说明标签
        info = QLabel(
            "规则说明：\n"
            "• 黑名单：默认禁止扫描的目标/端口\n"
            "• 白名单：明确允许扫描的目标/端口（优先级高于黑名单）\n"
            "• 内置规则（系统保留地址/端口）不可删除，仅可查看"
        )
        info.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(info)

        # Tab 切换：IP 规则 / 端口规则
        self.tabs = QTabWidget()

        # --- IP 规则 Tab ---
        self.tab_ip = QWidget()
        ip_layout = QVBoxLayout(self.tab_ip)

        # 黑名单
        blk_ip_group = QGroupBox("IP 黑名单（禁止扫描）")
        blk_ip_layout = QVBoxLayout(blk_ip_group)
        self.list_ip_black = QListWidget()
        blk_ip_layout.addWidget(self.list_ip_black)

        blk_ip_input_layout = QHBoxLayout()
        self.in_ip_black = QLineEdit()
        self.in_ip_black.setPlaceholderText("输入 IP 或 CIDR，如 192.168.1.1")
        self.btn_add_ip_black = QPushButton("添加")
        self.btn_del_ip_black = QPushButton("删除选中")
        blk_ip_input_layout.addWidget(self.in_ip_black)
        blk_ip_input_layout.addWidget(self.btn_add_ip_black)
        blk_ip_input_layout.addWidget(self.btn_del_ip_black)
        blk_ip_layout.addLayout(blk_ip_input_layout)
        ip_layout.addWidget(blk_ip_group)

        # 白名单
        wht_ip_group = QGroupBox("IP 白名单（明确允许）")
        wht_ip_layout = QVBoxLayout(wht_ip_group)
        self.list_ip_white = QListWidget()
        wht_ip_layout.addWidget(self.list_ip_white)

        wht_ip_input_layout = QHBoxLayout()
        self.in_ip_white = QLineEdit()
        self.in_ip_white.setPlaceholderText("输入 IP 或 CIDR，如 192.168.1.10")
        self.btn_add_ip_white = QPushButton("添加")
        self.btn_del_ip_white = QPushButton("删除选中")
        wht_ip_input_layout.addWidget(self.in_ip_white)
        wht_ip_input_layout.addWidget(self.btn_add_ip_white)
        wht_ip_input_layout.addWidget(self.btn_del_ip_white)
        wht_ip_layout.addLayout(wht_ip_input_layout)
        ip_layout.addWidget(wht_ip_group)

        self.tabs.addTab(self.tab_ip, "IP 规则")

        # --- 端口规则 Tab ---
        self.tab_port = QWidget()
        port_layout = QVBoxLayout(self.tab_port)

        # 黑名单
        blk_port_group = QGroupBox("端口黑名单（禁止扫描）")
        blk_port_layout = QVBoxLayout(blk_port_group)
        self.list_port_black = QListWidget()
        blk_port_layout.addWidget(self.list_port_black)

        blk_port_input_layout = QHBoxLayout()
        self.in_port_black = QSpinBox()
        self.in_port_black.setRange(1, 65535)
        self.in_port_black.setPlaceholderText("端口号")
        self.btn_add_port_black = QPushButton("添加")
        self.btn_del_port_black = QPushButton("删除选中")
        blk_port_input_layout.addWidget(QLabel("端口:"))
        blk_port_input_layout.addWidget(self.in_port_black)
        blk_port_input_layout.addWidget(self.btn_add_port_black)
        blk_port_input_layout.addWidget(self.btn_del_port_black)
        blk_port_layout.addLayout(blk_port_input_layout)
        port_layout.addWidget(blk_port_group)

        # 白名单
        wht_port_group = QGroupBox("端口白名单（明确允许）")
        wht_port_layout = QVBoxLayout(wht_port_group)
        self.list_port_white = QListWidget()
        wht_port_layout.addWidget(self.list_port_white)

        wht_port_input_layout = QHBoxLayout()
        self.in_port_white = QSpinBox()
        self.in_port_white.setRange(1, 65535)
        self.btn_add_port_white = QPushButton("添加")
        self.btn_del_port_white = QPushButton("删除选中")
        wht_port_input_layout.addWidget(QLabel("端口:"))
        wht_port_input_layout.addWidget(self.in_port_white)
        wht_port_input_layout.addWidget(self.btn_add_port_white)
        wht_port_input_layout.addWidget(self.btn_del_port_white)
        wht_port_layout.addLayout(wht_port_input_layout)
        port_layout.addWidget(wht_port_group)

        self.tabs.addTab(self.tab_port, "端口规则")

        layout.addWidget(self.tabs)

        # --- 底部按钮 ---
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存并应用")
        self.btn_cancel = QPushButton("❌ 取消")
        self.btn_reset = QPushButton("🔄 重置为默认")
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        # --- 事件绑定 ---
        self.btn_add_ip_black.clicked.connect(self._add_ip_black)
        self.btn_del_ip_black.clicked.connect(self._del_ip_black)
        self.btn_add_ip_white.clicked.connect(self._add_ip_white)
        self.btn_del_ip_white.clicked.connect(self._del_ip_white)

        self.btn_add_port_black.clicked.connect(self._add_port_black)
        self.btn_del_port_black.clicked.connect(self._del_port_black)
        self.btn_add_port_white.clicked.connect(self._add_port_white)
        self.btn_del_port_white.clicked.connect(self._del_port_white)

        self.btn_save.clicked.connect(self._save_and_close)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self._reset_to_default)

        # 回车键快捷添加
        self.in_ip_black.returnPressed.connect(self._add_ip_black)
        self.in_ip_white.returnPressed.connect(self._add_ip_white)

    def _load_rules_to_ui(self):
        """将 ScanFilter 中的规则加载到 UI 列表"""
        # IP 黑名单（仅自定义，不显示内置）
        self.list_ip_black.clear()
        for ip in sorted(self.filter._custom_ip_blacklist):
            self.list_ip_black.addItem(ip)

        # IP 白名单
        self.list_ip_white.clear()
        for ip in sorted(self.filter._custom_ip_whitelist):
            self.list_ip_white.addItem(ip)

        # 端口黑名单
        self.list_port_black.clear()
        for port in sorted(self.filter._custom_port_blacklist):
            self.list_port_black.addItem(str(port))

        # 端口白名单
        self.list_port_white.clear()
        for port in sorted(self.filter._custom_port_whitelist):
            self.list_port_white.addItem(str(port))

    # -------------------- IP 黑名单操作 --------------------

    def _add_ip_black(self):
        text = self.in_ip_black.text().strip()
        if not text:
            return
        # 简单校验 IP 格式
        if not self._is_valid_ip_or_cidr(text):
            QMessageBox.warning(self, "格式错误", f"无效的 IP 或 CIDR: {text}")
            return
        if text in self.filter._custom_ip_blacklist:
            QMessageBox.information(self, "提示", "该 IP 已在黑名单中")
            return
        self.filter.add_ip_blacklist(text)
        self.list_ip_black.addItem(text)
        self.in_ip_black.clear()

    def _del_ip_black(self):
        item = self.list_ip_black.currentItem()
        if item:
            ip = item.text()
            self.filter.remove_ip_blacklist(ip)
            self.list_ip_black.takeItem(self.list_ip_black.row(item))

    # -------------------- IP 白名单操作 --------------------

    def _add_ip_white(self):
        text = self.in_ip_white.text().strip()
        if not text:
            return
        if not self._is_valid_ip_or_cidr(text):
            QMessageBox.warning(self, "格式错误", f"无效的 IP 或 CIDR: {text}")
            return
        if text in self.filter._custom_ip_whitelist:
            QMessageBox.information(self, "提示", "该 IP 已在白名单中")
            return
        self.filter.add_ip_whitelist(text)
        self.list_ip_white.addItem(text)
        self.in_ip_white.clear()

    def _del_ip_white(self):
        item = self.list_ip_white.currentItem()
        if item:
            ip = item.text()
            self.filter.remove_ip_whitelist(ip)
            self.list_ip_white.takeItem(self.list_ip_white.row(item))

    # -------------------- 端口黑名单操作 --------------------

    def _add_port_black(self):
        port = self.in_port_black.value()
        if port in self.filter._custom_port_blacklist:
            QMessageBox.information(self, "提示", f"端口 {port} 已在黑名单中")
            return
        self.filter.add_port_blacklist(port)
        self.list_port_black.addItem(str(port))

    def _del_port_black(self):
        item = self.list_port_black.currentItem()
        if item:
            port = int(item.text())
            self.filter.remove_port_blacklist(port)
            self.list_port_black.takeItem(self.list_port_black.row(item))

    # -------------------- 端口白名单操作 --------------------

    def _add_port_white(self):
        port = self.in_port_white.value()
        if port in self.filter._custom_port_whitelist:
            QMessageBox.information(self, "提示", f"端口 {port} 已在白名单中")
            return
        self.filter.add_port_whitelist(port)
        self.list_port_white.addItem(str(port))

    def _del_port_white(self):
        item = self.list_port_white.currentItem()
        if item:
            port = int(item.text())
            self.filter.remove_port_whitelist(port)
            self.list_port_white.takeItem(self.list_port_white.row(item))

    # -------------------- 底部按钮 --------------------

    def _save_and_close(self):
        """保存规则到文件并关闭对话框"""
        try:
            self.filter.save_config()
            self.rules_changed.emit(self.filter)
            QMessageBox.information(self, "保存成功", "规则已保存并生效")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _reset_to_default(self):
        """重置为默认（清空所有自定义规则，保留内置）"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要清空所有自定义规则吗？\n内置规则（系统保留地址/端口）将保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.filter.clear_custom_rules()
            self._load_rules_to_ui()

    @staticmethod
    def _is_valid_ip_or_cidr(text: str) -> bool:
        """简单校验 IP 或 CIDR 格式"""
        import re
        ip_pattern = re.compile(
            r"^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$"
        )
        if not ip_pattern.match(text):
            return False
        # 校验每段 0-255
        parts = text.split("/")[0].split(".")
        return all(0 <= int(p) <= 255 for p in parts)


# ============================================================
# 便捷函数：弹出对话框
# ============================================================

def show_filter_dialog(
    filter_instance: Optional[ScanFilter] = None,
    parent=None,
    on_rules_changed: Optional[Callable] = None,
) -> Optional[ScanFilter]:
    """
    弹出黑白名单管理对话框

    Args:
        filter_instance: 当前 ScanFilter 实例，None 则创建新的
        parent: 父窗口
        on_rules_changed: 规则变更回调函数，接收 ScanFilter 实例

    Returns:
        用户确认后返回 ScanFilter 实例，取消则返回 None
    """
    dialog = FilterDialog(filter_instance, parent)
    if on_rules_changed:
        dialog.rules_changed.connect(on_rules_changed)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.filter
    return None
