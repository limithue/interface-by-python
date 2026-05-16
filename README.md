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
```

## 🚨 已知问题（原始1.0版本缺陷）
- 中文模块文件名易导致跨平台导入失败
- ICMP 存活检测需要管理员权限，普通权限会误判主机不存活
- 每端口一线程模型，大端口段扫描可能内存过高、程序崩溃
- UDP 扫描逻辑不可靠，误报率高
- 不支持 IP 网段（CIDR）扫描
- 无端口去重、无进度显示、无结果导出功能
- 异常处理不完善，Ctrl+C 无法正常退出
- 缺少速度限制，扫描过快易被防火墙拦截
