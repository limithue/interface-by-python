"""异常抽象层 — 项目根异常与解析层异常"""


class ScannerError(Exception):
    """项目根异常

    设计意图：GUI层、调度层、导出层只需捕获此基类，
    无需感知具体模块（parser/scanner/thread_mgr）的实现差异。
    """
    pass


class ParseError(ScannerError):
    """解析层异常 — 携带原始输入便于日志追溯

    Attributes:
        raw_input: 触发异常的原始输入字符串
    """
    def __init__(self, message: str, raw_input: str = ""):
        super().__init__(message)
        self.raw_input = raw_input
