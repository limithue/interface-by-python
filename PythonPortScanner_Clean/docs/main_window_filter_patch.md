#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui/main_window_filter_patch.py —— 主窗口集成黑白名单的补丁说明
===============================================================

本文件说明如何在现有 main_window.py 中集成黑白名单过滤功能。
按以下步骤修改即可，无需重构现有代码结构。

【修改位置 1】导入区（顶部）
--------------------------------
在原有导入后添加：

    from core.filter import ScanFilter, apply_filter
    from gui.filter_dialog import show_filter_dialog

【修改位置 2】MainWindow.__init__() 末尾
----------------------------------------
在 self._load_config_to_ui() 后添加过滤器初始化：

    # 初始化扫描过滤器（从配置文件加载）
    self.scan_filter = ScanFilter.load_from_config()

【修改位置 3】MainWindow._init_ui() 控制按钮区
----------------------------------------------
在导出按钮后添加"规则管理"按钮：

    self.btn_filter = QPushButton("⚙ 扫描规则")
    ctrl_layout.addWidget(self.btn_filter)

并在事件绑定区添加：

    self.btn_filter.clicked.connect(self.open_filter_dialog)

【修改位置 4】新增方法：打开规则对话框
------------------------------------
在 MainWindow 类中添加：

    def open_filter_dialog(self):
        """打开黑白名单管理对话框"""
        def on_rules_changed(new_filter):
            self.scan_filter = new_filter
            self.log("[FILTER] 扫描规则已更新并生效")

        show_filter_dialog(
            filter_instance=self.scan_filter,
            parent=self,
            on_rules_changed=on_rules_changed,
        )

【修改位置 5】MainWindow.start_scan() 扫描启动前
-----------------------------------------------
在解析 targets 和 ports 后、创建 ScanWorker 前，插入过滤逻辑：

        # 应用黑白名单过滤
        filter_result = self.scan_filter.apply(
            frozenset(targets), frozenset(ports)
        )
        if filter_result.blocked_count > 0:
            self.log(filter_result.summary())

        targets = list(filter_result.allowed_targets)
        ports = list(filter_result.allowed_ports)

        if not targets or not ports:
            QMessageBox.warning(self, "过滤结果", "所有目标/端口均被规则过滤，无有效扫描任务")
            return

【修改位置 6】MainWindow.closeEvent() 退出保存
---------------------------------------------
在 _save_config_from_ui() 后添加规则保存：

    # 保存扫描规则
    self.scan_filter.save_config()

【完整集成后的扫描流程】
-----------------------
    用户输入目标/端口
        ↓
    IPParser.resolve_targets() / PortParser.resolve_ports()
        ↓
    ScanFilter.apply() —— 过滤黑名单，优先白名单
        ↓
    展示过滤日志（如有）
        ↓
    ScanWorker(targets, ports, config) —— 仅扫描允许的目标
        ↓
    结果展示 → 导出报告

【GUI 界面效果】
---------------
主窗口新增 [⚙ 扫描规则] 按钮，点击弹出对话框：

┌─────────────────────────────────────────┐
│  扫描规则管理 — 黑白名单                  │
│  ─────────────────────────────────────  │
│  [IP 规则] [端口规则]                    │
│  ┌─ IP 黑名单（禁止扫描）────────────┐  │
│  │  192.168.1.1                       │  │
│  │  10.0.0.0/8                        │  │
│  └────────────────────────────────────┘  │
│  [输入 IP/CIDR        ] [添加] [删除选中] │
│  ┌─ IP 白名单（明确允许）────────────┐  │
│  │  192.168.1.10                      │  │
│  └────────────────────────────────────┘  │
│  [输入 IP/CIDR        ] [添加] [删除选中] │
│                                         │
│  [🔄 重置为默认]  [❌ 取消] [💾 保存并应用]│
└─────────────────────────────────────────┘

【技术亮点】
-----------
1. 白名单优先：即使 IP 同时命中黑白名单，白名单胜出放行
2. 内置兜底：系统保留地址/端口始终受保护，不可删除
3. 实时生效：保存后立即应用到下一次扫描
4. 持久化：规则保存到 scan_rules.json，重启后自动加载
5. 低耦合：FilterDialog 不直接操作 MainWindow，通过信号回调
"""
