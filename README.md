# My Python API Project

这是一个基于 Python (FastAPI) 的简单接口项目模板。

## 功能
- 提供 RESTful API 接口
- 自动生成 Swagger 文档
- 支持异步处理

## 快速开始

### 1. 安装依赖
建议使用虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
# 或者 venv\Scripts\activate (Windows)

pip install -r requirements.txt



轻量级端口扫描工具 - PortScanner
项目简介
🚀 基于Python开发的轻量级端口扫描工具，专为Windows环境设计，具有速度适中、功能精简、代码清晰易维护的特点。
本项目可用于网络安全实训、自用局域网扫描、网络排查等合法场景，能够高效检测指定IP地址和端口范围中开放的端口信息。

项目特点
轻量易用：仅需简单命令即可完成端口扫描，新手友好。
合规安全：默认低频发包模式，降低被防火墙拦截的风险。
模块化可迭代：代码结构清晰，便于功能扩展与二次开发。
多线程高效：支持自定义并发线程数，显著提升扫描效率。
功能丰富：
指定IP地址和端口范围进行扫描。
输出开放端口及对应服务名。
支持保存扫描结果，便于后续分析。
环境要求
操作系统：Windows 10/11 或其他支持的Python环境
Python版本：3.8 或更高版本
快速开始
1. 克隆项目
git clone https://github.com/your_username/PortScanner.git
cd PortScanner
2. 安装依赖
本项目无外部依赖，仅需确保 Python 环境即可。

3. 运行工具
python main.py <ip> [--start-port <起始端口>] [--end-port <结束端口>] [--threads <线程数>]
示例
扫描本地 127.0.0.1 的1到1024端口：

python main.py 127.0.0.1 --start-port 1 --end-port 1024 --threads 20
参数说明
参数	必填/可选	说明	默认值
<ip>	必填	目标 IP 地址	无
--start-port	可选	扫描的起始端口	1
--end-port	可选	扫描的结束端口	65535
--threads	可选	并发线程数（需小于配置文件中最大值）	配置文件中默认值
项目目录结构
port_scanner/
├── LICENSE                         # 项目授权协议
├── README.md                       # 项目说明文档
├── docs/
│   └── user_guide.md               # 用户使用指南
├── tests/
│   └── test_scanner.py             # 单元测试文件
├── config.py                       # 配置文件（自定义扫描设置）
├── main.py                         # 主入口程序
└── scanner.py                      # 核心扫描功能
注意事项
合法性：请仅在授权或合法允许的场景下使用本工具，否则可能违反相关法律法规。
网络隐私：不要在未经许可的情况下扫描他人的网络设备。
防火墙干扰：如果遭遇防火墙拦截��扫描异常，建议检查网络环境或调整扫描配置。
功能展望
🔧 支持多目标扫描 （如：IP地址段192.168.0.1-192.168.0.255)
⚡ 增加快速扫描模式，针对常见端口（如 HTTP、SSH、DNS）
🔍 添加UDP端口扫描功能
📁 扫描结果保存为文件，支持多种格式（如 CSV、JSON）
参与贡献
欢迎对本工具提出建议，或者通过 Pull Request 的方式参与到项目开发中！

贡献流程
Fork 仓库：https://github.com/your_username/PortScanner.git
创建分支：git checkout -b your-feature-branch
提交修改：git commit -m "描述你的改动"
推送分支：git push origin your-feature-branch
创建 拉取请求
