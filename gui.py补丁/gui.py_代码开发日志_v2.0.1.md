# 代码开发日志

**项目**：基于Python的Windows自用端口扫描工具  
**模块**：`gui.py` 界面层补丁  
**日期**：2026-06-02  
**版本**：v2.0.0 → v2.0.1（配置持久化与控件语义升级）

---

## 一、需求来源

根据实训计划书功能模块字典及用户截图指示，需将 GUI 中 **"跳过离线IP"** 控件由 `QPushButton(setCheckable=True)` 替换为原生 `QCheckBox`，并同步完成配置持久化与扫描状态锁定。

---

## 二、需求确认（三问三答）

| 序号 | 问题 | 用户答复 | 设计影响 |
|------|------|---------|---------|
| 1 | 现有代码结构是否提供？ | 用户粘贴完整 `gui.py` 源码（单文件 500+ 行，含 models / parsers / scanner / thread_mgr / exporters / worker / gui 全模块） | 基于现有代码做最小侵入式补丁，不破坏已有模块化边界 |
| 2 | 跳过离线IP的扫描逻辑位置？ | 逻辑已封装在 `core/port_scan.py`，仅需在 `gui.py` 传递勾选状态参数，**无需修改核心接口** | 保持 `ScanConfig.skip_offline` 字段不变，GUI 仅负责数据传递 |
| 3 | 初始状态与持久化要求？ | 初始状态从 `config.py` 加载；扫描时禁用控件；**需补充配置持久化逻辑** | 新增独立 `ConfigManager` 模块，实现 JSON 持久化与默认值回退 |

---

## 三、变更清单

### 3.1 控件替换（视觉与语义层）
- **原实现**：`QPushButton("跳过离线IP", checkable=True, checked=True)`
- **新实现**：`QCheckBox("跳过离线IP")`
- **理由**：`QCheckBox` 更符合布尔选项的视觉心智模型，原生支持 `stateChanged` 信号，去除 `QPushButton` 的按压态歧义。

### 3.2 新增配置管理层（高内聚低耦合）
- **新增类**：`ConfigManager`
- **职责**：
  - 封装 `scanner_config.json` 的读写逻辑
  - 提供默认值回退机制（`DEFAULTS` 字典）
  - 异常静默处理（无写权限时不阻塞 GUI 退出）
- **耦合度**：零依赖 PyQt / socket / threading，可独立单元测试。

### 3.3 配置持久化字段
新增持久化键：
```json
{
  "skip_offline": true,
  "threads": 10,
  "timeout": 2,
  "delay": 0,
  "protocol": "tcp",
  "target": "127.0.0.1,192.168.1.1-10",
  "port": "common",
  "window_geometry": "..."
}
```

### 3.4 生命周期绑定
- **启动加载**：`MainWindow._load_config_to_ui()` 在 `__init__` 末尾调用，恢复所有输入控件状态及窗口几何。
- **实时同步**：`chk_ping.stateChanged` 连接 `config_mgr.set`，内存实时更新。
- **退出保存**：`closeEvent()` 调用 `_save_config_from_ui()`，统一刷盘。

### 3.5 扫描状态锁定
- **修改方法**：`_set_controls_running(running: bool)`
- **锁定范围**：扫描期间禁用 `in_target`, `in_port`, `cb_proto`, `sb_threads`, `sb_timeout`, `sb_delay`, **`chk_ping`**
- **恢复时机**：扫描完成（正常/异常/终止）后统一恢复。

---

## 四、设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 配置存储格式 | JSON | 人类可读、Python 标准库原生支持、无需额外依赖 |
| 写盘时机 | 退出时统一保存 | 减少磁盘 IO，避免扫描过程中频繁写配置 |
| 默认值策略 | 合并覆盖（`{**DEFAULTS, **loaded}`） | 新增配置键时向后兼容旧文件 |
| 窗口几何存储 | `saveGeometry().toHex()` | PyQt 原生序列化，跨平台可靠 |
| 配置管理器位置 | 与 `MainWindow` 生命周期绑定 | 单例模式足够，无需全局变量或依赖注入框架 |

---

## 五、代码结构验证（低耦合高内聚）

```
gui.py（表现层）
  ├─ 依赖 ConfigManager.get/set（配置契约）
  ├─ 依赖 ScanConfig（数据契约）
  ├─ 依赖 ScanWorker（控制层信号）
  └─ 零文件 IO / 零网络 / 零业务逻辑

ConfigManager（配置层）
  ├─ 仅依赖 os/json
  ├─ 不导入 PyQt / socket / threading
  └─ 可独立测试

PortScanner（核心层）
  ├─ 接收 ScanConfig.skip_offline（布尔值）
  └─ 不感知 GUI 控件类型（Button 或 CheckBox 无关）
```

---

## 六、测试建议

1. **功能测试**：启动程序 → 勾选/取消 `QCheckBox` → 退出 → 重启 → 验证状态恢复。
2. **边界测试**：删除 `scanner_config.json` → 启动 → 验证默认值加载正常。
3. **并发测试**：扫描过程中点击 `chk_ping`，验证控件被禁用；扫描结束后验证恢复。
4. **权限测试**：将 `scanner_config.json` 设为只读 → 退出 → 验证无异常弹窗。

---

## 七、后续可拓展

- 将 `ConfigManager` 迁移至独立 `config.py`，供 CLI 模式复用。
- 增加配置版本号字段，支持未来配置格式迁移。
- 为 `QCheckBox` 增加快捷键（如 `Alt+S`）提升无障碍体验。

---

**日志撰写人**：AI 开发助手  
**关联文档**：《基于Python的Windows自用端口扫描工具开发实训计划书》第 3 周任务（GUI 开发 + 代码深度优化）
