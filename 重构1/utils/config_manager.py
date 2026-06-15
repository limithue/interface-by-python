"""
utils/config_manager.py
"""
import json
import os
from dataclasses import dataclass, asdict, fields
from 重构1.utils.path_helper import get_data_path

@dataclass
class GUIConfig:
    skip_offline: bool = True
    max_threads: int = 20
    default_ports: str = "common"
    default_protocol: str = "tcp"

class ConfigManager:
    def __init__(self, config_file="scan_config.json"):
        # 【关键修复 2】：配置文件指向 EXE 真实同级目录
        self.config_file = get_data_path(config_file)
        self.config = self.load()

    def load(self) -> GUIConfig:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    valid_fields = {f.name for f in fields(GUIConfig)}
                    filtered_data = {k: v for k, v in data.items() if k in valid_fields}
                    return GUIConfig(**filtered_data)
            except Exception:
                pass
        return GUIConfig()

    def save(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.config), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")
