# 代码生成指令任务书

## 一、任务基本信息
| 项目 | 内容 |
|------|------|
| 任务名称 | IP与端口解析模块重构 — 高内聚低耦合四层架构升级 |
| 执行对象 | Kimi AI 编程助手 |
| 生成目标 | core/exceptions.py、core/models.py、core/validator.py、core/parser.py、tests/test_parser.py |
| 依据资料 | 《PyQt6端口扫描工具代码问题分析》、DEV_LOG v1.0~v1.2、用户三项架构决策 |
| 任务性质 | 代码重构、架构升级、异常体系建立、配置注入支持、单元测试补全 |
| 使用场景 | 授权内网安全巡检端口扫描工具的输入预处理层 |

---

## 二、代码生成总体目标
基于原始 `parser.py`（单文件聚合IP/端口解析逻辑）及《PyQt6端口扫描工具代码问题分析》中识别的 4 项解析层缺陷，重构为四层模块架构，满足以下核心指标：

1. **高内聚**：每个py文件仅含一个抽象层职责（异常/数据/校验/解析）
2. **低耦合**：GUI层仅依赖 `ScanInputFacade` 与 `ParseResult`，不感知底层实现
3. **零副作用**：配置注入为实例级，不污染全局类属性
4. **任务量防护**：`len(targets) × len(ports) > 100000` 时拒绝启动，防止内存爆炸
5. **异常一致性**：所有解析异常继承 `ScannerError`，支持GUI层统一捕获
6. **不可变性**：解析结果使用 `FrozenSet` 与 `frozen=True` dataclass，保证线程安全

---

## 三、逐文件生成指令

### 文件一：core/exceptions.py（异常抽象层）
#### 3.1.1 生成指令
生成项目根异常与解析层异常定义模块，职责为建立统一的异常继承链，使上层模块（GUI、调度器、导出器）无需感知具体实现即可捕获所有解析异常。

#### 3.1.2 必须包含的内容
| 异常类 | 继承关系 | 功能规格 | 属性 |
|--------|----------|----------|------|
| ScannerError | Exception | 项目根异常，所有模块异常的基类 | — |
| ParseError | ScannerError | 解析层异常，携带原始输入便于日志追溯 | raw_input: str |

#### 3.1.3 约束条件
- 所有异常类必须提供有意义的错误信息
- ParseError 必须暴露 `raw_input` 属性，供日志系统记录原始输入
- 文件内不得包含任何业务逻辑或 I/O 操作
- 异常信息使用中文，符合实训报告语境

---

### 文件二：core/models.py（数据契约层）
#### 3.2.1 生成指令
生成不可变数据契约模块，职责为定义解析层与下游扫描引擎之间的唯一交互接口，消除模块间的副作用耦合。

#### 3.2.2 必须包含的内容
| 数据类 | 装饰器 | 字段 | 计算属性 |
|--------|--------|------|----------|
| ParseResult | @dataclass(frozen=True) | targets: FrozenSet[str], ports: FrozenSet[int] | total_tasks, target_count, port_count |

#### 3.2.3 约束条件
- `frozen=True` 保证多线程环境下结果对象不被意外修改
- 计算属性自动推导，避免下游重复计算
- 文件内不得包含任何解析逻辑或 I/O 操作

---

### 文件三：core/validator.py（校验层）
#### 3.3.1 生成指令
生成任务量安全校验模块，职责为独立计算 `target_count × port_count` 并与上限比较，拒绝超大任务量启动。

#### 3.3.2 必须实现的内容
| 名称 | 类型 | 功能规格 | 异常处理 |
|------|------|----------|----------|
| TaskValidator | 类 | 任务量校验器 | 超限抛 ParseError |
| __init__(max_tasks) | 方法 | 接收自定义上限，默认 100000 | — |
| validate(targets, ports) | 方法 | 校验任务总量，超限拒绝 | 抛 ParseError，含当前量/上限/建议 |
| get_stats(targets, ports) | 方法 | 返回统计字典，不触发异常 | 返回 dict 含 is_safe 布尔值 |

#### 3.3.3 约束条件
- 不依赖 IPParser / PortParser，仅接收不可变集合
- 校验信息必须包含：当前任务量、目标数、端口数、上限值、缩小范围建议
- 支持实例级 `max_tasks` 注入，不修改全局默认值

---

### 文件四：core/parser.py（解析引擎层）
#### 3.4.1 生成指令
生成 IP/端口解析引擎与扫描输入门面模块，职责为将输入字符串转换为结构化任务列表，隐藏底层协作细节。

#### 3.4.2 必须实现的类与函数
| 名称 | 类型 | 功能规格 | 异常处理 |
|------|------|----------|----------|
| IPParser | 类 | IP字符串解析器 | 格式错误抛 ParseError |
| resolve(target_str) | 类方法 | 支持单IP/CIDR/IP段/域名/组合 | 统一入口 |
| _parse_token(token) | 类方法 | 分发解析：域名>CIDR>IP段>单IP | 优先级判定 |
| _resolve_domain(domain) | 静态方法 | socket.gethostbyname 域名转IP | 捕获 gaierror |
| _parse_cidr(cidr) | 静态方法 | ipaddress.ip_network 展开网段 | 捕获 ValueError |
| _parse_single_ip(ip) | 静态方法 | ipaddress.ip_address 验证单IP | 捕获 ValueError |
| _parse_range(token) | 静态方法 | 支持简写(1-100)和全写(跨网段) | 验证起止/越界/倒置 |
| PortParser | 类 | 端口字符串解析器 | 越界抛 ParseError |
| resolve(port_str) | 方法 | 支持common/all/单端口/段/组合 | 实例级 common_ports |
| _parse_numeric_token(token) | 方法 | 解析纯数字端口或端口段 | 范围校验 1-65535 |
| ScanInputFacade | 类 | 扫描输入门面，隐藏协作细节 | 透传 ParseError |
| __init__(validator, common_ports) | 方法 | 注入校验器与常用端口 | 实例隔离 |
| parse(target_str, port_str) | 方法 | 对外唯一接口：解析→校验→返回 | 超限抛 ParseError |
| preview(target_str, port_str) | 方法 | 预览模式：解析+统计，不触发上限 | 返回 is_safe |

#### 3.4.3 IP解析详细规格
**支持格式**：
- 单IPv4: `192.168.1.1`
- CIDR网段: `192.168.1.0/24`
- IP段简写: `192.168.1.1-100`（末段简写，同网段）
- IP段全写: `192.168.1.1-192.168.2.255`（支持跨网段）
- 域名: `baidu.com`
- 组合: `192.168.1.1, 10.0.0.0/30, baidu.com`

**域名正则要求**：
- 必须包含至少一个字母（TLD部分）
- 排除纯数字+点组合（如 `192.168.1.1` 不被误判为域名）
- 有效长度 1-253 字符
- 标签不以 `-` 开头/结尾

#### 3.4.4 端口解析详细规格
**支持格式**：
- 关键字: `common`（16个预设常用端口）、`all`（1-65535）
- 单端口: `80`
- 端口段: `1-1000`
- 组合: `common, 8080-8082, 9000`

**预设 common 端口**（16个）：
`21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3306, 3389, 5432, 6379, 8080`

#### 3.4.5 关键约束
- IP解析返回 `FrozenSet[str]`，端口解析返回 `FrozenSet[int]`
- `PortParser` 通过 `__init__` 接收 `common_ports`，实例隔离不污染全局
- `ScanInputFacade` 为 GUI 层唯一入口，不暴露 `IPParser` / `PortParser` / `TaskValidator`
- 所有异常在模块边界消化，向上仅抛 `ParseError`（继承 `ScannerError`）

---

### 文件五：tests/test_parser.py（单元测试层）
#### 3.5.1 生成指令
生成 parser 模块单元测试，覆盖正常路径、边界值、异常路径、配置注入、Preview 模式，共 32 项断言。

#### 3.5.2 测试类划分
| 测试类 | 测试项数 | 覆盖范围 |
|--------|----------|----------|
| TestIPParser | 13 项 | 单IP、CIDR、IP段简写/全写/跨网段、域名、组合、空输入、无效格式、返回类型 |
| TestPortParser | 13 项 | common、all、单端口、端口段、组合、越界、空输入、大小写、实例隔离 |
| TestTaskValidator | 5 项 | 正常通过、边界值、超限拒绝、统计信息、默认值 |
| TestScanInputFacade | 10 项 | 端到端解析、任务量拒绝、配置注入、注入隔离、自定义校验、Preview、异常类型、不可变性 |

#### 3.5.3 约束条件
- 使用 `unittest` 标准框架
- 异常测试使用 `assertRaises` + 消息内容校验
- 域名解析测试允许网络环境导致的 `ParseError`（使用 `skipTest`）
- 所有测试必须独立运行，无执行顺序依赖

---

## 四、技术约束与规范

### 4.1 语言与环境约束
| 约束项 | 要求 |
|--------|------|
| Python 版本 | 3.8+ |
| 第三方依赖 | 禁止（仅标准库：ipaddress, socket, re, typing, dataclasses, unittest） |
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
| 模块依赖方向 | exceptions → models → validator → parser（单向，无循环） |
| 对外暴露 | 仅 `ScanInputFacade`、`ParseResult`、`ScannerError` |
| 配置注入 | 实例级，禁止修改类属性 |
| 返回类型 | 不可变集合（FrozenSet）与不可变数据类（frozen=True） |
| 异常传播 | 底层消化具体异常，向上仅抛 `ParseError` |

---

## 五、质量标准

### 5.1 功能质量
| 验收项 | 通过标准 |
|--------|----------|
| 导入无异常 | `python -c "from core.parser import ScanInputFacade"` 正常退出 |
| 单IP解析 | `IPParser.resolve("192.168.1.1") == {"192.168.1.1"}` |
| CIDR解析 | `/30` 网段返回 2 个可用主机地址 |
| IP段简写 | `1-3` 展开为 `1,2,3` |
| IP段跨网段 | `254-2` 跨网段生成 5 个 IP |
| 域名解析 | `localhost` 解析为至少 1 个 IP（或 ParseError） |
| common端口 | 16 个预设端口，含 80/443/22 等 |
| all端口 | 65535 个端口 |
| 组合解析 | `common, 9000` 返回 17 个端口 |
| 任务量上限 | `1.0.0.0/8` + `1-65535` 抛出 ParseError |
| 边界值 | 100000 任务量刚好通过，100001 拒绝 |
| 配置注入 | 自定义 3 个端口，默认 Facade 不受影响 |
| Preview模式 | 超限返回 `is_safe=False`，不抛异常 |

### 5.2 代码质量
| 验收项 | 通过标准 |
|--------|----------|
| 编译通过 | `py_compile` 所有模块无语法错误 |
| 无循环导入 | `import core.parser` 不触发 ImportError |
| 类型注解 | mypy 检查无 error 级别提示 |
| 文档覆盖 | 类 + 公共方法 docstring 覆盖率 100% |
| 无裸 except | 所有异常捕获指定具体类型 |
| 无魔法数 | 端口范围、任务上限等使用命名常量 |

### 5.3 测试质量
| 验收项 | 通过标准 |
|--------|----------|
| 测试通过率 | `python -m unittest tests.test_parser -v` 32/32 通过 |
| 测试独立性 | 无执行顺序依赖，乱序运行全部通过 |
| 异常覆盖 | 所有 `raise ParseError` 分支均有对应测试 |
| 边界覆盖 | 空输入、越界、倒置、刚好超限等边界均有测试 |

---

## 六、交付物清单
| 编号 | 交付物 | 类型 | 路径 | 代码行数 | 说明 |
|------|--------|------|------|----------|------|
| 1 | exceptions.py | 源码 | core/exceptions.py | ~21 | 异常抽象层 |
| 2 | models.py | 源码 | core/models.py | ~27 | 数据契约层 |
| 3 | validator.py | 源码 | core/validator.py | ~51 | 任务量校验层 |
| 4 | parser.py | 源码 | core/parser.py | ~197 | 解析引擎层 |
| 5 | test_parser.py | 测试 | tests/test_parser.py | ~268 | 单元测试 |
| 6 | 本指令任务书 | 文档 | TASK_BOOK_PARSER.md | — | 规格、约束、标准 |

---

## 七、执行规范
1. 严格依据《PyQt6端口扫描工具代码问题分析》中的解析层缺陷逐项修复，不随意增删功能
2. 保持与现有扫描引擎（scanner.py）、GUI界面（gui.py）的接口兼容
3. 仅做输入预处理，不实现扫描、攻击、破解功能
4. 输出正式、清晰，可直接用于实训报告代码章节
5. 完成后必须验证：编译通过、32项测试全通过、无循环导入

---

## 八、架构决策记录（ADR）

### ADR-001：四层模块拆分
- **决策**：按 `exceptions → models → validator → parser` 四层拆分
- **理由**：单向依赖（上层依赖下层，下层不依赖上层），消除循环导入
- **影响**：文件数从 1 增至 4，但编译/导入速度无显著下降，可维护性大幅提升

### ADR-002：异常继承链
- **决策**：`ParseError` 继承 `ScannerError`，而非直接使用 `ValueError`
- **理由**：GUI 层只需 `except ScannerError` 即可捕获所有模块异常，无需感知具体实现
- **影响**：新增异常文件，但降低跨模块耦合

### ADR-003：实例级配置注入
- **决策**：`PortParser` 通过 `__init__` 接收 `common_ports`，而非修改类属性
- **理由**：类属性全局共享会导致测试污染与运行时副作用
- **影响**：每次创建 Facade 需传入配置，但保证隔离性

### ADR-004：门面模式（Facade）
- **决策**：引入 `ScanInputFacade` 作为唯一对外接口
- **理由**：隐藏 `IPParser`、`PortParser`、`TaskValidator` 的协作细节
- **影响**：GUI 层代码简化，仅需 `from core.parser import ScanInputFacade`

### ADR-005：不可变返回类型
- **决策**：解析结果使用 `FrozenSet` 与 `frozen=True` dataclass
- **理由**：多线程环境下防止结果对象被意外修改，消除副作用
- **影响**：下游无法原地修改结果，需创建新对象

---

## 九、合规声明

本模块仅限授权内网安全测试使用。解析功能本身不发起网络扫描，仅做输入预处理。任务量上限防护旨在防止误操作导致的资源耗尽，不构成对扫描行为的限制或鼓励。

---

**文档版本**: v1.0  
**编制日期**: 2026-05-26  
**依据标准**: 《PyQt6端口扫描工具代码问题分析》、DEV_LOG v1.0~v1.2、用户三项架构决策（配置注入/异常契约/模块拆分）
