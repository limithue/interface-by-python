"""结果导出模块｜支持 TXT 与 CSV 格式化输出"""
import os
import csv
from datetime import datetime
from typing import List, Dict
from config import OUTPUT_DIR

def export_results(results: List[Dict], fmt: str = "csv") -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"scan_report_{timestamp}.{fmt}"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if fmt == "csv":
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["ip", "port", "protocol", "state", "service"])
            writer.writeheader()
            writer.writerows(results)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Port Scan Report | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'IP':<15} {'Port':<6} {'Proto':<6} {'State':<15} {'Service'}\n")
            f.write("-" * 65 + "\n")
            for r in results:
                f.write(f"{r['ip']:<15} {r['port']:<6} {r['protocol']:<6} {r['state']:<15} {r['service']}\n")
    return filepath
