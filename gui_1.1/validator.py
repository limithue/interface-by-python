"""校验层 — 任务量安全校验（高内聚·单一职责）"""
from typing import FrozenSet

from core.exceptions import ParseError

# 模块级默认配置
_DEFAULT_MAX_TASKS = 100_000


class TaskValidator:
    """任务总量校验器

    高内聚：仅负责任务量计算与上限拦截
    低耦合：不依赖IPParser/PortParser，接收任意不可变集合
    """

    def __init__(self, max_tasks: int = _DEFAULT_MAX_TASKS):
        self.max_tasks = max_tasks

    def validate(self, targets: FrozenSet[str], ports: FrozenSet[int]) -> None:
        """校验任务总量是否超过安全上限

        Args:
            targets: 不可变目标IP集合
            ports: 不可变端口集合

        Raises:
            ParseError: 当 target_count × port_count > max_tasks 时抛出
        """
        target_count = len(targets)
        port_count = len(ports)
        total = target_count * port_count

        if total > self.max_tasks:
            raise ParseError(
                f"扫描任务量过大: {total}（目标{target_count} × 端口{port_count}），"
                f"超过安全上限 {self.max_tasks}，请缩小扫描范围",
                raw_input=f"targets={target_count}, ports={port_count}"
            )

    def get_stats(self, targets: FrozenSet[str], ports: FrozenSet[int]) -> dict:
        """获取统计信息（不触发异常）"""
        target_count = len(targets)
        port_count = len(ports)
        return {
            "target_count": target_count,
            "port_count": port_count,
            "total_tasks": target_count * port_count,
            "max_tasks": self.max_tasks,
            "is_safe": target_count * port_count <= self.max_tasks
        }
