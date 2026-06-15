#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果导出模块 | 策略模式 + 动态字段 + 覆盖确认 + 元信息返回
设计原则：
  - 单一职责：每种格式一个类，只负责序列化
  - 开闭原则：新增格式只需注册，无需修改 Registry
  - 依赖倒置：GUI/CLI 通过 OverwriteStrategy 注入行为，模块不依赖 PyQt6
  - 防御编程：所有 IO 异常捕获并包装为 ExportError
"""

import os
import sys
import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


# ============================================================
# 1. 异常与数据契约
# ============================================================

class ExportError(Exception):
    """导出过程统一异常，调用方只需捕获此类即可"""
    pass


@dataclass
class ExportMeta:
    """
    导出元信息

    解决「未返回导出记录数、文件大小等元信息」问题，
    调用方可据此在 GUI 状态栏/弹窗中展示导出详情。
    """
    filepath: str
    format: str
    record_count: int
    file_size_bytes: int
    timestamp: datetime
    fields: List[str]


# ============================================================
# 2. 覆盖确认策略（策略模式）
# ============================================================

class OverwriteStrategy(ABC):
    """
    文件覆盖确认策略抽象基类

    GUI 层可继承此类实现弹窗确认，不污染本模块。
    CLI 层可使用内置 PromptCLI 策略。
    """

    @abstractmethod
    def should_overwrite(self, filepath: str) -> bool:
        """
        :return: True  继续写入（覆盖或文件不存在）
        :return: False 用户主动取消
        :raise:  FileExistsError 非交互模式下拒绝覆盖
        """
        pass


class RaiseOnExistsStrategy(OverwriteStrategy):
    """安全默认：文件存在则抛出 FileExistsError，防止误覆盖"""

    def should_overwrite(self, filepath: str) -> bool:
        if os.path.exists(filepath):
            raise FileExistsError(f"文件已存在: {filepath}")
        return True


class AlwaysOverwriteStrategy(OverwriteStrategy):
    """静默覆盖（用于自动化脚本场景）"""

    def should_overwrite(self, filepath: str) -> bool:
        return True


class PromptCLIOverwriteStrategy(OverwriteStrategy):
    """
    CLI 交互式确认

    非交互环境（管道/重定向）自动抛出异常，避免挂起。
    """

    def should_overwrite(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return True
        if not sys.stdin.isatty():
            raise FileExistsError(
                f"文件已存在且处于非交互模式，默认不覆盖: {filepath}"
            )
        try:
            choice = input(
                f"文件 [{filepath}] 已存在，是否覆盖? [y/N]: "
            ).strip().lower()
            return choice in ("y", "yes")
        except (EOFError, OSError):
            raise FileExistsError(
                f"非交互环境输入异常，默认不覆盖: {filepath}"
            )


# ============================================================
# 3. 动态字段提取工具（高内聚）
# ============================================================

def _extract_records(results: List[Any]) -> List[Dict[str, Any]]:
    """
    统一适配器：将 ScanResult/dataclass/dict 转为标准字典列表

    解决「硬编码字段列表」与「扫描结果字段耦合」问题，
    支持后续动态增删 banner/timestamp/product/version 等字段。
    """
    if not results:
        return []
    records: List[Dict[str, Any]] = []
    for r in results:
        if is_dataclass(r) and not isinstance(r, type):
            rec = asdict(r)
        elif isinstance(r, dict):
            rec = r.copy()
        else:
            # 兜底：反射提取公有属性
            rec = {
                k: getattr(r, k)
                for k in dir(r)
                if not k.startswith("_") and not callable(getattr(r, k, None))
            }
        # 统一序列化：PortState 等 Enum 转为字符串
        for key, val in rec.items():
            if isinstance(val, Enum):
                rec[key] = val.value
        records.append(rec)
    return records


def _ensure_dir(filepath: str) -> None:
    """确保输出目录存在，解决「路径不存在时崩溃」"""
    dirpath = os.path.dirname(filepath)
    if dirpath and not os.path.exists(dirpath):
        try:
            os.makedirs(dirpath, exist_ok=True)
        except OSError as e:
            raise ExportError(f"无法创建输出目录: {dirpath}") from e


# ============================================================
# 4. 导出策略接口与具体实现
# ============================================================

class IExporter(ABC):
    @abstractmethod
    def export(self, results: List[Any], filepath: str) -> ExportMeta:
        pass

    @abstractmethod
    def extension(self) -> str:
        pass

    @abstractmethod
    def supported_fields(self, results: List[Any]) -> List[str]:
        """返回该格式实际会输出的字段列表（用于元信息）"""
        pass


class CsvExporter(IExporter):
    """CSV 导出器 —— 动态字段，无需硬编码 fieldnames"""

    def extension(self) -> str:
        return ".csv"

    def supported_fields(self, results: List[Any]) -> List[str]:
        if not results:
            return []
        records = _extract_records(results)
        # 以第一条记录键顺序为基准，合并所有记录可能出现的键（防字段缺失）
        first_keys = list(records[0].keys())
        all_keys: set = set()
        for rec in records:
            all_keys.update(rec.keys())
        extra = [k for k in sorted(all_keys) if k not in first_keys]
        return first_keys + extra

    def export(self, results: List[Any], filepath: str) -> ExportMeta:
        _ensure_dir(filepath)
        records = _extract_records(results)
        fieldnames = self.supported_fields(results) if records else []

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=fieldnames, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(records)

            return ExportMeta(
                filepath=filepath,
                format="csv",
                record_count=len(records),
                file_size_bytes=os.path.getsize(filepath),
                timestamp=datetime.now(),
                fields=fieldnames,
            )
        except PermissionError as e:
            raise ExportError(f"权限不足，无法写入 CSV: {filepath}") from e
        except OSError as e:
            raise ExportError(f"磁盘错误或路径无法访问: {filepath}") from e


class TxtExporter(IExporter):
    """
    TXT 导出器 —— 动态列宽计算

    解决「列宽固定 15/6/6/15 字符导致长 IP 或状态值溢出」
    """

    def extension(self) -> str:
        return ".txt"

    def supported_fields(self, results: List[Any]) -> List[str]:
        if not results:
            return ["ip", "port", "protocol", "state", "service"]
        records = _extract_records(results)
        all_keys: set = set()
        for rec in records:
            all_keys.update(rec.keys())
        # 优先级排序：核心字段在前，扩展字段在后
        priority = [
            "ip", "port", "protocol", "state", "service",
            "banner", "response_time_ms", "error_msg",
        ]
        fields = [k for k in priority if k in all_keys]
        fields += sorted([k for k in all_keys if k not in priority])
        return fields

    def export(self, results: List[Any], filepath: str) -> ExportMeta:
        _ensure_dir(filepath)
        fields = self.supported_fields(results)
        records = _extract_records(results)

        # 动态计算每列宽度（内容最大长度 vs 表头长度）
        col_widths = [len(f) for f in fields]
        for rec in records:
            for i, field in enumerate(fields):
                val_str = str(rec.get(field, "-"))
                col_widths[i] = max(col_widths[i], len(val_str))
        # 最小宽度 6，加 2 字符 padding
        padded_widths = [max(w, 6) + 2 for w in col_widths]
        total_width = sum(padded_widths) + len(fields) - 1

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(
                    f"Port Scan Report | Generated: "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                f.write(f"Total Records: {len(records)}
")
                f.write("-" * total_width + "
")

                # 表头
                header_parts = [
                    field.upper().ljust(padded_widths[i])
                    for i, field in enumerate(fields)
                ]
                f.write(" ".join(header_parts) + "
")
                f.write("-" * total_width + "
")

                # 数据行
                for rec in records:
                    row_parts = [
                        str(rec.get(field, "-")).ljust(padded_widths[i])
                        for i, field in enumerate(fields)
                    ]
                    f.write(" ".join(row_parts) + "
")

            return ExportMeta(
                filepath=filepath,
                format="txt",
                record_count=len(records),
                file_size_bytes=os.path.getsize(filepath),
                timestamp=datetime.now(),
                fields=fields,
            )
        except PermissionError as e:
            raise ExportError(f"权限不足，无法写入 TXT: {filepath}") from e
        except OSError as e:
            raise ExportError(f"磁盘错误或路径无法访问: {filepath}") from e


class JsonExporter(IExporter):
    """JSON 导出器 —— 解决「未实现 JSON 格式」"""

    def extension(self) -> str:
        return ".json"

    def supported_fields(self, results: List[Any]) -> List[str]:
        if not results:
            return []
        records = _extract_records(results)
        all_keys: set = set()
        for rec in records:
            all_keys.update(rec.keys())
        return sorted(all_keys)

    def export(self, results: List[Any], filepath: str) -> ExportMeta:
        _ensure_dir(filepath)
        records = _extract_records(results)

        def _serialize(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(
                f"Object of type {type(obj).__name__} is not JSON serializable"
            )

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    records, f,
                    ensure_ascii=False,
                    indent=2,
                    default=_serialize,
                )

            return ExportMeta(
                filepath=filepath,
                format="json",
                record_count=len(records),
                file_size_bytes=os.path.getsize(filepath),
                timestamp=datetime.now(),
                fields=self.supported_fields(results),
            )
        except PermissionError as e:
            raise ExportError(f"权限不足，无法写入 JSON: {filepath}") from e
        except OSError as e:
            raise ExportError(f"磁盘错误或路径无法访问: {filepath}") from e


# ============================================================
# 5. 注册中心（解决「分支结构扩展性差」「无自动推断」）
# ============================================================

class ExporterRegistry:
    """
    导出器注册中心 —— 策略模式 + 自动推断

    新增格式只需调用 ExporterRegistry.register("xml", XmlExporter())
    无需修改 Registry 内部代码
    """

    _exporters = {
        "csv": CsvExporter(),
        "txt": TxtExporter(),
        "json": JsonExporter(),
    }

    @classmethod
    def register(cls, name: str, exporter: IExporter) -> None:
        cls._exporters[name.lower().lstrip(".")] = exporter

    @classmethod
    def _infer_format(cls, filepath: str) -> str:
        """从文件扩展名自动推断格式 —— 解决「无导出格式自动推断」"""
        ext = os.path.splitext(filepath)[1].lower().lstrip(".")
        fmt_map = {
            "csv": "csv", "txt": "txt", "json": "json",
            "js": "json", "text": "txt",
        }
        fmt = fmt_map.get(ext)
        if not fmt:
            raise ExportError(
                f"无法从文件扩展名推断导出格式: '{ext}'，"
                f"请显式指定 fmt 参数或修改文件后缀"
            )
        return fmt

    @classmethod
    def export(
        cls,
        results: List[Any],
        filepath: str,
        fmt: Optional[str] = None,
        overwrite_strategy: Optional[OverwriteStrategy] = None,
        output_dir: Optional[str] = None,
    ) -> ExportMeta:
        """
        统一导出入口

        :param results: 扫描结果列表（ScanResult/dataclass/dict 均可）
        :param filepath: 文件路径（绝对/相对/纯文件名）
        :param fmt: 显式指定格式；None 时自动推断
        :param overwrite_strategy: 覆盖确认策略，默认 RaiseOnExistsStrategy（安全）
        :param output_dir: filepath 为纯文件名时的默认输出目录（解决 OUTPUT_DIR 耦合）
        :return: ExportMeta 元信息对象
        """
        # 路径处理：纯文件名时拼接 output_dir，最终转为绝对路径
        if not os.path.isabs(filepath) and output_dir:
            filepath = os.path.join(output_dir, filepath)
        filepath = os.path.abspath(filepath)

        # 格式推断
        if fmt is None:
            fmt = cls._infer_format(filepath)
        else:
            fmt = fmt.lower().lstrip(".")

        exporter = cls._exporters.get(fmt)
        if not exporter:
            raise ExportError(
                f"不支持的导出格式: '{fmt}'，"
                f"当前支持: {list(cls._exporters.keys())}"
            )

        # 自动修正扩展名（如用户输入 report 自动变为 report.txt）
        expected_ext = exporter.extension()
        actual_ext = os.path.splitext(filepath)[1].lower()
        if actual_ext != expected_ext:
            filepath = filepath + expected_ext

        # 覆盖确认
        strategy = overwrite_strategy or RaiseOnExistsStrategy()
        if not strategy.should_overwrite(filepath):
            raise ExportError(f"用户取消导出: {filepath}")

        # 执行导出
        return exporter.export(results, filepath)
