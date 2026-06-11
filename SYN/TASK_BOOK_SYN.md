# 代码生成指令任务书

## 一、任务基本信息
| 项目 | 内容 |
|------|------|
| 任务名称 | SYN 半连接扫描模块开发 — 高内聚低耦合协议栈实现 |
| 执行对象 | Kimi AI 编程助手 |
| 生成目标 | core/syn_scanner.py、core/syn_scanner_doc.py、core/syn_scanner_patch.py |
| 依据资料 | 《基于Python的Windows自用端口扫描工具开发实训计划书》功能模块字典、用户三项架构决策 |
| 任务性质 | 协议栈底层实现、隐蔽扫描技术、权限兼容设计、工程化升级 |
| 使用场景 | 授权内网安全巡检、隐蔽端口探测、TCP/IP 协议教学演示、实训课程交付 |

---

## 二、代码生成总体目标

基于实训计划书"拓展功能需求"中"支持 TCP 全连接、SYN 半连接、UDP 扫描"的要求，以及用户三项明确架构决策（纯标准库手动构造 SYN 包+自动降级、PortScanner 新增协议分支、保守判定策略），生成可直接集成到现有项目的 SYN 半连接扫描模块源码，满足以下核心指标：

1. **零第三方依赖**：仅使用 Python 3.8+ 内置模块（socket、struct、ctypes）
2. **管理员权限执行 SYN 扫描**：Windows 下创建 Raw Socket（IPPROTO_TCP）发送原始 SYN 包
3. **普通权限自动降级**：无管理员权限时自动切换为 TCP 全连接扫描，不报错退出
4. **手动构造协议报文**：使用 struct.pack 按 RFC 793/791 格式构造 TCP/IP 头
5. **RFC 1071 校验和**：16 位累加回卷算法，TCP 校验和含伪首部
6. **保守判定策略**：SYN+ACK→OPEN、RST→CLOSED、超时→FILTERED
7. **高内聚低耦合**：所有 SYN 逻辑集中在 syn_scanner.py，仅暴露 SynScanner 类
8. **与现有扫描器集成**：PortScanner.scan_single() 新增 protocol="syn" 分支
9. **完整原理文档**：RFC 标准详解、报文结构 ASCII 图、判定流程图
10. **6 步集成补丁**：提供与 scanner.py / main_window.py / main.py 的对接说明

---

## 三、逐文件生成指令

### 文件一：core/syn_scanner.py（SYN 扫描引擎层）

#### 3.1.1 生成指令
生成 SYN 半连接扫描核心引擎模块，职责为基于 Python 标准库实现 TCP SYN 隐蔽扫描。手动构造 IP 头+TCP 头，发送原始 SYN 包，解析响应判定端口状态。无管理员权限时自动降级为 TCP 全连接扫描。

#### 3.1.2 必须包含的内容

| 名称 | 类型 | 功能规格 | 异常处理 |
|------|------|----------|----------|
| `_checksum(source)` | 函数 | RFC 1071 校验和计算：16位累加、溢出回卷、取反 | 无异常（纯数学运算） |
| `_build_ip_header(src_ip, dst_ip, payload_len)` | 函数 | 构造20字节IPv4头：Version=4, IHL=5, TTL=64, Protocol=TCP(6) | 无异常 |
| `_build_tcp_header(src_port, dst_port, seq_num, ...)` | 函数 | 构造20字节TCP头：Flags=SYN(0x02), Window=65535 | 无异常 |
| `_build_pseudo_header(src_ip, dst_ip, tcp_len)` | 函数 | 构造12字节伪首部（源IP+目的IP+保留+协议+长度） | 无异常 |
| `_calc_tcp_checksum(src_ip, dst_ip, tcp_header, data)` | 函数 | 计算TCP校验和（伪首部+TCP头+数据） | 无异常 |
| `_get_local_ip()` | 函数 | 获取本机出口IP：UDP连接外部地址法，失败回退127.0.0.1 | 捕获所有异常 |
| `_send_syn_packet(dst_ip, dst_port, timeout)` | 函数 | 创建Raw Socket、组装报文、发送SYN、接收响应 | PermissionError/OSError |
| `_parse_syn_response(response)` | 函数 | 解析响应报文：跳过IP头、提取TCP Flags、判定状态 | 无异常（防御性校验） |
| `_tcp_connect_fallback(ip, port, timeout)` | 函数 | TCP全连接降级：socket.create_connection | socket.timeout/ConnectionRefusedError/OSError |
| `_check_admin()` | 函数 | 跨平台权限检测：Windows(ctypes)/Linux(os.getuid) | 捕获所有异常 |
| `SynScanner` | 类 | 对外统一接口，封装完整扫描流程 | 内部消化所有异常 |
| `__init__(timeout)` | 方法 | 初始化超时、检测管理员权限 | — |
| `scan(ip, port)` | 方法 | 执行扫描：有权限→SYN扫描，无权限→TCP降级 | 返回(PortState, str) |
| `scan_syn(ip, port, timeout)` | 函数 | 便捷函数，与scan_tcp/scan_udp对称 | — |

#### 3.1.3 TCP 头构造详细规格

**结构（20字节，无选项）：**

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Source Port          |       Destination Port        |  ← 2+2字节
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number                        |  ← 4字节
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Acknowledgment Number                      |  ← 4字节
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Data |           |U|A|P|R|S|F|                               |
| Offset| Reserved  |R|C|S|S|Y|I|            Window             |  ← 1+1+2字节
|       |           |G|K|H|T|N|N|                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Checksum            |         Urgent Pointer        |  ← 2+2字节
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

**字段填充值：**

| 字段 | 值 | 说明 |
|------|-----|------|
| Source Port | random(30000, 60000) | 随机源端口 |
| Destination Port | 目标端口 | 用户指定 |
| Sequence Number | random(0, 0xFFFFFFFF) | 随机序列号 |
| Ack Number | 0 | SYN包无确认号 |
| Data Offset | 5 (0x50) | 头长20字节 → 5×4=20 |
| Reserved | 0 | 保留位 |
| Flags | 0x02 | 仅SYN位 |
| Window | 65535 | 最大窗口 |
| Checksum | 计算后回填 | 偏移16字节处 |
| Urgent Pointer | 0 | 无紧急数据 |

#### 3.1.4 IP 头构造详细规格

**结构（20字节，无选项）：**

| 字段 | 值 | 说明 |
|------|-----|------|
| Version | 4 | IPv4 |
| IHL | 5 | 头长20字节 |
| TOS | 0 | 普通服务 |
| Total Length | 40 | IP头(20)+TCP头(20) |
| Identification | random(0, 65535) | 随机标识 |
| Flags | 0x4000 | DF=1（不分片） |
| TTL | 64 | 生存时间 |
| Protocol | 6 | TCP |
| Header Checksum | 计算后回填 | — |
| Source IP | _get_local_ip() | 本机出口IP |
| Destination IP | 目标IP | 用户指定 |

#### 3.1.5 响应判定规格（保守策略）

| 响应类型 | TCP Flags | 端口状态 | 说明 |
|---------|-----------|---------|------|
| SYN + ACK | 0x12 (SYN+ACK) | **OPEN** | 端口开放，服务就绪 |
| RST | 0x04 (RST) | **CLOSED** | 端口关闭，无服务监听 |
| 无响应/超时 | — | **FILTERED** | 防火墙丢弃或主机离线 |
| 其他/异常 | — | **ERROR** | 网络错误或其他异常 |

**判定流程：**

```
发送 SYN 包
    │
    ▼
等待响应（超时1~2秒）
    │
    ├──────→ 收到 SYN+ACK ──→ 端口 OPEN（不回复ACK）
    │
    ├──────→ 收到 RST ──────→ 端口 CLOSED
    │
    └──────→ 超时/无响应 ────→ 端口 FILTERED
```

#### 3.1.6 降级策略规格

**触发条件：** `_check_admin()` 返回 False

**降级流程：**
1. 不尝试创建 Raw Socket
2. 直接调用 `_tcp_connect_fallback(ip, port, timeout)`
3. 使用标准 `socket.create_connection()`
4. 连接成功 → OPEN，描述含"[降级]"
5. 连接拒绝 → CLOSED，描述含"[降级]"
6. 超时 → FILTERED，描述含"[降级]"

#### 3.1.7 约束条件
- 仅使用 Python 标准库：socket、struct、ctypes、os、sys、random、time
- 禁止第三方库（scapy、winpcap 等）
- 所有异常内部消化，返回 `(PortState, str)` 元组
- 不修改全局状态，不依赖外部配置
- 报文构造使用网络字节序（`!` 格式字符）
- 校验和计算必须包含伪首部（RFC 793 要求）
- 奇数长度数据需补零后再计算校验和

---

### 文件二：core/syn_scanner_doc.py（原理文档层）

#### 3.2.1 生成指令
生成 SYN 半连接扫描技术原理说明文档，职责为提供完整的 TCP/IP 协议栈知识讲解，供实训报告直接使用。包含 RFC 标准引用、报文结构 ASCII 图、判定流程图、与全连接扫描对比。

#### 3.2.2 必须包含的内容

| 章节 | 内容 |
|------|------|
| 一、为什么需要 SYN 扫描 | 全连接扫描的缺陷（日志留痕、IDS检测）、SYN扫描的优势（隐蔽性高） |
| 二、三次握手 vs 半连接对比 | ASCII 时序图、日志记录对比、隐蔽性对比、Banner获取对比 |
| 三、TCP 报文结构详解 | RFC 793 TCP头20字节结构、Flags定义表、IP头20字节结构 |
| 四、校验和计算算法 | RFC 1071 算法步骤、Python实现代码、TCP伪首部结构 |
| 五、响应判定逻辑 | 保守策略表格、判定流程图、各状态说明 |
| 六、Windows 权限机制 | Raw Socket限制、权限检测方法、降级策略说明 |
| 七、实现方案对比 | 纯标准库 vs scapy vs Nmap 对比表、本模块选型理由 |
| 八、与现有扫描器集成 | 集成位置、调用链、代码示例 |
| 九、合规与风险提示 | 法律合规、技术风险、使用建议 |

#### 3.2.3 约束条件
- 文档为 Python 多行字符串（`"""` 包裹），可直接作为模块文件导入
- 所有 RFC 标准必须准确引用（793、791、1071）
- 报文结构使用 ASCII 艺术图，清晰展示位偏移
- 包含完整的判定流程图（文字版）
- 合规声明必须醒目

---

### 文件三：core/syn_scanner_patch.py（集成补丁说明）

#### 3.3.1 生成指令
生成 SYN 半连接扫描与现有代码的集成补丁说明文档，职责为指导开发者在 scanner.py、main_window.py、main.py 中接入 SYN 扫描功能，无需重构现有代码结构。

#### 3.3.2 必须包含的修改位置

| 编号 | 修改位置 | 操作 | 代码片段 |
|------|---------|------|---------|
| 1 | scanner.py 导入区 | 新增导入 | `from core.syn_scanner import SynScanner` |
| 2 | scanner.py scan_single() | 新增分支 | `elif proto == "syn": syn_scanner = SynScanner(...)` |
| 3 | main_window.py 协议下拉框 | 添加选项 | `self.cb_proto.addItems(["tcp", "udp", "syn"])` |
| 4 | main_window.py 启动检测 | 权限提示 | `if proto == "syn" and not _check_admin(): QMessageBox.warning(...)` |
| 5 | main.py CLI 参数 | 添加 choices | `choices=["tcp", "udp", "syn"]` |
| 6 | config.py 协议列表 | 可选添加 | `SCAN_PROTOCOLS = ["tcp", "udp", "syn"]` |

#### 3.3.3 必须包含的集成后流程

```
用户选择协议 "syn"
    ↓
GUI/CLI → ScanConfig(protocol="syn")
    ↓
PortScanner.scan_single(ip, port, "syn")
    ↓
SynScanner.scan(ip, port)
    ↓
_check_admin()
    ├─────→ [有权限] → _send_syn_packet(ip, port)
    │                    → 构造 IP 头 (20 字节)
    │                    → 构造 TCP 头 (20 字节, Flags=SYN)
    │                    → 计算 TCP 校验和（含伪首部）
    │                    → 创建 Raw Socket (IPPROTO_TCP)
    │                    → 发送完整报文
    │                    → 接收响应
    │                    → _parse_syn_response()
    │                        → SYN+ACK → OPEN
    │                        → RST → CLOSED
    │                        → 超时 → FILTERED
    │
    └─────→ [无权限] → _tcp_connect_fallback(ip, port)
                         → 标准 TCP socket.connect()
                         → 连接成功 → OPEN [降级标记]
                         → 连接拒绝 → CLOSED [降级标记]
                         → 超时 → FILTERED [降级标记]
    ↓
返回 ScanResult(state=OPEN/CLOSED/FILTERED/ERROR)
    ↓
GUI 表格展示结果（绿色=OPEN，白色=CLOSED，黄色=FILTERED，红色=ERROR）
```

#### 3.3.4 约束条件
- 修改步骤编号清晰，每步包含：位置、操作、代码片段
- 提供完整的 scan_single() 方法结构示例
- 包含技术亮点说明和注意事项
- 包含测试验证建议

---

## 四、技术约束与规范

### 4.1 语言与环境约束
| 约束项 | 要求 |
|--------|------|
| Python 版本 | 3.8+ |
| 第三方依赖 | 禁止（仅 socket、struct、ctypes、os、sys、random、time） |
| 运行权限 | 管理员权限（SYN扫描）/ 普通权限（自动降级） |
| 操作系统 | Windows 10/11（Raw Socket限制）/ Linux（root权限） |

### 4.2 代码风格约束
| 项 | 规范 |
|----|------|
| 函数/变量 | 小写+下划线 |
| 类 | 大驼峰 |
| 常量 | 全大写（如 SYN_FLAG = 0x02） |
| 私有方法 | 单下划线前缀 |
| 文档字符串 | 类与公共方法必须包含，说明参数、返回值、异常 |
| 类型注解 | 完整（参数+返回值） |
| 二进制操作 | struct.pack 使用 `!` 网络字节序 |

### 4.3 架构约束
| 约束项 | 要求 |
|--------|------|
| 模块依赖方向 | syn_scanner.py → socket/struct/ctypes（单向）→ core.models.PortState（单向）→ scanner.py（被导入） |
| 对外暴露 | 仅 `SynScanner` 类与 `scan_syn()` 函数 |
| 配置注入 | 无外部配置，仅 timeout 参数 |
| 返回类型 | `(PortState, str)` 元组 |
| 异常传播 | 所有异常内部消化，不向上抛出 |
| 状态管理 | 不修改全局状态，实例级 _has_admin 标记 |

---

## 五、质量标准

### 5.1 功能质量
| 验收项 | 通过标准 |
|--------|----------|
| 导入无异常 | `python -c "from core.syn_scanner import SynScanner"` 正常退出 |
| 管理员权限检测 | `_check_admin()` 返回正确布尔值 |
| 本地回环扫描 | `SynScanner.scan("127.0.0.1", 80)` 返回 OPEN/CLOSED/FILTERED |
| 普通权限降级 | 非管理员运行不抛 PermissionError，结果含"[降级]" |
| 超时判定 | 扫描不存在主机返回 FILTERED |
| 校验和计算 | IP头+TCP头校验和计算结果正确（可通过Wireshark验证） |

### 5.2 代码质量
| 验收项 | 通过标准 |
|--------|----------|
| 编译通过 | py_compile 无语法错误 |
| 无循环导入 | `import core.syn_scanner` 不触发 ImportError |
| 类型注解 | 参数+返回值完整覆盖 |
| 文档覆盖 | 类+公共方法 docstring 覆盖率 100% |
| 无裸 except | 所有异常捕获指定具体类型 |
| 无魔法数 | Flags、协议号使用命名常量注释 |
| 字节序正确 | struct.pack 使用 `!` 网络字节序 |

### 5.3 文档质量
| 验收项 | 通过标准 |
|--------|----------|
| RFC 引用准确 | 793(TCP)、791(IP)、1071(Checksum) 标准正确 |
| 报文结构清晰 | ASCII 图展示位偏移和字段长度 |
| 判定流程完整 | 包含 OPEN/CLOSED/FILTERED/ERROR 全路径 |
| 集成步骤清晰 | 6 步修改，每步含位置、操作、代码 |

---

## 六、交付物清单
| 编号 | 交付物 | 类型 | 路径 | 代码行数 | 说明 |
|------|--------|------|------|----------|------|
| 1 | syn_scanner.py | 源码 | core/syn_scanner.py | ~520 | SYN 扫描引擎层 |
| 2 | syn_scanner_doc.py | 文档 | core/syn_scanner_doc.py | ~380 | 原理说明文档（RFC标准） |
| 3 | syn_scanner_patch.py | 文档 | core/syn_scanner_patch.py | ~200 | 集成补丁说明（6步接入） |
| 4 | 本指令任务书 | 文档 | TASK_BOOK_SYN.md | — | 规格、约束、标准 |

---

## 七、执行规范
1. 严格依据用户三项架构决策（纯标准库+降级/新增分支/保守策略）逐项实现
2. 保持与现有扫描引擎（scanner.py）、GUI界面（main_window.py）的接口兼容
3. 仅做端口探测，不实现攻击、破解功能
4. 输出正式、清晰，可直接用于实训报告代码章节
5. 完成后必须验证：编译通过、导入无异常、权限检测正确、降级可靠

---

## 八、架构决策记录（ADR）

### ADR-001：纯标准库实现 + 自动降级
- **决策**：采用 socket + struct + ctypes 纯标准库实现；无权限时自动降级为 TCP 全连接扫描
- **理由**：符合实训"内置库为主"要求；普通权限下 100% 可运行
- **影响**：代码量较大（需手动构造报文），但零依赖、可控、便于学习

### ADR-002：PortScanner 新增协议分支
- **决策**：在 PortScanner.scan_single() 中新增 `elif proto == "syn"` 分支
- **理由**：改动最小，与 TCP/UDP 并列，结构清晰；无需修改工厂/注入逻辑
- **影响**：PortScanner 类略微膨胀，但仍在可控范围

### ADR-003：保守判定策略
- **决策**：SYN+ACK→OPEN, RST→CLOSED, 超时→FILTERED
- **理由**：优先保证隐蔽性，不回复 ACK，连接不建立；降低误报率
- **影响**：可能漏掉防火墙放行但实际开放的端口（标记为 FILTERED）

### ADR-004：不可变返回类型
- **决策**：返回 `(PortState, str)` 元组，不修改外部状态
- **理由**：线程安全，下游扫描器无法意外修改结果
- **影响**：需要创建新对象（开销可忽略）

### ADR-005：原理文档独立化
- **决策**：将原理说明独立为 syn_scanner_doc.py，与实现代码分离
- **理由**：文档与代码解耦，便于单独审阅和复用；实训报告可直接引用
- **影响**：文件数增加，但内容更聚焦

---

## 九、合规声明

本模块仅限授权内网安全测试使用。SYN 半连接扫描虽隐蔽性高，但仍属于主动网络探测行为。用户必须确保所有扫描目标均已获得明确授权。频繁发送 SYN 包可能触发防火墙规则或 IDS 告警，请合理设置线程数与延迟。

---

**文档版本**: v1.0  
**编制日期**: 2026-06-09  
**依据标准**: RFC 793 (TCP), RFC 791 (IP), RFC 1071 (Checksum), 《基于Python的Windows自用端口扫描工具开发实训计划书》
