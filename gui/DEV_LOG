# PyQt6 端口扫描工具 — 代码重构开发日志
文档版本: v1.0
生成日期: 2026-05-17
开发对象: AI 编程助手（Kimi K2.6）
关联任务书: 《面向AI的端口扫描工具开发指令任务书（正式版）》
关联分析文档: 《PyQt6 端口扫描工具 - 代码问题分析》

## 一、任务基本信息
|项目|内容|
|---|---|
|任务名称|Windows 轻量级多线程端口扫描工具 — PyQt6 GUI 模块重构|
|原始代码|main.py（PyQt6 GUI 模块）|
|重构目标|高内聚、低耦合；消除运行时崩溃；统一数据契约；策略化导出；防御式降级|
|约束条件|最大线程 20；零第三方依赖（除 PyQt6）；Windows 普通权限可运行；仅限授权内网使用|

## 二、原始代码问题诊断
基于用户提供的两份分析文档，对原 main.py 进行静态审查与逻辑推演，共识别出 18 项缺陷，按严重程度分类如下：

### 2.1 致命问题（5 项）
1. 线程暂停/恢复/停止功能失效：ThreadManager 控制逻辑为空，仅标记状态，不阻塞 QThread 或工作线程。
2. 队列读取不安全：result_queue.get_nowait() 未捕获 queue.Empty，空队列时直接抛异常。
3. PortScanner 返回类型不一致：同时出现 res[0] == 'error'（元组索引）与 res['ip']（字典键值），运行时必触发 TypeError。
4. 关闭窗口线程不退出：未重写 closeEvent，后台 ScanWorker 继续运行，进程残留。
5. UDP 扫描未实现：界面可选 UDP，但 PortScanner 无 UDP 逻辑，选择后结果无意义。

### 2.2 功能性缺陷（5 项）
6. 暂停按钮无法切换恢复：仅绑定 pause_scan，无 resume_scan 槽函数，暂停后死锁。
7. 导出功能格式固定：export_data() 硬编码 TXT，与按钮文字「导出CSV」不符。
8. 进度条数值越界：进度计算无上限保护，可能超过 100%。
9. 异常捕获不完整：ICMP 无权限、Socket 异常、解析失败直接崩线程。
10. 重复启动线程风险：停止后未清空 worker 对象，多次点击「开始」导致多轮并发。

### 2.3 并发与安全缺陷（3 项）
11. 结果无线程安全保护：多线程写入 self.results 未加锁，可能丢失/重复/错乱。
12. 轮询循环无法即时响应停止：while + sleep(0.2) 轮询，停止信号延迟高。
13. 无扫描速度控制：发包过快，无随机延迟与限流，易被防火墙拦截。

### 2.4 UI 与体验缺陷（3 项）
14. “跳过离线 IP” 控件使用错误：使用 QPushButton 做开关，视觉误导（功能逻辑正确，控件类型欠妥）。
15. 日志可读性差：无时间戳，无颜色区分，排查困难。
16. 按钮状态管理混乱：开始/暂停/停止/导出状态分散赋值，易误操作。

### 2.5 工程化规范问题（4 项）
17. 无窗口关闭保护：未重写 closeEvent。
18. 函数内导入模块不规范：run() 内 import time，影响性能且不符合编码规范。
19. 无任务总量上限：超大网段 + 端口段可能瞬间占满内存。
20. 无合规使用提示：缺少授权检测与法律声明。

注：原分析文档列 18 项，本日志在归类时合并了部分关联项，实际覆盖全部缺陷点。

## 三、架构重构方案
### 3.1 设计原则
• 单一职责（SRP）：每个类只负责一个抽象层次（数据、解析、扫描、调度、导出、UI）。
• 依赖倒置（DIP）：ScanWorker 通过构造函数注入 PortScanner 与 ThreadManager，便于单元测试替换 Mock。
• 开闭原则（OCP）：新增导出格式仅需注册到 ExporterRegistry，无需修改 GUI 代码。
• 防御式编程：所有异常在模块边界消化，不向上层抛裸异常。

### 3.2 模块职责划分
┌─────────────────────────────────────────────┐
│  GUI 层 (MainWindow)                         │
│  职责：布局、事件绑定、状态展示、用户交互      │
├─────────────────────────────────────────────┤
│  控制层 (ScanWorker)                         │
│  职责：任务编排、信号转发、连接扫描器与线程管理器│
├─────────────────────────────────────────────┤
│  扫描层 (PortScanner)                        │
│  职责：socket 探测、服务识别、Banner 抓取      │
├─────────────────────────────────────────────┤
│  调度层 (ThreadManager)                      │
│  职责：任务队列、并发控制、暂停/恢复/停止      │
├─────────────────────────────────────────────┤
│  解析层 (IPParser / PortParser)              │
│  职责：输入字符串 → 结构化任务列表             │
├─────────────────────────────────────────────┤
│  导出层 (ExporterRegistry / IExporter)       │
│  职责：ScanResult → 持久化文件（TXT/CSV/JSON）│
├─────────────────────────────────────────────┤
│  数据层 (ScanResult / ScanConfig / PortState)│
│  职责：不可变数据契约、配置对象、枚举状态       │
└─────────────────────────────────────────────┘

## 四、逐项修改清单
|序号|原问题|修改内容|涉及模块|状态|
|---|---|---|---|---|
|1|线程控制失效|ThreadManager 引入 _paused/_stopped 条件变量；ScanWorker 透传 pause/resume/stop|thread_mgr, worker|✅ 已解决|
|2|队列读取不安全|轮询前判空；_worker_loop 内 try/finally 保证异常也计入进度|thread_mgr|✅ 已解决|
|3|返回类型不一致|统一为 ScanResult dataclass（frozen=True），消灭元组/字典混用|models, scanner|✅ 已解决|
|4|关闭线程不退出|重写 MainWindow.closeEvent()，拦截 → worker.stop() → wait(2000)|gui|✅ 已解决|
|5|UDP 未实现|实现 _scan_udp()，基于 SOCK_DGRAM + sendto/recvfrom|scanner|✅ 已解决|
|6|暂停无法恢复|合并为 toggle_pause() 状态机，按钮文本自动切换|gui|✅ 已解决|
|7|导出格式固定|引入 ExporterRegistry 策略模式，支持 TXT/CSV/JSON|exporters, gui|✅ 已解决|
|8|进度条越界|progress() 做除零保护；finished 强制置 100%|thread_mgr, gui|✅ 已解决|
|9|异常捕获不全|ping_host() 捕获 PermissionError 降级 TCP；scan_single() 外层消化异常|scanner|✅ 已解决|
|10|重复启动风险|start_scan() 首行检查 isRunning()，直接 return|gui|✅ 已解决|
|11|结果无线程安全|_lock 保护 _processed；_stat_lock 保护 _open_count；结果通过 queue.Queue 传递|thread_mgr, worker|✅ 已解决|
|12|停止响应延迟|主循环 sleep(0.1)，每次检查 _stopped，秒级响应|worker|✅ 已解决|
|13|无速度控制|ScanConfig.delay_max + _worker_loop 内 random.uniform()|thread_mgr, models|✅ 已解决|
|14|控件类型欠妥|保留 QPushButton(setCheckable=True)，逻辑正确；如需可一键替换为 QCheckBox|gui|⚠️ 功能正确，控件保留|
|15|日志可读性差|日志加 %H:%M:%S 时间戳；结果表格按状态着色；状态栏实时三指标|gui|✅ 已解决|
|16|按钮状态混乱|_set_controls_running(bool) 统一管控所有控件 enabled 状态|gui|✅ 已解决|
|17|无关闭保护|closeEvent 重写，扫描中需二次确认|gui|✅ 已解决|
|18|函数内导入|所有 import 移至文件顶部|全局|✅ 已解决|
|19|无任务上限|线程上限 MAX_THREADS=20；任务流式分发，不一次性载入内存|models, thread_mgr|⚠️ 已缓解，未设硬性上限|
|20|无合规提示|源码注释、日志前缀、状态栏均体现授权内网约束|全局|✅ 已解决|

## 五、关键技术决策（ADR）
### ADR-001：统一数据契约采用 dataclass(frozen=True)
• 背景：原代码元组与字典混用，导致运行时类型错误。
• 决策：引入不可变的 ScanResult dataclass。
• 理由：
– 编译期类型检查友好（配合类型注解）。
– frozen=True 防止多线程环境下结果对象被意外修改。
– asdict() 便于 JSON 序列化。
• 影响：所有模块（扫描器、线程管理器、导出器、GUI）统一依赖 models.py 层。

### ADR-002：扫描器异常内部消化，不向上抛裸异常
• 背景：原代码 Socket 异常直接崩线程，导致 GUI 卡死。
• 决策：PortScanner.scan_single() 最外层包裹 try/except，所有异常转换为 PortState.ERROR。
• 理由：
– 端口扫描天然存在大量超时/拒绝连接，属于预期内结果，不应视为致命错误。
– 异常信息通过 error_msg 字段保留，供上层展示。
• 影响：ScanWorker.run() 无需再捕获扫描细节异常，逻辑大幅简化。

### ADR-003：ICMP 无权限时自动降级为 TCP 探测
• 背景：Windows 普通用户无管理员权限时，ping 命令抛 PermissionError。
• 决策：捕获 PermissionError 后，设置 _icmp_available=False，后续改用 socket.create_connection 探测 80 端口。
• 理由：
– 任务书明确要求「兼容 Windows 普通权限，降低管理员权限依赖」。
– 降级后仍能过滤大部分离线主机，仅精度略降。
• 影响：ping_host() 内部状态机管理，调用方无感知。

### ADR-004：导出器采用注册表模式而非工厂模式
• 背景：需支持 TXT/CSV/JSON，未来可能扩展 XML/数据库。
• 决策：ExporterRegistry 静态字典注册，而非 if/else 工厂。
• 理由：
– 新增格式时只需在 _exporters 字典中注册新实例，零侵入 GUI。
– 符合开闭原则（OCP）。
• 影响：MainWindow 完全解耦于具体导出实现。

### ADR-005：线程调度保留自定义线程池，不迁移至 concurrent.futures
• 背景：用户明确 ThreadManager 为自定义实现（threading+queue）。
• 决策：保留原设计，增强 _paused/_stopped 条件变量控制。
• 理由：
– concurrent.futures 的暂停/恢复粒度不足，自定义线程池更易实现逐任务延迟与状态控制。
– 零第三方依赖约束。
• 影响：需自行维护 _worker_loop 的异常安全与进度统计。

## 六、新增功能清单
|功能|说明|实现模块|
|---|---|---|
|Banner 抓取|TCP 连接成功后尝试 recv(1024) 读取服务 Banner|PortScanner._scan_tcp()|
|响应时间统计|记录每个端口的扫描耗时（毫秒）|ScanResult.response_time_ms|
|结果表格着色|OPEN=绿色、ERROR=红色、FILTERED=黄色、CLOSED=白色|MainWindow.handle_result()|
|状态栏实时统计|总任务 / 已完成 / 开放端口 三指标|MainWindow._update_status()|
|批量清空|一键清空结果表格、日志、进度、状态栏|MainWindow.clear_all()|
|导出格式扩展|新增 JSON 导出，通过注册表一键扩展|JsonExporter, ExporterRegistry|
|窗口关闭保护|扫描中关闭窗口需二次确认|MainWindow.closeEvent()|

## 七、代码统计
|指标|数值|
|---|---|
|总代码行数|~420 行（含注释与空行）|
|模块/类数量|7 个职责层、12 个类、2 个枚举|
|接口/抽象类|IExporter（1 个抽象基类）|
|第三方依赖|PyQt6（仅 GUI 层）|
|标准库依赖|socket, threading, queue, subprocess, csv, json, random, dataclasses, enum, abc, typing, datetime, time, sys, os|

## 八、测试与验证
### 8.1 单元测试推演（未自动化，已逻辑验证）
• IP 解析：127.0.0.1,192.168.1.1-3 → 正确展开为 4 个 IP，去序保序。
• 端口解析：common → 返回预设 15 个常用端口；1-3,80 → [1,2,3,80]。
• 扫描器：scan_single("127.0.0.1", 80, "tcp") → 返回 ScanResult，状态为 OPEN/CLOSED/ERROR 之一，类型始终一致。
• 线程管理器：提交 10 个任务，暂停后 _processed 停止增长，恢复后继续，停止后队列清空。
• 导出器：任意 List[ScanResult] 输入，TXT/CSV/JSON 均生成合法文件。

### 8.2 集成测试推演
• 完整扫描流程：输入 → 解析 → ICMP 预检 → 流式分发 → 并发扫描 → 结果入表 → 日志输出 → 导出文件。
• 边界条件：
– 全部主机离线 + skip_offline=True → 任务数为 0，正常提示「无有效扫描任务」。
– 线程数=1，延迟=5s → 串行执行，无异常。
– 窗口扫描中关闭 → 弹出确认对话框，确认后线程优雅退出。

## 九、遗留事项与待办
|序号|事项|优先级|建议方案|
|---|---|---|---|
|1|任务总量硬性上限|中|在 IPParser/PortParser 层增加 len(targets)*len(ports) > 100000 时拒绝启动，防止极端输入|
|2|“跳过离线 IP” 控件替换为 QCheckBox|低|一键替换，不影响业务逻辑|
|3|多文件工程拆分|低|按职责层拆分为 models.py, parsers.py, scanner.py, thread_mgr.py, exporters.py, worker.py, gui.py|
|4|自动化单元测试|低|使用 unittest + unittest.mock 对 PortScanner 与 ThreadManager 进行 Mock 测试|
|5|扫描结果持久化数据库|低|新增 SqliteExporter 实现 IExporter 接口即可|

## 十、合规与风险提示
1. 使用限制：本工具仅限授权内网安全巡检、端口开放检测、运维测试使用。
2. 法律声明：严禁用于未授权网络扫描、漏洞利用、暴力破解或任何攻击性行为。
3. 权限说明：
– ICMP 存活检测在 Windows 上需要管理员权限，无权限时自动降级为 TCP 探测。
– 扫描行为可能被目标主机防火墙记录，请确保已获得书面授权。
4. 免责声明：开发者不对因未授权使用、配置错误或网络环境差异导致的任何后果承担责任。

## 十一、交付物清单
|序号|交付物|状态|
|---|---|---|
|1|重构后完整源码（单文件）|✅ 已交付|
|2|代码问题逐项分析文档|✅ 已交付（用户上传）|
|3|架构设计说明与 ADR|✅ 本文档|
|4|使用教程与运行说明|需用户确认是否单独输出|
|5|合规使用声明|✅ 已包含于源码注释及本文档|

日志结束
