"""
utils/config_manager.py
GUI 配置持久化管理器
"""
import json
import os
from dataclasses import dataclass, asdict, fields

@dataclass
class GUIConfig:
    skip_offline: bool = True
    max_threads: int = 20
    default_ports: str = "common"
    default_protocol: str = "tcp"

class ConfigManager:
    def __init__(self, config_file="scan_config.json"):
        self.config_file = config_file
        self.config = self.load()

    def load(self) -> GUIConfig:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 兼容旧版本：仅提取 dataclass 中定义的字段
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

