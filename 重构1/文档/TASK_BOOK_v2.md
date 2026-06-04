# 基于Python的Windows端口扫描工具 — 代码生成指令任务书

## 一、任务基本信息

| 项目 | 内容 |
|------|------|
| 任务名称 | Windows 轻量级多线程端口扫描工具 — 全模块源码生成任务 |
| 执行对象 | Kimi AI 编程助手 |
| 生成目标 | 11份可直接运行的完整源码，构成模块化项目结构 |
| 依据资料 | 《基于Python的Windows自用端口扫描工具开发实训计划书》、《Python 端口扫描器问题分析》（10项缺陷）、重构版参考源码（`main_window_1.2.py`）、用户三项确认答复 |
| 任务性质 | 代码重构、架构升级、缺陷修复、功能增强、工程化交付 |
| 使用场景 | 课程实训、授权内网安全巡检、端口开放检测、教学演示、GUI与CLI双模式操作 |

---

## 二、代码生成总体目标

基于原始实训代码及问题分析中列出的 **10项缺陷** 与 **6项升级需求**，生成升级后的可直接运行源码，满足以下核心指标：

1. **模块化架构**：按 `core/`（引擎）、`utils/`（工具）、`gui/`（界面）三层拆分，职责单一
2. **双模式并存**：CLI 命令行模式（`argparse`）与 GUI 可视化模式（`PyQt6`）统一入口
3. **零第三方依赖（核心引擎）**：`core/` 与 `utils/` 仅使用 Python 3.8+ 内置模块
4. **GUI 允许 PyQt6**：`gui/` 与 `main.py` 允许依赖 `PyQt6`，但核心逻辑不得反向依赖 GUI
5. **Windows 普通权限 100% 可运行**：ICMP 自动降级 TCP 探测，绝不跳过 IP
6. **扫 1-65535 不崩溃**：`ThreadPoolExecutor` / `threading` 线程池替代每端口一线程
7. **误报率可控**：TCP 二次验证、UDP 保守策略、超时精细控制
8. **导出策略模式化**：`IExporter` + `ExporterRegistry`，支持 TXT/CSV/JSON 动态字段导出
9. **覆盖确认双模式**：GUI 模态弹窗 / CLI 交互式 `y/n` / 非交互默认拒绝
10. **合规内置**：启动强制合规提示、大任务量确认、报告自动附加法律声明

---

## 三、逐文件生成指令

### 文件一：config.py（全局配置层）

#### 3.1.1 生成指令
生成全局配置模块，集中管理所有常量、映射表、默认参数与路径模板。禁止包含任何业务逻辑、I/O 操作或类定义。

#### 3.1.2 必须包含的内容

| 配置项 | 类型 | 规格说明 |
|--------|------|----------|
| `COMMON_PORTS` | `dict[int, str]` | 端口到服务名映射，至少覆盖 28 种常见服务（FTP/SSH/Telnet/SMTP/DNS/HTTP/POP3/IMAP/HTTPS/SMB/RDP/MySQL/PostgreSQL/Redis/MongoDB 等） |
| `TCP_ALIVE_PORTS` | `list[int]` | 降级存活探测轮询端口：`[80, 443, 22, 3389, 445, 139, 21, 25]` |
| `DEFAULT_TIMEOUT` | `float` | 单次探测超时，默认 `1.0` 秒 |
| `DEFAULT_THREADS` | `int` | 默认并发线程数，默认 `10` |
| `MAX_THREADS` | `int` | 线程硬上限，固定 `20`（实训计划书约束） |
| `DEFAULT_DELAY_MIN` | `float` | 随机延迟下限，默认 `0.0` 秒 |
| `DEFAULT_DELAY_MAX` | `float` | 随机延迟上限，默认 `0.5` 秒 |
| `COLORS` | `dict[str, str]` | ANSI 颜色转义序列（`cyan/yellow/green/red/magenta/white`） |
| `OUTPUT_DIR` | `str` | 默认输出目录 `"./reports"`（仅作为字符串常量，不执行路径创建） |
| `APP_NAME` | `str` | 应用名称 `"Port Scanner"` |
| `VERSION` | `str` | 版本号 `"2.0.0"` |
| `COMPLIANCE_TEXT` | `str` | 合规声明模板，包含《网络安全法》提示与使用范围限制 |

#### 3.1.3 约束条件
- 所有键名必须为英文大写，符合常量命名规范
- 端口值必须在 1-65535 范围内
- 颜色代码必须为 `[XXm` 标准格式
- 文件内不得包含任何函数定义、类定义或执行逻辑

---

### 文件二：core/models.py（数据契约层）

#### 3.2.1 生成指令
生成数据模型模块，定义所有模块共享的不可变数据契约。消除元组/字典混用风险，为动态字段导出提供标准化接口。

#### 3.2.2 必须包含的类与枚举

| 名称 | 类型 | 功能规格 |
|------|------|----------|
| `PortState` | `Enum` | 端口状态枚举：`OPEN = "open"`、`CLOSED = "closed"`、`FILTERED = "filtered"`、`ERROR = "error"` |
| `ScanResult` | `@dataclass(frozen=True)` | 扫描结果不可变对象，字段：`ip` (str)、`port` (int)、`protocol` (str)、`state` (PortState)、`service` (Optional[str])、`banner` (Optional[str])、`error_msg` (Optional[str])、`response_time_ms` (Optional[float]) |
| `ScanConfig` | `@dataclass` | 扫描运行时配置，字段：`protocol` (str)、`threads` (int)、`timeout` (int)、`delay_min` (float)、`delay_max` (float)、`skip_offline` (bool) |

#### 3.2.3 约束条件
- `ScanResult` 必须标记 `frozen=True`，确保哈希安全与不可变性
- 所有字段必须带类型注解
- 模块仅依赖 `dataclass`、`enum`、`typing`，无其他依赖

---

### 文件三：core/ip_parser.py（输入解析层）

#### 3.3.1 生成指令
生成 IP 解析模块，支持全格式目标解析。纯函数设计，无 GUI / 网络 / 文件依赖。

#### 3.3.2 必须实现的函数

| 名称 | 功能规格 | 异常处理 |
|------|----------|----------|
| `resolve_targets(text: str) -> List[str]` | 解析单 IP、IP 段（`192.168.1.10-20`）、CIDR（`192.168.1.0/24`）、域名（`socket.getaddrinfo` 预检）、逗号分隔混合输入 | `ValueError`（空输入、无法解析、CIDR 超出 `/24` 限制） |
| `_expand_cidr(cidr: str) -> List[str]` | CIDR 展开为 IP 列表，限制网段大小（最大 `/16`，超范围抛异常） | `ValueError`（格式错误、超大规模） |
| `_expand_range(ip_range: str) -> List[str]` | IP 段展开，如 `192.168.1.1-100` | `ValueError`（格式错误、超 256 个） |

#### 3.3.3 约束条件
- 禁止裸 `except:`，必须捕获具体异常
- 域名解析失败时抛出 `ValueError` 并附带原始输入
- 返回列表需去重且保序（`dict.fromkeys`）
- 仅使用 `socket`、`re`、`typing` 标准库

---

### 文件四：core/port_parser.py（端口解析层）

#### 3.4.1 生成指令
生成端口解析模块，支持全格式端口解析。纯函数设计，与 IP 解析层对称。

#### 3.4.2 必须实现的函数

| 名称 | 功能规格 | 异常处理 |
|------|----------|----------|
| `resolve_ports(text: str) -> List[int]` | 解析 `common`（返回内置列表）、单端口、端口段（`1-1000`）、离散端口（`22,80,443`）混合输入 | `ValueError`（无有效端口、越界） |
| `COMMON_PORTS_LIST` | 常量列表，与 `config.COMMON_PORTS` 键一致 | — |

#### 3.4.3 约束条件
- 端口去重并排序
- 自动过滤 `<1` 或 `>65535` 的非法值
- 仅使用标准库

---

### 文件五：core/scanner.py（扫描引擎层）

#### 3.5.1 生成指令
生成扫描核心引擎模块，提供所有网络探测函数、存活检测逻辑与端口扫描器类。必须保证线程安全、异常分层、权限兼容。

#### 3.5.2 必须实现的函数与类

| 名称 | 类型 | 功能规格 | 异常处理 |
|------|------|----------|----------|
| `colored(text, color)` | 函数 | 跨平台彩色文本，Windows 自动检测并启用 VT100 | 无异常，静默降级 |
| `_checksum(source_string)` | 函数 | ICMP 报文校验和（RFC 1071） | 无异常 |
| `scan_tcp_once(ip, port, timeout)` | 函数 | 单次 TCP 全连接探测，返回 `(state, service, banner)` | 捕获 `socket.timeout`、`ConnectionRefusedError`、`OSError` |
| `scan_tcp(ip, port, timeout)` | 函数 | TCP 扫描（含二次验证），首次开放后延迟 50ms 重扫确认 | 依赖 `scan_tcp_once` |
| `scan_udp(ip, port, timeout)` | 函数 | UDP 保守探测：发空包，超时标记 `FILTERED`，ICMP 不可达标记 `CLOSED` | 捕获 `OSError`、`PermissionError` |
| `is_alive_icmp(ip, timeout)` | 函数 | ICMP 存活探测，返回三级状态：`True`（在线）、`False`（离线）、`None`（权限不足） | 捕获 `PermissionError`、`OSError`、`subprocess.TimeoutExpired` |
| `is_alive_tcp(ip, timeout)` | 函数 | TCP 降级探测，轮询 `TCP_ALIVE_PORTS`，**始终 return True** | 单端口随机延迟 |
| `is_alive(ip, timeout)` | 函数 | 统一存活入口：先 ICMP，权限不足自动降级 TCP，TCP 也失败则返回 `True` | 子函数处理异常 |
| `PortScanner` | 类 | 线程池扫描器，内部消化所有异常，返回统一 `ScanResult` | 线程安全、支持中断 |

#### 3.5.3 `PortScanner` 类详细规格

| 方法 | 规格 |
|------|------|
| `__init__(timeout: float)` | 初始化超时、`_icmp_available` 标志 |
| `ping_host(ip: str) -> bool` | ICMP 探测；无权限时自动降级为 `_tcp_ping`，设置 `_icmp_available = False` |
| `_tcp_ping(ip: str, port: int = 80) -> bool` | TCP 连通性探测，用于降级 |
| `scan_single(ip, port, protocol) -> ScanResult` | 统一扫描入口，记录 `response_time_ms`，消化所有异常为 `ERROR` 状态 |
| `_scan_tcp(ip, port) -> Tuple[PortState, Optional[str], Optional[str]]` | 全连接扫描，识别服务名与 Banner |
| `_scan_udp(ip, port) -> Tuple[PortState, Optional[str], Optional[str]]` | UDP 扫描，保守策略 |
| `_identify_service(port, protocol) -> str` | 服务识别，优先 `socket.getservbyport`，失败回退内置映射表 |

#### 3.5.4 关键约束
- 禁止裸 `except:`，必须捕获具体异常
- `is_alive_tcp` 必须 `return True`，禁止跳过任何 IP
- 套接字必须在使用后关闭（`with` 语句或 `finally`）
- 仅使用 `socket`、`subprocess`、`time`、`random` 等内置模块

---

### 文件六：core/thread_manager.py（并发调度层）

#### 3.6.1 生成指令
生成线程管理模块，基于 `threading` + `queue` 实现轻量级线程池。支持暂停、恢复、停止、进度查询。

#### 3.6.2 必须实现的类

| 名称 | 类型 | 功能规格 |
|------|------|----------|
| `ThreadManager` | 类 | 线程池调度器：任务队列、结果队列、并发控制、生命周期管理 |

#### 3.6.3 `ThreadManager` 类详细规格

| 方法 | 规格 |
|------|------|
| `__init__(max_workers, delay_min, delay_max)` | 初始化队列、锁、条件变量、状态标志 |
| `set_total(n: int)` | 设置总任务数，用于进度计算 |
| `progress() -> float` | 返回 0.0~100.0 的进度百分比 |
| `pause()` | 设置暂停标志，工作线程进入条件等待 |
| `resume()` | 清除暂停标志，唤醒所有等待线程 |
| `stop()` | 设置停止标志，清空任务队列，唤醒线程使其退出 |
| `start(worker_func: Callable)` | 启动 `max_workers` 个守护线程 |
| `_worker_loop(worker_func)` | 任务消费循环：检查暂停/停止 → 取任务 → 随机延迟 → 执行 → 结果入队 |
| `wait()` | 等待所有工作线程结束（带超时） |

#### 3.6.4 关键约束
- 线程安全：所有共享状态（`_processed`、`_paused`、`_stopped`）必须加锁
- 防御编程：`worker_func` 抛异常时，包装为 `ERROR` 状态的 `ScanResult` 入队，不崩溃
- 禁止每端口一线程，必须复用线程池

---

### 文件七：utils/exporters.py（导出策略层）

#### 3.7.1 生成指令
生成结果导出模块，采用 **策略模式** 实现格式无关的导出引擎。支持动态字段、覆盖确认、元信息返回。模块零外部依赖（纯标准库）。

#### 3.7.2 必须实现的类与异常

| 名称 | 类型 | 功能规格 |
|------|------|----------|
| `ExportError` | `Exception` | 导出过程统一异常 |
| `ExportMeta` | `@dataclass` | 导出元信息：`filepath`、`format`、`record_count`、`file_size_bytes`、`timestamp`、`fields` |
| `OverwriteStrategy` | `ABC` | 覆盖确认策略抽象基类：`should_overwrite(filepath) -> bool` |
| `RaiseOnExistsStrategy` | `OverwriteStrategy` | 安全默认：文件存在则抛 `FileExistsError` |
| `AlwaysOverwriteStrategy` | `OverwriteStrategy` | 静默覆盖（自动化脚本场景） |
| `PromptCLIOverwriteStrategy` | `OverwriteStrategy` | CLI 交互式 `y/N` 确认；非交互环境（`stdin.isatty() == False`）自动抛异常拒绝 |
| `IExporter` | `ABC` | 导出策略接口：`export(results, filepath) -> ExportMeta`、`extension() -> str`、`supported_fields(results) -> List[str]` |
| `TxtExporter` | `IExporter` | TXT 导出：动态列宽计算（遍历内容取最大宽度 + padding），解决固定列宽溢出 |
| `CsvExporter` | `IExporter` | CSV 导出：`csv.DictWriter` 动态字段，不写死 `fieldnames`，`extrasaction="ignore"` |
| `JsonExporter` | `IExporter` | JSON 导出：`json.dump` + `default` 序列化 Enum，支持 `ensure_ascii=False` |
| `ExporterRegistry` | 类 | 注册中心：自动格式推断（从文件扩展名）、策略注册、统一导出入口 |

#### 3.7.3 `ExporterRegistry.export()` 入口规格

```python
def export(
    results: List[Any],
    filepath: str,
    fmt: Optional[str] = None,
    overwrite_strategy: Optional[OverwriteStrategy] = None,
    output_dir: Optional[str] = None,
) -> ExportMeta
```

- `fmt=None` 时自动从 `filepath` 扩展名推断格式
- `output_dir` 处理纯文件名路径拼接
- 自动修正扩展名（如用户输入 `report` 自动变为 `report.txt`）
- 默认覆盖策略为 `RaiseOnExistsStrategy()`（安全优先）

#### 3.7.4 关键约束
- 动态字段：通过 `_extract_records()` 统一适配器将 `ScanResult` / `dict` 自动转为字典，运行时提取所有字段
- 异常分层：`PermissionError` → `ExportError("权限不足")`；`OSError` → `ExportError("磁盘错误")`
- 目录自动创建：`os.makedirs(..., exist_ok=True)`，失败时包装为 `ExportError`
- 模块不依赖 `PyQt6`，GUI 覆盖策略在 `gui/` 层实现

---

### 文件八：utils/logger.py（日志管理层）

#### 3.8.1 生成指令
生成日志模块，基于 `logging` 标准库实现实时日志记录与文件导出。支持控制台与文件双输出。

#### 3.8.2 必须实现的类

| 名称 | 功能规格 |
|------|----------|
| `ScanLogger` | 配置 `logging.Logger`，支持 `DEBUG/INFO/WARNING/ERROR` 级别；文件处理器按时间戳命名；格式包含时间、级别、消息 |

#### 3.8.3 约束条件
- 日志文件编码 `utf-8`
- 支持运行时切换日志级别
- 线程安全（`logging` 内置线程安全）

---

### 文件九：utils/config_manager.py（配置持久化层）

#### 3.9.1 生成指令
生成配置管理模块，封装 JSON 配置的读写与默认值回退。与 GUI 解耦，不依赖 PyQt6。

#### 3.9.2 必须实现的类

| 名称 | 功能规格 |
|------|----------|
| `ConfigManager` | 配置持久化管理器：默认配置字典、加载、保存、get/set |

#### 3.9.3 约束条件
- 配置文件路径默认 `"scanner_config.json"`
- 加载失败时回退到默认值，不抛异常
- 保存时异常静默处理，避免阻塞退出流程
- 合并策略：以默认值为基础，用已存值覆盖

---

### 文件十：gui/main_window.py（图形界面层）

#### 3.10.1 生成指令
生成 PyQt6 主界面模块。零业务逻辑，仅负责布局、事件绑定、数据展示。通过 `ScanWorker`（`QThread`）与核心引擎交互，避免界面卡顿。

#### 3.10.2 必须实现的类与组件

| 名称 | 类型 | 功能规格 |
|------|------|----------|
| `MainWindow` | `QMainWindow` | 主窗口：标题栏显示版本、1100×750 默认尺寸 |
| `GUIPromptOverwriteStrategy` | `OverwriteStrategy` | GUI 模态覆盖确认：弹出 `QMessageBox.question`，默认选「否」 |
| `ScanWorker` | `QThread` | 工作线程：连接 `ThreadManager` 与 `PortScanner`，转换 PyQt 信号 |

#### 3.10.3 界面布局规格

| 区域 | 组件 | 说明 |
|------|------|------|
| 输入参数组 | `QLineEdit` (目标IP) | 支持单IP/IP段/CIDR/域名/逗号分隔 |
| | `QLineEdit` (端口) | 支持 common/单端口/端口段/离散端口 |
| | `QComboBox` (协议) | tcp / udp |
| | `QSpinBox` (线程) | 1~20 |
| | `QSpinBox` (超时) | 1~10 秒 |
| | `QSpinBox` (随机延迟) | 0~5 秒 |
| | `QCheckBox` (跳过离线IP) | 勾选时先 ICMP 探测，无权限自动降级 |
| 控制按钮 | `QPushButton` (开始/暂停/停止/清空) | 扫描状态联动禁用/启用 |
| | `QPushButton` (导出 TXT/CSV/JSON) | 调用 `ExporterRegistry`，注入 `GUIPromptOverwriteStrategy` |
| 进度展示 | `QProgressBar` | 0~100%，带百分比文本 |
| 结果表格 | `QTableWidget` | 7列：IP/端口/协议/状态/服务/耗时/错误；按状态着色（Open绿/Closed白/Filtered黄/Error红） |
| 日志区域 | `QPlainTextEdit` | 等宽字体，只读，最大块数 2000，自动滚动 |
| 状态栏 | `QStatusBar` | 显示总任务/已完成/开放端口数 |

#### 3.10.4 `ScanWorker` 信号规格

| 信号 | 参数 | 说明 |
|------|------|------|
| `progress` | `int` | 0~100 进度 |
| `log_msg` | `str` | 日志文本 |
| `result` | `ScanResult` | 单条结果 |
| `finished` | `List[ScanResult]` | 扫描完成 |
| `error` | `str` | 异常信息 |
| `stats_update` | `(int, int, int)` | total, processed, open_count |

#### 3.10.5 关键约束
- 扫描期间禁用所有输入控件（含 `QCheckBox`、`QSpinBox`、`QLineEdit`）
- 暂停/恢复按钮文本切换：`⏸ 暂停` ↔ `▶ 恢复`
- 导出弹窗展示 `ExportMeta` 详情：路径、记录数、大小、字段列表
- 关闭窗口时保存配置（`ConfigManager`），若扫描进行中需二次确认
- 启动时弹出合规提示弹窗（`QMessageBox.information`），用户确认后方可操作

---

### 文件十一：main.py（程序入口层）

#### 3.11.1 生成指令
生成统一入口模块，支持 CLI 命令行与 GUI 可视化双模式启动。处理参数解析、合规提示、扫描调度、结果展示、报告导出。

#### 3.11.2 必须实现的函数

| 名称 | 功能规格 | 异常处理 |
|------|----------|----------|
| `parse_ip(text: str) -> List[str]` | 调用 `IPParser.resolve_targets`，限制 CIDR 大小 | `ValueError` |
| `parse_ports(text: str) -> List[int]` | 调用 `PortParser.resolve_ports` | `ValueError` |
| `print_progress(current, total, width=50)` | 原生进度条，无第三方库 | 无 |
| `save_report(results, filepath, fmt)` | 调用 `ExporterRegistry.export`，附加合规声明 | `ExportError` |
| `check_admin() -> bool` | 跨平台权限检测（Windows 用 `ctypes.windll.shell32.IsUserAnAdmin`） | 静默返回 False |
| `compliance_prompt()` | 强制合规提示：控制台输出品红色声明，等待用户输入 `yes` 确认 | 输入非 yes 则退出 |
| `main()` | 主流程：权限检测 → 合规提示 → 参数解析 → 大任务确认 → 扫描 → 展示 → 导出 | 全局异常捕获 |

#### 3.11.3 CLI 交互流程

```
启动 → 检测管理员权限（黄色提示）→ 合规声明（品红色，需输入 yes）→
输入目标/端口/协议/线程/超时 → 解析 → 大任务量确认（>1000 任务需确认）→
扫描（实时进度条 + 开放端口高亮）→ 结果汇总 → 导出报告（自动附加合规声明）→ 结束
```

#### 3.11.4 界面输出规格

| 元素 | 颜色 | 说明 |
|------|------|------|
| 标题 | 青色 | 应用名称与版本 |
| 权限提示 | 黄色（无权限）/ 绿色（有权限） | 管理员状态 |
| 错误信息 | 红色 | 参数错误、扫描异常 |
| 开放端口 | 绿色 | 高亮显示 |
| 合规声明 | 品红色 | 法律提示 |
| 进度条 | 白色/青色 | 百分比与进度块 |

#### 3.11.5 关键约束
- CLI 模式下使用 `argparse` 解析参数：`--target`、`-p`/`--ports`、`-t`/`--threads`、`-o`/`--timeout`、`-d`/`--delay`、`-f`/`--format`、`-o`/`--output`、`-g`/`--gui`
- 添加 `-g` 或 `--gui` 参数时启动 PyQt6 界面
- 无参数或参数不全时，进入交互式向导模式
- 大任务量（IP数 × 端口数 > 1000）时要求控制台确认，防止误操作
- 报告文件末尾自动追加 `COMPLIANCE_TEXT`
- 仅使用 `argparse`、`sys`、`os` 等标准库（GUI 模式允许 `PyQt6`）

---

## 四、技术约束与规范

### 4.1 语言与环境约束
- Python 3.8+（兼容 Windows 10/11）
- 核心引擎（`core/`、`utils/`）**零第三方库**
- GUI 层（`gui/`）允许依赖 `PyQt6`
- 仅使用白名单内置模块：`socket`、`threading`、`queue`、`subprocess`、`time`、`random`、`csv`、`json`、`logging`、`argparse`、`re`、`ctypes`、`os`、`sys`、`datetime`、`abc`、`dataclasses`、`enum`、`typing`、`inspect`

### 4.2 代码风格约束
- 函数/变量：小写 + 下划线（`snake_case`）
- 类：大驼峰（`PascalCase`）
- 常量：全大写 + 下划线（`SCREAMING_SNAKE_CASE`）
- 必须加 docstring（Google 风格）与行内注释
- 禁止裸 `except:`，必须捕获具体异常类型
- 禁止魔法数，必须使用 `config` 中定义的常量
- 模块顶部添加 `#!/usr/bin/env python3` 与编码声明

### 4.3 架构约束
- **低耦合**：`gui/` 不直接调用 `socket`/`threading`，通过 `ScanWorker` 调用 `core/`
- **高内聚**：每个模块职责单一，同类功能集中
- **依赖倒置**：`ExporterRegistry` 依赖 `IExporter` 抽象，不依赖具体格式
- **开闭原则**：新增导出格式只需注册，无需修改 `ExporterRegistry` 内部逻辑

### 4.4 安全与合规约束
- 普通权限可运行，权限不足自动降级
- 绝不跳过 IP（`is_alive_tcp` 必须 `return True`）
- 随机延迟 0~N 秒防防火墙拦截
- 线程硬上限 20
- 禁止超大网段（CIDR 最大 `/16`）
- 报告自动附加合规声明
- 启动强制合规提示（GUI 弹窗 / CLI 输入确认）

---

## 五、质量标准

### 5.1 功能质量
- [ ] 导入无异常：`import config`、`from core.scanner import PortScanner` 等全部正常
- [ ] 本地回环扫描正常：`127.0.0.1` 扫描 `80,443` 返回预期结果
- [ ] CIDR 解析正确：`192.168.1.0/24` 展开为 256 个 IP
- [ ] 端口解析与去重正常：`common`、`1-1000`、`22,80,443` 混合输入正确
- [ ] 权限自动降级：非管理员运行 ICMP 探测时自动降级 TCP，不崩溃
- [ ] Ctrl+C 安全退出：线程池收到停止信号后优雅退出，不残留僵尸线程
- [ ] 报告可导出：TXT/CSV/JSON 三种格式均能生成，内容完整，末尾含合规声明
- [ ] GUI 启动正常：`-g` 参数或双击运行能弹出 PyQt6 窗口
- [ ] GUI 扫描不卡顿：`ScanWorker` 在独立线程运行，界面响应流畅
- [ ] 覆盖确认有效：GUI 弹窗 / CLI 交互均能阻止误覆盖

### 5.2 性能质量
- [ ] 全端口扫描（1-65535）内存占用 < 50MB
- [ ] 20 线程全端口扫描耗时 < 120 秒（本地回环）
- [ ] 连续扫描稳定不崩溃，无内存泄漏
- [ ] GUI 结果表格 1000 行以上不卡顿

### 5.3 代码质量
- [ ] 无裸 `except:` 语句
- [ ] 无死代码（未使用的函数/变量）
- [ ] 无魔法数（所有数值来自 `config`）
- [ ] 线程安全：共享变量均有锁保护
- [ ] 套接字正常关闭（`with` 语句或 `try/finally`）
- [ ] 类型注解覆盖率 > 80%
- [ ] 每个公共函数/类均有 docstring

---

## 六、交付物清单

| 编号 | 交付物 | 类型 | 路径 | 说明 |
|------|--------|------|------|------|
| 1 | `config.py` | 源码 | `./config.py` | 全局配置与常量 |
| 2 | `core/models.py` | 源码 | `./core/models.py` | 数据契约（ScanResult / PortState / ScanConfig） |
| 3 | `core/ip_parser.py` | 源码 | `./core/ip_parser.py` | IP/域名/CIDR 解析 |
| 4 | `core/port_parser.py` | 源码 | `./core/port_parser.py` | 端口解析 |
| 5 | `core/scanner.py` | 源码 | `./core/scanner.py` | 扫描引擎（PortScanner / 存活探测） |
| 6 | `core/thread_manager.py` | 源码 | `./core/thread_manager.py` | 线程池调度器 |
| 7 | `utils/exporters.py` | 源码 | `./utils/exporters.py` | 导出策略（IExporter / Registry / 动态字段） |
| 8 | `utils/logger.py` | 源码 | `./utils/logger.py` | 日志记录 |
| 9 | `utils/config_manager.py` | 源码 | `./utils/config_manager.py` | 配置持久化 |
| 10 | `gui/main_window.py` | 源码 | `./gui/main_window.py` | PyQt6 主界面（ScanWorker / 控件布局） |
| 11 | `main.py` | 源码 | `./main.py` | 统一入口（CLI + GUI 双模式） |
| 12 | 本指令任务书 | 文档 | `./TASK_BOOK_v2.md` | 规格、约束、标准 |

---

## 七、执行规范

1. **严格依据问题分析升级**：针对 10 项缺陷逐项修复，不随意增删功能
2. **保持轻量化**：核心引擎无第三方依赖，GUI 层仅依赖 `PyQt6`
3. **仅做端口检测**：不实现攻击、破解功能
4. **输出正式可交付**：代码可直接用于课程实训提交，含完整注释与 docstring
5. **完成后验证**：必须自验证导入、回环扫描、解析、权限降级、导出、GUI 启动六项基础功能
6. **合规优先**：所有代码路径必须包含合规提示，严禁生成用于非法扫描的绕过逻辑

---

文档版本：v2.0
编制日期：2026-06-04
依据标准：《基于Python的Windows自用端口扫描工具开发实训计划书》、《Python 端口扫描器问题分析》、用户三项确认答复、重构版参考源码
