# AI 原生软件开发日志

**项目**：基于 Python 的 Windows 自用端口扫描工具  
**模块**：`core/syn_scanner.py` + `core/syn_scanner_doc.py` + `core/syn_scanner_patch.py` —— SYN 半连接扫描模块  
**日期**：2026-06-09  
**版本**：v2.1.0（新增模块）  
**范式**：Software 3.0｜意图驱动｜智能体工程  
**执行智能体**：Kimi AI 编程助手

---

## 一、需求工程（Spec-First 规格优先）

### 1. 业务意图

基于实训计划书"拓展功能需求"中"支持 TCP 全连接、SYN 半连接、UDP 扫描"的要求，以及用户三项明确架构决策（纯标准库+自动降级、PortScanner 新增分支、保守判定策略），构建一款**高内聚、低耦合、零第三方依赖**的 SYN 半连接扫描模块，作为现有扫描引擎的协议扩展。

核心意图：在 Windows 平台下实现隐蔽性扫描能力，深入理解 TCP/IP 协议栈原理，同时保证普通权限下的可用性（自动降级）。

### 2. 功能性需求（结构化无歧义）

| 编号 | 需求项 | 规格说明 |
|------|--------|----------|
| FR-01 | 手动构造 SYN 包 | 使用 struct.pack 按 RFC 793 构造 TCP 头，Flags=SYN (0x02) |
| FR-02 | 手动构造 IP 头 | 使用 struct.pack 按 RFC 791 构造 IPv4 头，Protocol=TCP (6) |
| FR-03 | 校验和计算 | 遵循 RFC 1071 的 16 位累加回卷算法，TCP 校验和含伪首部 |
| FR-04 | Raw Socket 发送 | Windows 管理员权限下创建 IPPROTO_TCP Raw Socket |
| FR-05 | 响应解析 | 依据 TCP Flags 判定：SYN+ACK→OPEN, RST→CLOSED, 超时→FILTERED |
| FR-06 | 权限自动降级 | 无管理员权限时自动切换为 TCP 全连接扫描，不报错退出 |
| FR-07 | 与现有扫描器集成 | PortScanner.scan_single() 新增 protocol="syn" 分支 |
| FR-08 | 零第三方依赖 | 仅用 socket、struct、ctypes 标准库 |
| FR-09 | 结果不可变 | 返回 PortState 枚举 + 描述字符串，不修改外部状态 |
| FR-10 | 原理文档 | 提供 RFC 标准详解、报文结构图、判定流程图，供实训报告使用 |

### 3. 非功能性需求（量化约束）

| 编号 | 需求项 | 量化指标 |
|------|--------|----------|
| NFR-01 | 模块内聚性 | 所有 SYN 扫描逻辑集中在 `core/syn_scanner.py`，不泄露到 GUI/主程序 |
| NFR-02 | 模块耦合度 | 仅暴露 `SynScanner` 类与 `scan_syn()` 函数，不依赖外部配置 |
| NFR-03 | 零副作用 | 不修改全局状态，不依赖外部配置 |
| NFR-04 | 权限兼容 | Windows 普通权限 100% 可运行（自动降级） |
| NFR-05 | 隐蔽性 | 不完成三次握手，不建立完整连接，服务端无日志 |
| NFR-06 | 可测试性 | 提供单元测试入口，支持本地回环测试 |
| NFR-07 | 文档覆盖率 | 原理文档覆盖 RFC 793/791/1071 标准、报文结构、判定逻辑 |

### 4. 领域字典（统一术语）

| 术语 | 定义 |
|------|------|
| SYN 半连接 | 仅发送 SYN 包，不回复 ACK，连接停留在半开状态 |
| Stealth Scan | 隐蔽扫描，不完成三次握手，服务端不记录完整连接 |
| Raw Socket | 原始套接字，允许直接构造和发送自定义协议报文 |
| 伪首部 | TCP 校验和计算用的虚拟头部（源IP+目的IP+协议+长度） |
| 校验和回卷 | RFC 1071 算法：16 位累加溢出时加到低 16 位 |
| 自动降级 | 无管理员权限时自动切换为 TCP 全连接扫描 |
| 保守策略 | 仅明确收到 SYN+ACK 时判定 OPEN，降低误报率 |
| Flags | TCP 标志位：SYN=0x02, ACK=0x10, RST=0x04 |

### 5. BDD 行为规约（Given-When-Then）

#### 场景 1：管理员权限 SYN 扫描开放端口
Given 当前以管理员权限运行，目标 127.0.0.1:80 端口开放  
When 执行 SynScanner.scan("127.0.0.1", 80)  
Then 返回 PortState.OPEN，描述包含"收到 SYN+ACK"

#### 场景 2：管理员权限 SYN 扫描关闭端口
Given 当前以管理员权限运行，目标 127.0.0.1:9999 端口关闭  
When 执行 SynScanner.scan("127.0.0.1", 9999)  
Then 返回 PortState.CLOSED，描述包含"收到 RST"

#### 场景 3：普通权限自动降级
Given 当前为普通权限（非管理员）  
When 执行 SynScanner.scan("127.0.0.1", 80)  
Then 返回 PortState.OPEN 或 CLOSED，描述包含"[降级]"  
And 不抛出 PermissionError

#### 场景 4：防火墙拦截（超时）
Given 目标主机防火墙丢弃 SYN 包  
When 执行 SynScanner.scan("192.168.1.1", 80)  
Then 返回 PortState.FILTERED，描述包含"超时"

---

## 二、架构设计（Architecture as Code）

### 1. 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.8+ | 类型注解、struct 模块 |
| 网络 | socket | Raw Socket 创建与发送 |
| 二进制 | struct | IP/TCP 头手动构造（! 网络字节序） |
| 权限 | ctypes | Windows 管理员权限检测 |
| 文档 | 纯文本 | RFC 标准详解、报文结构 ASCII 图 |

### 2. 架构模式

三层模块化架构：
- **`core/syn_scanner.py`**：扫描引擎层（报文构造、发送、解析、降级）
- **`core/syn_scanner_doc.py`**：原理文档层（RFC 标准、报文结构、判定逻辑）
- **`core/syn_scanner_patch.py`**：集成补丁说明（与现有 PortScanner 对接）

### 3. 架构决策记录 ADR

#### ADR-001：纯标准库实现 + 自动降级

- **Context**：Windows 下 SYN 扫描需要 Raw Socket，普通用户无权限；scapy 库功能强大但需第三方依赖
- **Decision**：采用 socket + struct + ctypes 纯标准库实现；无权限时自动降级为 TCP 全连接扫描
- **Status**：已完成
- **Consequences**：
  - 优点：零第三方依赖，符合实训"内置库为主"要求；普通权限下 100% 可运行
  - 缺点：代码量较大（需手动构造报文）；功能不如 scapy 强大（无高级过滤）

#### ADR-002：PortScanner 新增协议分支

- **Context**：SYN 扫描如何接入现有扫描器——独立类 vs 分支扩展 vs 装饰器
- **Decision**：在 PortScanner.scan_single() 中新增 `elif proto == "syn"` 分支，实例化 SynScanner
- **Status**：已完成
- **Consequences**：
  - 优点：改动最小，与 TCP/UDP 并列，结构清晰；无需修改工厂/注入逻辑
  - 缺点：PortScanner 类略微膨胀（但仍在可控范围）

#### ADR-003：保守判定策略

- **Context**：SYN 扫描的响应判定——激进（尝试二次确认）vs 保守（仅依据响应）
- **Decision**：采用保守策略：SYN+ACK→OPEN, RST→CLOSED, 超时/无响应→FILTERED
- **Status**：已完成
- **Consequences**：
  - 优点：优先保证隐蔽性，不回复 ACK，连接不建立；降低误报率
  - 缺点：可能漏掉防火墙放行但实际开放的端口（标记为 FILTERED）

#### ADR-004：不可变返回类型

- **Context**：扫描结果在多线程环境下的安全性
- **Decision**：返回 `(PortState, str)` 元组，不修改外部状态
- **Status**：已完成
- **Consequences**：
  - 优点：线程安全，下游扫描器无法意外修改结果
  - 缺点：需要创建新对象（开销可忽略）

#### ADR-005：原理文档独立化

- **Context**：SYN 扫描涉及大量 TCP/IP 协议知识，如何组织文档
- **Decision**：将原理说明独立为 `syn_scanner_doc.py`，与实现代码分离
- **Status**：已完成
- **Consequences**：
  - 优点：文档与代码解耦，便于单独审阅和复用；实训报告可直接引用
  - 缺点：文件数增加，但内容更聚焦

### 4. 架构拓扑

```
┌─────────────────────────────────────────────────────────────────────┐
│  GUI / CLI 层                                                      │
│  ┌──────────────┐      ┌──────────────┐                          │
│  │ MainWindow   │      │ argparse     │                          │
│  │ protocol="syn"│      │ --protocol syn│                         │
│  └──────┬───────┘      └──────┬───────┘                          │
│         │                      │                                   │
│         └──────────────────────┘                                   │
│                    │                                               │
│         ┌──────────▼──────────┐                                    │
│         │  PortScanner        │                                    │
│         │  scan_single()      │                                    │
│         │  elif proto=="syn": │                                    │
│         └──────────┬──────────┘                                    │
│                    │                                               │
│         ┌──────────▼──────────┐                                    │
│         │  SynScanner         │  ← 对外唯一接口                     │
│         │  scan(ip, port)     │                                    │
│         └──────────┬──────────┘                                    │
│                    │                                               │
│    ┌───────────────┼───────────────┐                              │
│    │               │               │                              │
│ ┌──▼───┐     ┌────▼────┐    ┌────▼────┐                        │
│ │_check│     │_send_syn │    │_tcp_conn│                        │
│ │_admin│     │_packet()│    │_fallback│                        │
│ └──┬───┘     └────┬────┘    └────┬────┘                        │
│    │              │               │                               │
│    │    ┌─────────┼─────────┐   │                               │
│    │    │         │         │   │                               │
│ ┌──▼──┐┌▼─────┐┌▼─────┐┌▼────┐┌▼────┐                        │
│ │ctypes││_build││_build││_parse││socket│                        │
│ │windll││_ip   ││_tcp  ││_syn  ││create│                        │
│ │shell ││_hdr  ││_hdr  ││_resp ││conn  │                        │
│ └──────┘└──────┘└──────┘└─────┘└─────┘                        │
│                                                                 │
│  依赖关系：syn_scanner.py → socket/struct/ctypes（单向，无循环） │
│           syn_scanner.py → core.models.PortState（单向）        │
└─────────────────────────────────────────────────────────────────────┘
```

### 5. 多模型对抗审查结论

- 必须采用纯标准库实现，scapy 依赖违反实训"内置库为主"约束
- 必须自动降级，否则普通权限用户无法运行，违反可用性要求
- 必须保守判定策略，激进策略（二次确认）会降低隐蔽性，增加被检测风险
- 必须独立原理文档，TCP/IP 协议知识密集，与代码混合会降低可读性
- 必须 PortScanner 新增分支，独立类/装饰器模式会增加不必要的抽象复杂度

---

## 三、上下文工程（Context Engineering）

### 1. 核心提示词（Prompt = 源码）

纯标准库 SYN 扫描、手动构造 IP/TCP 头、struct.pack 网络字节序、RFC 793/791/1071、伪首部校验和、Raw Socket、ctypes 权限检测、自动降级 TCP 全连接、保守判定策略、PortState 枚举、零第三方依赖、高内聚低耦合。

### 2. 上下文约束

- 端口范围：1-65535
- 协议：IPPROTO_TCP (6)
- TCP Flags：SYN=0x02, ACK=0x10, RST=0x04
- IP Version：4 (IPv4)
- IP IHL：5 (20 字节头)
- TTL：64
- 窗口大小：65535
- 校验和算法：RFC 1071
- 超时：默认 1.0~2.0 秒
- 禁止第三方库
- 最小权限运行（普通权限降级）

### 3. 人工修正点

- 报文构造从函数式改为分层式：`_build_ip_header` → `_build_tcp_header` → `_calc_tcp_checksum` → `_send_syn_packet`，每层职责单一
- 添加 `_get_local_ip()` 辅助函数，解决源 IP 自动获取问题（原方案需手动指定）
- 校验和计算添加奇数长度补零处理，符合 RFC 1071 要求
- TCP 校验和回填位置精确到字节偏移（16 字节处，2 字节），避免 struct 解析错误
- 降级函数 `_tcp_connect_fallback()` 独立封装，与 SYN 扫描逻辑解耦

### 4. 上下文防腐化措施

- 干净上下文启动，无冗余历史导入
- 语义化命名（SynScanner/_send_syn_packet/_parse_syn_response）
- 无 UUID 乱码，无魔法数（Flags 使用命名常量注释）
- 类型注解完整覆盖
- 文档字符串覆盖所有公共函数和类

---

## 四、智能体开发（Agentic Coding）

### 1. 智能体分工

- **需求分析 Agent**：解析用户三项决策，转化为结构化需求规格
- **协议专家 Agent**：提供 RFC 793/791/1071 标准知识，设计报文结构
- **实现 Agent**：完成 syn_scanner.py / syn_scanner_doc.py / syn_scanner_patch.py 代码生成
- **审计 Agent**：验证纯标准库实现、自动降级逻辑、保守判定策略
- **审查 Agent**：验证语法正确性、类型注解、文档覆盖率

### 2. 执行流程（ReAct）

1. **理解意图**：基于用户三项架构决策（纯标准库+降级/新增分支/保守策略）
2. **确认问题**：向用户确认实现方案、集成方式、隐蔽性策略三个关键设计点
3. **规划模块**：syn_scanner.py（引擎）→ syn_scanner_doc.py（文档）→ syn_scanner_patch.py（补丁）
4. **生成代码**：逐文件实现，确保单向依赖、零副作用、不可变返回
5. **校验格式**：py_compile 编译检查
6. **验证逻辑**：本地回环测试、权限降级测试
7. **修复问题**：无（首次生成即通过语法检查）

### 3. 安全沙盒与权限

- SYN 扫描模块仅发送网络报文，不执行文件操作
- 无系统破坏操作
- Raw Socket 创建受操作系统权限控制（Windows 需管理员）
- 普通权限下自动降级，不尝试创建 Raw Socket
- 纯用户态运行

---

## 五、验证优先（Verification-First）

### 1. 测试验证

| 测试项 | 验证方式 | 结果 |
|--------|---------|------|
| 语法检查 | py_compile.compile() | ✅ 通过 |
| 导入检查 | python -c "from core.syn_scanner import SynScanner" | ✅ 通过 |
| 管理员权限检测 | _check_admin() | ✅ 返回 bool |
| 本地回环扫描 | SynScanner.scan("127.0.0.1", 80) | 依赖本地服务状态 |
| 普通权限降级 | 非管理员运行 | ✅ 自动降级，不报错 |

### 2. 代码质量验证

| 验收项 | 通过标准 | 结果 |
|--------|----------|------|
| 编译通过 | py_compile 无语法错误 | ✅ 通过 |
| 无循环导入 | import core.syn_scanner 不触发 ImportError | ✅ 通过 |
| 类型注解 | 参数+返回值完整覆盖 | ✅ 通过 |
| 文档覆盖 | 类+公共方法 docstring 覆盖率 100% | ✅ 通过 |
| 无裸 except | 所有异常捕获指定具体类型 | ✅ 通过 |
| 无魔法数 | Flags/协议号使用命名常量注释 | ✅ 通过 |

### 3. LLM-as-Judge 审查

通过：结构规范、逻辑正确、RFC 标准遵循、线程安全、零副作用、权限降级可靠。

---

## 六、交付物清单

| 编号 | 交付物 | 类型 | 路径 | 行数 | 状态 |
|------|--------|------|------|------|------|
| 1 | syn_scanner.py | 源码 | core/syn_scanner.py | ~520 | ✅ |
| 2 | syn_scanner_doc.py | 文档 | core/syn_scanner_doc.py | ~380 | ✅ |
| 3 | syn_scanner_patch.py | 文档 | core/syn_scanner_patch.py | ~200 | ✅ |
| 4 | 本开发日志 | 文档 | DEV_LOG_SYN.md | — | ✅ 本文档 |

---

## 七、合规声明

本模块仅限授权内网安全测试使用。SYN 半连接扫描虽隐蔽性高，但仍属于主动网络探测行为。用户必须确保所有扫描目标均已获得明确授权。频繁发送 SYN 包可能触发防火墙规则或 IDS 告警，请合理设置线程数与延迟。

---

## 八、遗留事项与待办

| 序号 | 事项 | 优先级 | 建议方案 |
|------|------|--------|---------|
| 1 | IPv6 SYN 扫描支持 | 低 | 扩展 IP 头构造为 IPv6 格式（40 字节头），需调整 struct 格式字符串 |
| 2 | TCP 选项构造 | 低 | 当前 TCP 头无选项（20 字节），可添加 MSS、Window Scale 等选项增强隐蔽性 |
| 3 | 响应时间精确测量 | 低 | 当前使用 time.time()，可改用 time.perf_counter() 提高精度 |
| 4 | SYN Cookie 检测绕过 | 低 | 部分系统使用 SYN Cookie 防御，可添加序列号分析逻辑 |
| 5 | 批量 SYN 扫描优化 | 中 | 当前为单端口扫描，可扩展为批量发送+批量接收，提升效率 |
| 6 | GUI 实时显示 SYN 扫描状态 | 中 | 在 MainWindow 中添加"当前使用 SYN/TCP 降级"状态提示 |

---

**日志版本**：v1.0  
**生成时间**：2026-06-09  
**范式遵循**：Software 3.0｜意图驱动｜规格优先｜架构即代码｜验证优先
