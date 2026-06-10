"""
main.py
项目统一启动入口
"""
import sys
import os

# 确保根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    # 默认启动 GUI 模式
    try:
        from PyQt6.QtWidgets import QApplication
        from gui.main_window import MainWindow
        
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except ImportError:
        print("❌ 启动 GUI 失败，请确保已安装 PyQt6 (pip install PyQt6)")
        sys.exit(1)

if __name__ == "__main__":
    main()
