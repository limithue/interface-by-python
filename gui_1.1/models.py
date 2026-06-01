"""数据契约层 — 解析结果不可变数据模型"""
from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class ParseResult:
    """不可变数据契约：解析层与下游扫描引擎的唯一交互接口

    frozen=True 保证多线程环境下结果对象不被意外修改，
    消除解析器与扫描器之间的副作用耦合。
    """
    targets: FrozenSet[str]
    ports: FrozenSet[int]

    @property
    def total_tasks(self) -> int:
        """总扫描任务量 = 目标数 × 端口数"""
        return len(self.targets) * len(self.ports)

    @property
    def target_count(self) -> int:
        return len(self.targets)

    @property
    def port_count(self) -> int:
        return len(self.ports)
