"""日志配置模块｜低耦合高内聚，支持异步队列阻塞兜底、日志轮转、模块级隔离"""
import logging
import logging.handlers
import os
import queue
import threading
import atexit
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class LogConfig:
    """高内聚配置类：废弃原全局 OUTPUT_DIR / LOG_FILE 硬编码，由调用方注入。

    低耦合：不依赖任何外部 config.py 模块，调用方自行决定配置来源（环境变量、
    配置文件、命令行参数等），实例化后传入 LoggerManager 即可。
    """
    level: int = logging.INFO
    console_level: int = logging.INFO
    file_level: int = logging.DEBUG
    log_dir: str = "./output"
    log_file: str = "scanner.log"
    max_bytes: int = 10 * 1024 * 1024   # 10MB / 个
    backup_count: int = 5                # 保留 5 份，超出自动删除最旧
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    queue_max_size: int = 1000
    use_queue: bool = True               # 高并发端口扫描启用异步队列
    encoding: str = "utf-8"


class LoggerManager:
    """日志管理器：低耦合高内聚的生命周期管理。

    低耦合：
      - 不依赖外部 config.py 全局变量，通过 LogConfig 注入全部配置。
      - 不直接操作 root logger，避免污染全局日志环境。
    高内聚：
      - 封装 logger 创建、handler 组装、异步队列调度、优雅关闭。
      - 所有状态（registry、listener、锁）均收敛于本类内部。
    """

    _logger_registry: Dict[str, logging.Logger] = {}
    _listener_registry: Dict[str, logging.handlers.QueueListener] = {}
    _registry_lock = threading.Lock()

    @classmethod
    def get_logger(cls, name: str = "portscanner", config: Optional[LogConfig] = None) -> logging.Logger:
        """获取模块级 logger（非 root），单例防重复，线程安全。

        修复问题 1/2/7：使用命名 logger 替代 root logger，双检锁防止重复添加 Handler。

        Args:
            name: logger 名称，强烈建议使用 __name__ 实现模块级隔离。
            config: 日志配置，为 None 时使用默认 LogConfig。

        Returns:
            配置完成的 logging.Logger 实例。
        """
        if name in cls._logger_registry:
            return cls._logger_registry[name]

        with cls._registry_lock:
            if name in cls._logger_registry:
                return cls._logger_registry[name]

            cfg = config if config is not None else LogConfig()
            logger = cls._assemble(name, cfg)
            cls._logger_registry[name] = logger
            return logger

    @classmethod
    def _assemble(cls, name: str, cfg: LogConfig) -> logging.Logger:
        """内部组装逻辑：模块级隔离、防重复、双 Handler 分级、异步队列阻塞兜底。"""
        logger = logging.getLogger(name)
        logger.setLevel(cfg.level)

        # 若因异常导致重复进入，先清空已有 handler 防止重复输出（修复问题 1）
        if logger.handlers:
            for h in logger.handlers[:]:
                h.flush()
                h.close()
                logger.removeHandler(h)

        # 目录级联创建（修复问题 6：不依赖外部 config 模块的 OUTPUT_DIR）
        os.makedirs(cfg.log_dir, exist_ok=True)
        log_path = os.path.join(cfg.log_dir, cfg.log_file)

        formatter = logging.Formatter(cfg.fmt, datefmt=cfg.datefmt)

        # 构建实际输出 Handler（修复问题 3/4/5/8）
        real_handlers: List[logging.Handler] = []

        console_h = logging.StreamHandler()
        console_h.setLevel(cfg.console_level)   # 独立级别：开发/生产差异化输出
        console_h.setFormatter(formatter)
        real_handlers.append(console_h)

        # 按文件大小轮转，10MB/个，保留 5 份，超出自动删除最旧（修复问题 3）
        file_h = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=cfg.max_bytes,
            backupCount=cfg.backup_count,
            encoding=cfg.encoding
        )
        file_h.setLevel(cfg.file_level)          # 文件记录更详细，控制台保持简洁
        file_h.setFormatter(formatter)
        real_handlers.append(file_h)

        if cfg.use_queue:
            # 异步队列：阻塞兜底方案（修复问题 9）
            # 当队列满时，QueueHandler.put 会阻塞扫描线程，保证日志完整性不丢失。
            # 适用于短时扫描场景：短时阻塞优于日志丢失。
            log_queue = queue.Queue(maxsize=cfg.queue_max_size)
            queue_handler = logging.handlers.QueueHandler(log_queue)
            logger.addHandler(queue_handler)

            listener = logging.handlers.QueueListener(
                log_queue, *real_handlers, respect_handler_level=True
            )
            listener.start()
            cls._listener_registry[name] = listener

            # 注册进程退出时优雅关闭（修复问题 10）
            atexit.register(cls._shutdown_one, name)
        else:
            # 同步模式：直接挂载（低并发或调试场景）
            for h in real_handlers:
                logger.addHandler(h)

        # 阻断向 root logger 传播，避免第三方日志混入（修复问题 2）
        logger.propagate = False

        return logger

    @classmethod
    def _shutdown_one(cls, name: str) -> None:
        """关闭指定 logger：停止 listener、flush 并关闭所有 handler。

        修复问题 10：确保最后几条日志落盘，不丢失。
        """
        listener = cls._listener_registry.pop(name, None)
        if listener:
            listener.stop()

        logger = cls._logger_registry.pop(name, None)
        if logger:
            for handler in logger.handlers[:]:
                try:
                    handler.flush()
                    handler.close()
                except Exception:
                    pass
                logger.removeHandler(handler)

    @classmethod
    def shutdown_all(cls) -> None:
        """全局关闭：扫描结束或程序退出时调用，确保所有日志 flush/close。"""
        names = list(cls._listener_registry.keys())
        for name in names:
            cls._shutdown_one(name)


# 进程级兜底：Python 正常退出时自动 flush/close（修复问题 10）
atexit.register(LoggerManager.shutdown_all)
