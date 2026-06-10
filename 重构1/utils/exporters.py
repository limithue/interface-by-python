"""
utils/exporters.py
基于策略模式与注册中心的导出引擎
"""
import csv
import json
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any

# ================= 覆盖策略层 =================
class OverwriteStrategy(ABC):
    @abstractmethod
    def should_overwrite(self, filepath: str) -> bool: pass

class AlwaysOverwriteStrategy(OverwriteStrategy):
    def should_overwrite(self, filepath: str) -> bool: return True

class PromptCLIOverwriteStrategy(OverwriteStrategy):
    def should_overwrite(self, filepath: str) -> bool:
        if os.path.exists(filepath):
            resp = input(f"⚠️ 文件 {filepath} 已存在，是否覆盖？(y/n): ").strip().lower()
            return resp == 'y'
        return True

# ================= 导出策略层 =================
class IExporter(ABC):
    @abstractmethod
    def export(self, data: List[Dict[str, Any]], filepath: str): pass

class CsvExporter(IExporter):
    def export(self, data: List[Dict[str, Any]], filepath: str):
        if not data: return
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

class JsonExporter(IExporter):
    def export(self, data: List[Dict[str, Any]], filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

class TxtExporter(IExporter):
    def export(self, data: List[Dict[str, Any]], filepath: str):
        if not data: return
        headers = list(data[0].keys())
        col_widths = {h: max(len(h), max(len(str(row.get(h, ''))) for row in data)) for h in headers}
        
        with open(filepath, 'w', encoding='utf-8') as f:
            header_line = " | ".join(h.ljust(col_widths[h]) for h in headers)
            f.write(header_line + "\n")
            f.write("-" * len(header_line) + "\n")
            for row in data:
                line = " | ".join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers)
                f.write(line + "\n")

# ================= 注册中心 =================
class ExporterRegistry:
    _exporters = {
        '.csv': CsvExporter(),
        '.json': JsonExporter(),
        '.txt': TxtExporter()
    }

    @classmethod
    def export(cls, data: List[Dict], filepath: str, strategy: OverwriteStrategy = None):
        if strategy is None:
            strategy = AlwaysOverwriteStrategy()
            
        if not strategy.should_overwrite(filepath):
            return False

        ext = os.path.splitext(filepath)[1].lower()
        exporter = cls._exporters.get(ext)
        if not exporter:
            raise ValueError(f"不支持的导出格式: {ext}")
        
        exporter.export(data, filepath)
        return True
