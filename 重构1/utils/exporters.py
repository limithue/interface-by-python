from dataclasses import dataclass

@dataclass
class ExportMeta:
    """导出任务的元数据（补丁类）"""
    total_records: int = 0
    file_size_bytes: int = 0
    file_path: str = ""
    format_type: str = ""
    overwrite_strategy: str = "safe"




# 在 utils/exporters.py 顶部添加
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ExportMeta:
    """导出任务的元数据配置"""
    filename: str                  # 导出文件名（不含后缀）
    format: str                    # 导出格式 (csv, json, html, xlsx)
    timestamp: datetime            # 导出时间
    total_records: int             # 总记录数
    output_dir: Optional[str] = None # 输出目录
    overwrite: bool = False        # 是否覆盖同名文件



"""
utils/exporters.py
"""
import csv
import json
import os
import sys
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class OverwriteStrategy(ABC):
    @abstractmethod
    def should_overwrite(self, filepath: str) -> bool: pass

class AlwaysOverwriteStrategy(OverwriteStrategy):
    def should_overwrite(self, filepath: str) -> bool: return True

class PromptCLIOverwriteStrategy(OverwriteStrategy):
    def should_overwrite(self, filepath: str) -> bool:
        if os.path.exists(filepath):
            # 【关键修复 1】：防止在无控制台环境（PyInstaller -w）下调用 input() 导致闪退
            if not sys.stdin.isatty():
                return False 
            resp = input(f"⚠️ 文件 {filepath} 已存在，是否覆盖？(y/n): ").strip().lower()
            return resp == 'y'
        return True

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

class ExporterRegistry:
    _exporters = {
        '.csv': CsvExporter(),
        '.json': JsonExporter()
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
