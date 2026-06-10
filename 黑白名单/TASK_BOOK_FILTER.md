# 代码生成指令任务书

## 一、任务基本信息
| 项目 | 内容 |
|------|------|
| 任务名称 | 扫描目标黑白名单过滤模块开发 — 高内聚低耦合架构升级 |
| 执行对象 | Kimi AI 编程助手 |
| 生成目标 | core/filter.py、gui/filter_dialog.py、gui/main_window_filter_patch.py |
| 依据资料 | 《基于Python的Windows自用端口扫描工具开发实训计划书》功能模块字典、用户三项架构决策 |
| 任务性质 | 代码重构、安全策略增强、配置持久化、GUI 交互升级 |
| 使用场景 | 授权内网安全巡检、防止误操作系统保留地址/端口、自定义扫描规则管理 |

---

## 二、代码生成总体目标

基于实训计划书"拓展功能需求"中"支持 IP / 端口黑白名单、线程数、发包间隔自定义"的要求，以及用户三项明确架构决策（解析后过滤、白名单优先、内置+外部配置结合），生成可直接集成到现有项目的过滤模块源码，满足以下核心指标：

1. **高内聚**：所有过滤逻辑集中在 `core/filter.py`，不泄露到 GUI/扫描器
2. **低耦合**：GUI 层仅依赖 `ScanFilter` 和 `FilterResult`，不感知内部规则存储结构
3. **白名单优先**：命中白名单即放行，即使同时命中黑名单
4. **内置兜底**：系统保留地址/端口硬编码保护，不可删除
5. **配置持久化**：用户自定义规则保存到 JSON，重启自动加载
6. **动态管理**：GUI 支持运行时增删规则，实时生效
7. **不可变返回**：过滤结果使用 FrozenSet 与 frozen=True dataclass，线程安全
8. **过滤反馈**：返回详细过滤日志（被过滤项、原因、规则来源），供 GUI 展示

---

## 三、逐文件生成指令

### 文件一：core/filter.py（过滤引擎层）

#### 3.1.1 生成指令
生成扫描目标黑白名单过滤核心模块，职责为在解析后、扫描前对目标 IP 和端口进行过滤。支持黑名单（默认禁止）和白名单（明确许可）两种模式，白名单优先级高于黑名单。

#### 3.1.2 必须包含的内容

| 名称 | 类型 | 功能规格 | 异常处理 |
|------|------|----------|----------|
| `_DEFAULT_IP_BLACKLIST` | 常量 | 系统保留 IP 地址集合（广播、组播、保留地址） | — |
| `_DEFAULT_PORT_BLACKLIST` | 常量 | 系统保留端口集合（Echo、Chargen、RPC 等） | — |
| `FilterLog` | dataclass(frozen=True) | 单条过滤记录：item, item_type, reason, rule_source | 不可变 |
| `FilterResult` | dataclass(frozen=True) | 过滤结果契约：allowed_targets, allowed_ports, blocked_logs, total_input_* | 不可变 |
| `RuleLoader` | 类 | JSON 规则文件加载/保存，与 ScanFilter 解耦 | 文件异常静默处理 |
| `ScanFilter` | 类 | 核心过滤引擎 | 透传异常 |
| `__init__` | 方法 | 初始化内置规则 + 自定义规则 | 实例隔离 |
| `load_from_config` | 类方法 | 从 JSON 加载规则创建实例 | 文件缺失返回空规则 |
| `add_ip_blacklist` | 方法 | 动态添加 IP 黑名单 | — |
| `remove_ip_blacklist` | 方法 | 移除 IP 黑名单 | — |
| `add_port_blacklist` | 方法 | 动态添加端口黑名单 | — |
| `remove_port_blacklist` | 方法 | 移除端口黑名单 | — |
| `add_ip_whitelist` | 方法 | 动态添加 IP 白名单 | — |
| `remove_ip_whitelist` | 方法 | 移除 IP 白名单 | — |
| `add_port_whitelist` | 方法 | 动态添加端口白名单 | — |
| `remove_port_whitelist` | 方法 | 移除端口白名单 | — |
| `clear_custom_rules` | 方法 | 清空所有自定义规则（保留内置） | — |
| `apply` | 方法 | 执行过滤，返回 FilterResult | — |
| `save_config` | 方法 | 保存自定义规则到 JSON | 异常静默处理 |
| `apply_filter` | 函数 | 便捷过滤函数，一键加载配置并执行 | — |

#### 3.1.3 过滤优先级规则

**判断顺序（从高到低）：**
1. **白名单命中** → 直接放行（最高优先级）
2. **内置黑名单命中** → 拒绝（系统保留地址/端口，不可覆盖）
3. **组播/广播/保留地址检测** → 拒绝（通过 ipaddress 库动态检测）
4. **自定义黑名单命中** → 拒绝
5. **以上均未命中** → 放行

#### 3.1.4 内置默认黑名单规格

**系统保留 IP 地址：**
- `255.255.255.255` — 有限广播地址
- `224.0.0.0` ~ `239.255.255.255` — 组播地址段（224.0.0.0/4）
- `169.254.255.255` — 链路本地广播
- `0.0.0.0` — 未指定地址

**系统保留端口：**
- `0` — 保留
- `7` — Echo（反射攻击风险）
- `9` — Discard
- `13` — Daytime
- `17` — Quote of the Day
- `19` — Chargen（放大攻击风险）
- `37` — Time
- `111` — RPCbind（历史漏洞）
- `512` ~ `515` — rlogin 系列（exec/login/shell/printer，高风险）
- `540` — uucp

#### 3.1.5 约束条件
- 仅使用 Python 标准库（ipaddress, json, os, typing, dataclasses）
- 内置规则为 frozenset，不可修改
- 自定义规则为 set，支持动态增删
- 过滤操作不修改输入集合，返回新对象
- 所有返回集合为 FrozenSet，数据类为 frozen=True
- 异常捕获指定具体类型，禁止裸 except

---

### 文件二：gui/filter_dialog.py（规则管理 GUI 层）

#### 3.2.1 生成指令
生成黑白名单管理对话框，职责为提供可视化界面管理黑白名单规则。支持添加/删除 IP 和端口规则，实时同步到 ScanFilter 实例并持久化到 JSON。与 MainWindow 通过信号通信，零直接耦合。

#### 3.2.2 必须包含的内容

| 名称 | 类型 | 功能规格 |
|------|------|----------|
| `FilterDialog` | QDialog 子类 | 黑白名单管理对话框 |
| `rules_changed` | pyqtSignal | 规则变更信号，发射 ScanFilter 实例 |
| `__init__` | 方法 | 初始化对话框，持有 ScanFilter 实例副本 |
| `_init_ui` | 方法 | 构建界面：Tab 切换（IP规则/端口规则）、黑名单/白名单列表、输入框、按钮 |
| `_load_rules_to_ui` | 方法 | 将 ScanFilter 规则加载到 QListWidget |
| `_add_ip_black` | 方法 | 添加 IP 黑名单（含格式校验） |
| `_del_ip_black` | 方法 | 删除选中的 IP 黑名单项 |
| `_add_ip_white` | 方法 | 添加 IP 白名单（含格式校验） |
| `_del_ip_white` | 方法 | 删除选中的 IP 白名单项 |
| `_add_port_black` | 方法 | 添加端口黑名单 |
| `_del_port_black` | 方法 | 删除选中的端口黑名单项 |
| `_add_port_white` | 方法 | 添加端口白名单 |
| `_del_port_white` | 方法 | 删除选中的端口白名单项 |
| `_save_and_close` | 方法 | 保存规则到 JSON 并关闭对话框 |
| `_reset_to_default` | 方法 | 清空所有自定义规则（保留内置），需二次确认 |
| `_is_valid_ip_or_cidr` | 静态方法 | IP/CIDR 格式校验正则 |
| `show_filter_dialog` | 函数 | 便捷函数，弹出对话框并返回结果 |

#### 3.2.3 界面布局规格

```
┌─────────────────────────────────────────┐
│  扫描规则管理 — 黑白名单                  │
│  ─────────────────────────────────────  │
│  [IP 规则] [端口规则]                    │
│  ┌─ IP 黑名单（禁止扫描）────────────┐  │
│  │  ▢ 192.168.1.1                     │  │
│  │  ▢ 10.0.0.0/8                      │  │
│  └────────────────────────────────────┘  │
│  [输入 IP/CIDR        ] [添加] [删除选中] │
│  ┌─ IP 白名单（明确允许）────────────┐  │
│  │  ▢ 192.168.1.10                    │  │
│  └────────────────────────────────────┘  │
│  [输入 IP/CIDR        ] [添加] [删除选中] │
│                                         │
│  [🔄 重置为默认]  [❌ 取消] [💾 保存并应用]│
└─────────────────────────────────────────┘
```

#### 3.2.4 约束条件
- 仅依赖 PyQt6 和 core.filter
- 持有 ScanFilter 实例副本，不直接操作外部状态
- 通过 `rules_changed` 信号通知调用方
- 输入校验失败时弹出 QMessageBox 警告
- 重置操作需二次确认（QMessageBox.question）
- 回车键快捷添加（QLineEdit.returnPressed）

---

### 文件三：gui/main_window_filter_patch.py（集成补丁说明）

#### 3.3.1 生成指令
生成主窗口集成黑白名单过滤功能的补丁说明文档，职责为指导开发者在现有 main_window.py 中接入过滤模块，无需重构现有代码结构。

#### 3.3.2 必须包含的内容

| 修改位置 | 操作 | 代码片段 |
|---------|------|---------|
| 导入区 | 新增导入 | `from core.filter import ScanFilter, apply_filter`<br>`from gui.filter_dialog import show_filter_dialog` |
| `__init__` | 初始化过滤器 | `self.scan_filter = ScanFilter.load_from_config()` |
| `_init_ui` | 添加按钮 | `self.btn_filter = QPushButton("⚙ 扫描规则")` |
| 事件绑定 | 绑定点击 | `self.btn_filter.clicked.connect(self.open_filter_dialog)` |
| 新增方法 | 打开对话框 | `def open_filter_dialog(self): ...` |
| `start_scan` | 插入过滤 | `filter_result = self.scan_filter.apply(...)` |
| `closeEvent` | 保存规则 | `self.scan_filter.save_config()` |

#### 3.3.3 集成后扫描流程

```
用户输入目标/端口
    ↓
IPParser.resolve_targets() / PortParser.resolve_ports()
    ↓
ScanFilter.apply(frozenset(targets), frozenset(ports))
    ↓
展示过滤日志（如有被过滤项）
    ↓
ScanWorker(allowed_targets, allowed_ports, config)
    ↓
结果展示 → 导出报告
```

---

## 四、技术约束与规范

### 4.1 语言与环境约束
| 约束项 | 要求 |
|--------|------|
| Python 版本 | 3.8+ |
| 第三方依赖 | 禁止（filter.py 仅标准库；filter_dialog.py 仅 PyQt6） |
| 运行权限 | 普通用户权限 |

### 4.2 代码风格约束
| 项 | 规范 |
|----|------|
| 函数/变量 | 小写+下划线 |
| 类 | 大驼峰 |
| 常量 | 全大写 |
| 私有方法 | 单下划线前缀 |
| 文档字符串 | 类与公共方法必须包含 |
| 类型注解 | 完整（参数+返回值） |

### 4.3 架构约束
| 约束项 | 要求 |
|--------|------|
| 模块依赖方向 | filter.py → 标准库；filter_dialog.py → PyQt6 + filter.py；main_window.py → filter_dialog.py（单向，无循环） |
| 对外暴露 | 仅 `ScanFilter`、`FilterResult`、`FilterLog`、`show_filter_dialog` |
| 配置注入 | 实例级，禁止修改类属性 |
| 返回类型 | 不可变集合（FrozenSet）与不可变数据类（frozen=True） |
| 异常传播 | 底层消化具体异常，向上仅抛标准异常 |

---

## 五、质量标准

### 5.1 功能质量
| 验收项 | 通过标准 |
|--------|----------|
| 导入无异常 | `python -c "from core.filter import ScanFilter"` 正常退出 |
| 内置黑名单 | 组播地址(224.0.0.1)被过滤，普通地址(192.168.1.1)放行 |
| 白名单优先 | 同时命中黑白名单的 IP 被放行 |
| 配置加载 | 从 scan_rules.json 加载自定义规则并生效 |
| 配置保存 | 修改规则后保存到 JSON，重启后恢复 |
| 过滤反馈 | 返回 FilterResult 包含被过滤项的详细日志 |
| GUI 弹窗 | FilterDialog 正常显示，增删规则实时更新列表 |

### 5.2 代码质量
| 验收项 | 通过标准 |
|--------|----------|
| 编译通过 | py_compile 所有模块无语法错误 |
| 无循环导入 | `import core.filter` 不触发 ImportError |
| 类型注解 | mypy 检查无 error 级别提示 |
| 文档覆盖 | 类 + 公共方法 docstring 覆盖率 100% |
| 无裸 except | 所有异常捕获指定具体类型 |
| 无魔法数 | 端口范围、任务上限等使用命名常量 |

### 5.3 测试质量
| 验收项 | 通过标准 |
|--------|----------|
| 测试通过率 | `python core/filter.py` 4/4 项测试通过 |
| 测试独立性 | 无执行顺序依赖 |
| 边界覆盖 | 内置规则、自定义规则、白名单优先、配置加载 |

---

## 六、交付物清单
| 编号 | 交付物 | 类型 | 路径 | 代码行数 | 说明 |
|------|--------|------|------|----------|------|
| 1 | filter.py | 源码 | core/filter.py | ~550 | 过滤引擎层 |
| 2 | filter_dialog.py | 源码 | gui/filter_dialog.py | ~380 | 规则管理 GUI |
| 3 | main_window_filter_patch.py | 文档 | gui/main_window_filter_patch.py | ~120 | 集成补丁说明 |
| 4 | 本指令任务书 | 文档 | TASK_BOOK_FILTER.md | — | 规格、约束、标准 |

---

## 七、执行规范
1. 严格依据用户三项架构决策（解析后过滤/白名单优先/内置+外部配置）逐项实现
2. 保持与现有扫描引擎（scanner.py）、GUI 界面（main_window.py）的接口兼容
3. 仅做目标过滤，不实现扫描、攻击、破解功能
4. 输出正式、清晰，可直接用于实训报告代码章节
5. 完成后必须验证：编译通过、4 项测试全通过、无循环导入

---

## 八、架构决策记录（ADR）

### ADR-001：解析后过滤
- **决策**：在 IPParser/PortParser 解析完成后执行过滤
- **理由**：与解析逻辑解耦，可独立测试；能处理 CIDR 展开后的精确 IP 列表
- **影响**：需要先完成解析才能过滤，大网段解析可能消耗内存（已有 100,000 任务量上限防护）

### ADR-002：白名单优先
- **决策**：白名单优先级高于黑名单，命中白名单即放行
- **理由**：符合安全领域"默认拒绝、明确允许"的最佳实践
- **影响**：用户可能误将危险地址加入白名单，需配合合规提示

### ADR-003：内置+外部分离
- **决策**：内置规则硬编码（不可删除），用户规则外部 JSON 存储（可增删）
- **理由**：内置规则作为安全底线始终生效；用户规则灵活可配置
- **影响**：用户无法覆盖内置规则（设计意图，防止误操作）

### ADR-004：不可变返回类型
- **决策**：FilterResult 使用 frozen=True dataclass，allowed_targets/allowed_ports 使用 FrozenSet
- **理由**：多线程环境下防止结果对象被意外修改
- **影响**：下游无法原地修改结果，需创建新对象

### ADR-005：GUI 与引擎解耦
- **决策**：FilterDialog 持有 ScanFilter 实例副本，通过 rules_changed 信号通知 MainWindow
- **理由**：FilterDialog 可独立测试、复用；不直接操作 MainWindow 状态
- **影响**：需要信号/回调机制，增加少量代码复杂度

---

## 九、合规声明

本模块仅限授权内网安全测试使用。黑白名单过滤旨在防止误操作系统保留地址/端口，降低扫描行为的合规风险。过滤功能本身不构成对扫描行为的限制或鼓励，用户仍需确保所有扫描目标均已获得明确授权。

---

**文档版本**: v1.0  
**编制日期**: 2026-06-09  
**依据标准**: 《基于Python的Windows自用端口扫描工具开发实训计划书》、用户三项架构决策（解析后过滤/白名单优先/内置+外部配置）
