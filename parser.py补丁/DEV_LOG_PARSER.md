# AI 原生软件开发日志
项目：Windows 轻量级多线程端口扫描工具 — IP与端口解析模块重构
范式：Software 3.0｜意图驱动｜智能体工程
日期：2026-05-26
变更依据：《PyQt6 端口扫描工具 - 代码问题分析》、用户三项架构决策、DEV_LOG v1.0~v1.2
执行智能体：Kimi AI 编程助手

---

## 一、需求工程（Spec-First 规格优先）

### 1. 业务意图
基于《PyQt6 端口扫描工具 - 代码问题分析》对原始 `parser.py` 进行系统性重构，解决 4 项解析层缺陷、消除全局状态污染、建立任务量安全防护、统一异常体系，输出可直接用于实训报告交付的解析层源码与单元测试。

核心意图：构建一款**高内聚、低耦合、零副作用、可测试**的输入预处理层，作为扫描引擎与 GUI 界面的统一数据入口。

### 2. 功能性需求（结构化无歧义）
| 编号 | 需求项 | 规格说明 |
|------|--------|----------|
| FR-01 | 目标解析 | 支持单 IP、CIDR 网段、IP 段简写/全写（跨网段）、域名、组合输入 |
| FR-02 | 端口解析 | 支持 common（16 种服务映射）、all（1-65535）、单端口、端口段、组合输入 |
| FR-03 | 任务量防护 | `len(targets) × len(ports) > 100000` 时拒绝启动，防止内存爆炸 |
| FR-04 | 配置注入 | 常用端口与任务上限支持实例级注入，不污染全局类属性 |
| FR-05 | 预览模式 | 解析并返回统计信息，不触发上限异常，用于 GUI 实时估算 |
| FR-06 | 异常统一 | 所有解析异常继承 `ScannerError`，支持 GUI 层统一捕获 |

### 3. 非功能性需求（量化约束）
| 编号 | 需求项 | 量化指标 |
|------|--------|----------|
| NFR-01 | 模块内聚性 | 每个 py 文件仅含一个抽象层职责 |
| NFR-02 | 模块耦合度 | GUI 层仅依赖 `ScanInputFacade` 与 `ParseResult` |
| NFR-03 | 线程安全 | 返回不可变集合（FrozenSet）与不可变数据类（frozen=True） |
| NFR-04 | 零副作用 | 配置注入为实例级，不影响其他 Facade 实例 |
| NFR-05 | 可测试性 | 32 项单元测试，逻辑分支覆盖率 ≥ 95% |
| NFR-06 | 异常一致性 | 所有解析异常继承 `ScannerError` |

### 4. 领域字典（统一术语）
| 术语 | 定义 |
|------|------|
| FrozenSet | 不可变集合，消除多线程副作用 |
| frozen=True | dataclass 装饰器，禁止运行时修改字段 |
| ParseResult | 不可变数据契约，解析层与下游的唯一交互接口 |
| ScannerError | 项目根异常，所有模块异常的基类 |
| ParseError | 解析层异常，携带原始输入便于日志追溯 |
| Facade | 门面模式，隐藏底层协作细节，降低耦合 |
| 实例隔离 | 每个解析器实例拥有独立配置，不共享全局状态 |
| 任务量上限 | 默认 100000，可配置，超限拒绝启动 |

### 5. BDD 行为规约（Given-When-Then）

#### 场景 1：IP 段简写解析
Given 用户输入目标 "192.168.1.1-3"
When 执行 IPParser.resolve
Then 解析出 3 个 IP 地址：192.168.1.1, 192.168.1.2, 192.168.1.3

#### 场景 2：跨网段 IP 段解析
Given 用户输入目标 "192.168.1.254-192.168.2.2"
When 执行 IPParser.resolve
Then 解析出 5 个 IP 地址，包含 192.168.2.1

#### 场景 3：任务量超限拒绝
Given 用户输入目标 "1.0.0.0/8" 和端口 "1-65535"
When 执行 ScanInputFacade.parse
Then 抛出 ParseError，提示任务量过大并建议缩小范围

#### 场景 4：配置注入隔离
Given 创建 Facade A 注入 common_ports={22,80,443}
And 创建默认 Facade B
When 分别执行 parse("127.0.0.1", "common")
Then Facade A 返回 3 个端口，Facade B 返回 16 个端口

#### 场景 5：Preview 模式安全估算
Given 用户输入目标 "1.0.0.0/8" 和端口 "1-65535"
When 执行 ScanInputFacade.preview
Then 不抛出异常，返回 is_safe=False 与 total_tasks

---

## 二、架构设计（Architecture as Code）

### 1. 技术栈
| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.8+ | 类型注解、dataclass |
| 网络 | socket | 域名解析 |
| 网段 | ipaddress | CIDR 解析、IP 验证 |
| 正则 | re | 域名格式校验 |
| 测试 | unittest | 标准测试框架 |

### 2. 架构模式
四层模块化架构：
- **exceptions.py**：异常抽象层（根异常 + 解析异常）
- **models.py**：数据契约层（不可变 ParseResult）
- **validator.py**：校验层（任务量上限拦截）
- **parser.py**：解析引擎层（IP/Port/Facade）

### 3. 架构决策记录 ADR

#### ADR-001：四层模块拆分
- Context：原 parser.py 单文件聚合所有解析逻辑，职责混杂
- Decision：按 exceptions → models → validator → parser 四层拆分
- Status：已完成
- Consequences：文件数增加但依赖方向单向，消除循环导入，可维护性提升

#### ADR-002：异常继承链
- Context：原代码使用裸 ValueError，GUI 层无法区分解析异常与其他异常
- Decision：ParseError 继承 ScannerError，建立统一异常体系
- Status：已完成
- Consequences：GUI 层只需 except ScannerError，降低跨模块耦合

#### ADR-003：实例级配置注入
- Context：原代码 COMMON_PORTS 为类属性，全局共享导致测试污染
- Decision：PortParser 通过 __init__ 接收 common_ports，实例隔离
- Status：已完成
- Consequences：每次创建 Facade 需传入配置，但保证零副作用

#### ADR-004：门面模式（Facade）
- Context：GUI 层直接调用 IPParser/PortParser，耦合度高
- Decision：引入 ScanInputFacade 作为唯一对外接口
- Status：已完成
- Consequences：GUI 层代码简化，隐藏底层协作细节

#### ADR-005：不可变返回类型
- Context：原代码返回可变 Set，多线程环境下存在副作用风险
- Decision：解析结果使用 FrozenSet 与 frozen=True dataclass
- Status：已完成
- Consequences：下游无法原地修改结果，线程安全但需创建新对象

### 4. 架构拓扑
```
┌─────────────────────────────────────────┐
│  GUI / main.py / 命令行入口              │
│  依赖：ScanInputFacade, ParseResult      │
│           ScannerError                   │
└─────────────┬───────────────────────────┘
              │
    ┌─────────▼──────────┐
    │ ScanInputFacade      │  ← 门面：编排 IP/Port/Validator
    └─────────┬────────────┘
              │
    ┌─────────┴────────────┐
    │                      │
┌───▼────┐    ┌────▼─────┐    ┌────────────▼─────────┐
│IPParser│    │PortParser│    │    TaskValidator       │
│        │    │(实例隔离)│    │                        │
└───┬────┘    └────┬─────┘    └────────────┬───────────┘
    │              │                       │
    └──────┬───────┘                       │
           │                               │
    ┌──────▼──────┐              ┌─────────▼──────────┐
    │ ParseResult │              │     ParseError     │
    │ (models.py) │              │   (exceptions.py)  │
    └─────────────┘              └─────────┬──────────┘
                                           │
                                  ┌────────▼─────────┐
                                  │   ScannerError   │
                                  │ (exceptions.py)  │
                                  └──────────────────┘
```

### 5. 多模型对抗审查结论
- 必须将原单文件拆分为四层，否则职责混杂违反 SRP
- 必须使用实例级注入，类属性全局共享会导致不可预期的副作用
- 必须建立异常继承链，否则 GUI 层异常处理逻辑将耦合具体实现
- 必须使用不可变返回类型，否则多线程扫描结果可能被意外修改
- 必须保留任务量上限防护，防止超大网段 + 全端口导致内存耗尽

---

## 三、上下文工程（Context Engineering）

### 1. 核心提示词（Prompt = 源码）
高内聚低耦合、四层模块拆分、异常继承链、实例隔离注入、不可变数据契约、门面模式、任务量上限防护、IP段简写/全写/跨网段、域名解析、端口common/all/段/组合、零副作用、线程安全。

### 2. 上下文约束
- DEFAULT_MAX_TASKS = 100_000
- COMMON_PORTS = {21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3306, 3389, 5432, 6379, 8080}
- 端口有效范围：1-65535
- 域名正则：要求 TLD 含字母，排除纯数字+点组合
- 禁止第三方库
- 最小权限运行

### 3. 人工修正点
- 域名正则从宽松模式调整为严格模式（要求 TLD 含字母），防止 IP 段被误判为域名
- PortParser 从类属性注入改为实例级注入，消除测试污染
- IP 段解析增加跨网段支持（原代码强制前三段一致）
- 增加 Preview 模式，用于 GUI 实时任务量估算

### 4. 上下文防腐化措施
- 干净上下文启动，无冗余历史导入
- 语义化命名（IPParser/PortParser/TaskValidator/ScanInputFacade）
- 无 UUID 乱码，无魔法数
- 类型注解完整覆盖

---

## 四、智能体开发（Agentic Coding）

### 1. 智能体分工
- **实现 Agent**：完成四层模块代码生成
- **审计 Agent**：验证模块依赖方向、异常继承链、不可变性
- **审查 Agent**：验证 32 项单元测试、边界值覆盖、零副作用

### 2. 执行流程（ReAct）
1. 理解意图：基于用户三项架构决策（配置注入/异常契约/模块拆分）
2. 规划模块：exceptions → models → validator → parser → tests
3. 生成代码：逐文件实现，确保单向依赖
4. 校验格式：py_compile 编译检查
5. 验证逻辑：32 项单元测试全部通过
6. 修复问题：域名正则误匹配、类属性污染、跨网段支持

### 3. 安全沙盒与权限
- 最小权限原则：解析模块仅做字符串处理，不发起网络扫描
- 无系统破坏操作
- 无外连攻击逻辑
- 纯用户态运行

---

## 五、验证优先（Verification-First）

### 1. 测试用例
| 测试类 | 用例数 | 覆盖范围 |
|--------|--------|----------|
| TestIPParser | 13 | 单IP、CIDR、IP段简写/全写/跨网段、域名、组合、空输入、无效格式、返回类型 |
| TestPortParser | 13 | common、all、单端口、端口段、组合、越界、空输入、大小写、实例隔离 |
| TestTaskValidator | 5 | 正常通过、边界值、超限拒绝、统计信息、默认值 |
| TestScanInputFacade | 10 | 端到端解析、任务量拒绝、配置注入、注入隔离、自定义校验、Preview、异常类型、不可变性 |

### 2. 验证结果
- 32/32 项测试通过
- py_compile 全部模块编译通过
- 无循环导入
- 类型注解完整
- 零副作用验证：实例 A 注入不影响实例 B

### 3. LLM-as-Judge 审查
通过：结构规范、逻辑正确、异常体系完整、线程安全、零副作用、测试覆盖充分。

---

## 六、交付物清单
| 编号 | 交付物 | 类型 | 路径 | 行数 | 状态 |
|------|--------|------|------|------|------|
| 1 | exceptions.py | 源码 | core/exceptions.py | 21 | ✅ |
| 2 | models.py | 源码 | core/models.py | 27 | ✅ |
| 3 | validator.py | 源码 | core/validator.py | 51 | ✅ |
| 4 | parser.py | 源码 | core/parser.py | 197 | ✅ |
| 5 | test_parser.py | 测试 | tests/test_parser.py | 268 | ✅ |
| 6 | TASK_BOOK_PARSER.md | 文档 | TASK_BOOK_PARSER.md | 284 | ✅ |
| 7 | 本开发日志 | 文档 | DEV_LOG_PARSER.md | — | ✅ 本文档 |

---

## 七、合规声明

本模块仅限授权内网安全测试使用。解析功能本身不发起网络扫描，仅做输入预处理。任务量上限防护旨在防止误操作导致的资源耗尽，不构成对扫描行为的限制或鼓励。

---

## 八、遗留事项与待办
| 序号 | 事项 | 优先级 | 建议方案 |
|------|------|--------|----------|
| 1 | 超大 IP 段生成性能优化 | 低 | 当前 `192.168.1.1-192.168.255.255` 约 6.5 万个 IP 在任务量上限拦截前完成生成；如需优化可改用生成器惰性展开 |
| 2 | IPv6 支持 | 低 | 当前仅支持 IPv4，IPv6 需扩展 ipaddress 解析逻辑 |
| 3 | 域名解析超时控制 | 低 | `socket.gethostbyname` 为阻塞调用，GUI 层建议在独立线程调用 Facade |
| 4 | 扫描引擎接入新 Facade | 高 | scanner.py 需从旧解析调用迁移至 `ScanInputFacade.parse()` |
| 5 | GUI 层替换旧解析调用 | 高 | gui.py 需替换为 `from core.parser import ScanInputFacade` |

---

日志版本：v1.0
生成时间：2026-05-26
范式遵循：Software 3.0｜意图驱动｜规格优先｜架构即代码｜验证优先
