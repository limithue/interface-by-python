# 代码生成指令任务书

## 一、任务基本信息
| 项目 | 内容 |
|------|------|
| 任务名称 | gui.py 界面层补丁 — QCheckBox 语义升级与配置持久化重构 |
| 执行对象 | Kimi AI 编程助手 |
| 生成目标 | gui.py 单份可直接运行的完整源码（含内嵌全模块） |
| 依据资料 | 用户截图指示、原始 gui.py 源码（高内聚低耦合重构版）、实训计划书功能模块字典 |
| 任务性质 | 代码重构、控件语义升级、配置持久化增强、状态锁定补全 |
| 使用场景 | 授权内网安全巡检、端口开放检测、教学演示、实训课程交付 |

---

## 二、代码生成总体目标
基于原始 gui.py 源码（含 models / parsers / scanner / thread_mgr / exporters / worker / gui 七大内嵌模块）及用户三项明确答复，生成升级后的可直接运行源码，满足以下核心指标：

1. **控件语义精准**："跳过离线IP" 由 `QPushButton(setCheckable)` 升级为原生 `QCheckBox`，消除按压态歧义
2. **配置持久化零耦合**：新增 `ConfigManager` 配置管理器，JSON 持久化，GUI 层零文件 IO 操作
3. **扫描状态全锁定**：扫描期间禁用所有参数输入控件（含 `QCheckBox`），防止误触与状态不一致
4. **生命周期闭环**：启动时从 `scanner_config.json` 加载初始状态，退出时自动保存，含窗口几何恢复
5. **核心接口零侵入**：`skip_offline` 逻辑仍通过 `ScanConfig` 数据契约传递，不修改 `PortScanner` / `ScanWorker` 接口
6. **低耦合高内聚**：配置层独立可测试，表现层零业务逻辑，控制层信号驱动

---

## 三、逐模块生成指令

### 模块一：ConfigManager（新增配置管理层）
#### 3.1.1 生成指令
新增配置持久化管理类，职责为封装 JSON 配置的读写、默认值回退与异常静默处理，禁止包含任何 GUI / 网络 / 线程依赖。

#### 3.1.2 必须包含的内容
| 配置项 | 类型 | 规格说明 |
|--------|------|----------|
| DEFAULTS | dict | 默认配置字典，含 `skip_offline` / `threads` / `timeout` / `delay` / `protocol` / `target` / `port` / `window_geometry` |
| load() | 方法 | 从 `scanner_config.json` 加载；文件缺失或损坏时回退到 DEFAULTS |
| save() | 方法 | 原子化写入 JSON；无写权限时静默处理，不阻塞 GUI 退出 |
| get(key, default) | 方法 | 读取配置值 |
| set(key, value) | 方法 | 内存级写入，不立即刷盘 |

#### 3.1.3 约束条件
- 仅依赖 `os` / `json` 标准库，零 PyQt / socket / threading 导入
- 默认值策略为合并覆盖：`{**DEFAULTS, **loaded}`，确保向后兼容
- 窗口几何存储使用 `saveGeometry().toHex()` 原生序列化
- 类实例与 `MainWindow` 生命周期绑定，但逻辑完全独立

---

### 模块二：MainWindow._init_ui（表现层布局）
#### 3.2.1 生成指令
重构扫描参数输入区，将 "跳过离线IP" 控件替换为 `QCheckBox`，保持原有布局流与信号绑定方式。

#### 3.2.2 必须实现的变更
| 原实现 | 新实现 | 规格说明 |
|--------|--------|----------|
| `QPushButton("跳过离线IP", checkable=True)` | `QCheckBox("跳过离线IP")` | 原生复选框，视觉语义一致，支持 `stateChanged` 信号 |
| 硬编码默认值 | `ConfigManager` 驱动 | 所有输入控件初始值由 `_load_config_to_ui()` 注入 |
| 无实时同步 | `stateChanged` 绑定 | `chk_ping.stateChanged` 连接 `config_mgr.set`，内存实时更新 |

#### 3.2.3 约束条件
- `QCheckBox` 必须添加 `spacing: 6px` 与 `indicator` 样式，保持与整体风格一致
- 不得改变 `ScanConfig` 的构造方式，`skip_offline` 仍通过 `isChecked()` 获取布尔值
- 布局位置保持原 `h3` 水平流末尾，右侧接 `addStretch()`

---

### 模块三：MainWindow._load_config_to_ui（配置映射层）
#### 3.3.1 生成指令
实现配置到 UI 控件的单向映射方法，在 `__init__` 末尾调用，完成启动状态恢复。

#### 3.3.2 必须恢复的状态
| 控件 | 配置键 | 恢复方式 |
|------|--------|----------|
| `chk_ping` | `skip_offline` | `setChecked(bool)` |
| `sb_threads` | `threads` | `setValue(int)` |
| `sb_timeout` | `timeout` | `setValue(int)` |
| `sb_delay` | `delay` | `setValue(int)` |
| `cb_proto` | `protocol` | `setCurrentIndex(findText(str))` |
| `in_target` | `target` | `setText(str)` |
| `in_port` | `port` | `setText(str)` |
| `MainWindow` 几何 | `window_geometry` | `restoreGeometry(bytes.fromhex(str))` |

#### 3.3.3 约束条件
- 仅依赖 `ConfigManager.get`，不触及文件系统
- 配置键缺失时回退到 `AppConfig` 静态常量或硬编码安全默认值
- 窗口几何为可选恢复项，值为空时跳过

---

### 模块四：MainWindow._save_config_from_ui（配置回写层）
#### 3.4.1 生成指令
实现 UI 状态到配置管理器的回写方法，在 `closeEvent()` 中调用，完成退出持久化。

#### 3.4.2 必须保存的状态
| 控件 | 配置键 | 读取方式 |
|------|--------|----------|
| `chk_ping` | `skip_offline` | `isChecked()` |
| `sb_threads` | `threads` | `value()` |
| `sb_timeout` | `timeout` | `value()` |
| `sb_delay` | `delay` | `value()` |
| `cb_proto` | `protocol` | `currentText()` |
| `in_target` | `target` | `text()` |
| `in_port` | `port` | `text()` |
| `MainWindow` 几何 | `window_geometry` | `saveGeometry().toHex().data().decode()` |

#### 3.4.3 约束条件
- 收集完所有控件值后，统一调用 `config_mgr.save()` 刷盘
- 异常由 `ConfigManager` 内部静默消化，GUI 层无 try-catch 包裹

---

### 模块五：MainWindow._set_controls_running（状态锁定层）
#### 3.5.1 生成指令
扩展扫描状态切换方法，将 `chk_ping` 纳入禁用/启用范围，确保扫描期间参数不可变更。

#### 3.5.2 锁定控件清单
```python
for w in [self.in_target, self.in_port, self.cb_proto,
          self.sb_threads, self.sb_timeout, self.sb_delay,
          self.chk_ping]:  # ← 新增
    w.setEnabled(not running)
```

#### 3.5.3 约束条件
- 扫描启动时（`running=True`）全部禁用，扫描结束后（`running=False`）统一恢复
- 按钮状态（`btn_start` / `btn_stop` / `btn_pause`）保持原有逻辑不变

---

### 模块六：MainWindow.closeEvent（生命周期层）
#### 3.6.1 生成指令
重写窗口关闭事件，优先保存配置，再处理运行中扫描线程的终止确认。

#### 3.6.2 执行顺序
1. 调用 `_save_config_from_ui()` 持久化当前配置
2. 若扫描线程运行中，弹出 `QMessageBox.Question` 确认退出
3. 用户确认后调用 `worker.stop()` 与 `worker.wait(2000)`
4. 接受或忽略关闭事件

#### 3.6.3 约束条件
- 配置保存必须在确认对话框之前执行，确保无论用户是否取消，已修改状态均已落盘
- 线程终止超时设为 2 秒，避免无限阻塞

---

## 四、技术约束与规范

### 4.1 语言与环境约束
- Python 3.8+
- PyQt6 为唯一外部依赖（实训计划书指定）
- 配置管理器仅使用 `os` / `json` 标准库

### 4.2 代码风格约束
- 函数/变量：小写 + 下划线
- 类：大驼峰
- 常量：全大写
- 必须加 docstring 与注释，说明低耦合设计意图

### 4.3 架构约束
- **表现层零业务逻辑**：`MainWindow` 不直接创建 socket、不操作文件、不管理线程池
- **配置层零 UI 依赖**：`ConfigManager` 不导入 PyQt6，可独立单元测试
- **控制层信号驱动**：`ScanWorker` 通过 `pyqtSignal` 与 GUI 通信，禁止直接回调
- **数据契约不变**：`ScanConfig` / `ScanResult` / `PortState` 枚举保持冻结数据类设计

---

## 五、质量标准

### 5.1 功能质量
- 导入无异常（`python gui.py` 可直接语法检查通过）
- `QCheckBox` 勾选/取消状态在重启后正确恢复
- 扫描期间 `QCheckBox` 被禁用，结束后恢复
- 删除 `scanner_config.json` 后启动，加载默认值无报错
- 窗口大小与位置在重启后恢复

### 5.2 交互质量
- 控件视觉与功能一致，状态切换正常（符合用户截图验收标准）
- 配置实时同步无延迟，退出保存无弹窗干扰
- 扫描中断后参数控件立即恢复可编辑状态

### 5.3 代码质量
- 无裸 `except:`
- 无死代码
- 无魔法数（常量集中至 `AppConfig` 或 `ConfigManager.DEFAULTS`）
- 线程安全（`ScanWorker` 的 `_stat_lock` 保持原有设计）
- 套接字正常关闭（`PortScanner` 的 `with` 语句与 `finally` 保持）

---

## 六、交付物清单
| 编号 | 交付物 | 类型 | 说明 |
|------|--------|------|------|
| 1 | gui.py | 源码 | 完整单文件源码（含内嵌 models / parsers / scanner / thread_mgr / exporters / worker / gui / config_mgr 八大模块） |
| 2 | 代码开发日志 | 文档 | 需求确认、变更清单、设计决策、测试建议 |
| 3 | 本指令任务书 | 文档 | 规格、约束、标准、验收依据 |

---

## 七、执行规范
1. 严格依据用户三项答复与原始 gui.py 源码升级，不随意增删功能模块
2. 保持 PyQt6 轻量级 GUI，无额外第三方依赖（除实训计划书已指定的 PyQt6 / pyinstaller）
3. 仅做端口检测界面交互，不实现攻击、破解功能
4. 输出正式、清晰，可直接作为实训课程作业/项目交付
5. 完成后必须验证：导入检查、QCheckBox 状态恢复、扫描锁定、配置持久化、权限降级提示

---
文档版本：v1.0  
编制日期：2026-06-02  
依据标准：用户截图指示、原始 gui.py 源码（高内聚低耦合重构版）、《基于Python的Windows自用端口扫描工具开发实训计划书》
