"""
main.py
项目统一启动入口 (终极防闪退与崩溃诊断版)
"""
import sys
import os
import traceback
import ctypes

# ==========================================
# 1. 安全的哑流对象 (解决 -w 模式下标准流为 None 的底层崩溃)
# ==========================================
class DummyStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False
    def read(self, *args, **kwargs): return ""
    def readline(self, *args, **kwargs): return ""

# 仅在 PyInstaller 打包环境下重定向
if getattr(sys, 'frozen', False):
    if sys.stdout is None: sys.stdout = DummyStream()
    if sys.stderr is None: sys.stderr = DummyStream()
    if sys.stdin is None: sys.stdin = DummyStream()

# ==========================================
# 2. 全局崩溃捕获与诊断机制 (解决无声闪退)
# ==========================================
def handle_crash(exc_type, exc_value, exc_traceback):
    """拦截所有致命异常，写入日志并弹窗提示"""
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # 1. 尝试输出到控制台 (如果是 -c 模式)
    print("\n" + "="*50)
    print("FATAL ERROR:")
    print(error_msg)
    print("="*50 + "\n")
    
    # 2. 写入 EXE 同级目录的 crash.log
    try:
        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_path, "crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(error_msg)
    except Exception:
        pass
    
    # 3. Windows 下弹出原生错误对话框
    try:
        short_msg = error_msg[:800] + "..." if len(error_msg) > 800 else error_msg
        ctypes.windll.user32.MessageBoxW(
            0, 
            f"程序发生致命错误，详细堆栈已保存至 crash.log。\n\n错误信息:\n{short_msg}", 
            "程序崩溃诊断", 
            0x10  # MB_ICONERROR
        )
    except Exception:
        pass
    
    sys.exit(1)

# 挂载全局异常钩子
sys.excepthook = handle_crash

# ==========================================
# 3. 环境路径初始化
# ==========================================
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse

def main():
    # 判断是否为无控制台模式 (Windowed)
    is_windowed = getattr(sys, 'frozen', False) and isinstance(sys.stdout, DummyStream)
    
    parser = argparse.ArgumentParser(description="Python 网络扫描工具")
    parser.add_argument('--cli', action='store_true', help='强制使用 CLI 模式')
    parser.add_argument('--target', type=str, help='目标 IP/CIDR')
    parser.add_argument('--ports', type=str, default='common', help='端口范围')
    
    if is_windowed and '--cli' not in sys.argv:
        args = argparse.Namespace(cli=False, target=None, ports='common')
    else:
        args = parser.parse_args()

    if args.cli and args.target:
        print(f"[*] CLI 模式启动 | 目标: {args.target} | 端口: {args.ports}")
        # TODO: 调用 core.scanner
    else:
        # GUI 模式启动
        try:
            from PyQt6.QtWidgets import QApplication
            from gui.main_window import MainWindow
            
            app = QApplication(sys.argv)
            
            # 捕获 PyQt 事件循环内的异常
            def qt_exception_hook(exc_type, exc_value, exc_traceback):
                handle_crash(exc_type, exc_value, exc_traceback)
            sys.excepthook = qt_exception_hook
            
            window = MainWindow()
            window.show()
            
            exit_code = app.exec()
            sys.exit(exit_code)
            
        except ImportError as e:
            handle_crash(ImportError, e, e.__traceback__)
        except Exception as e:
            handle_crash(type(e), e, e.__traceback__)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        handle_crash(type(e), e, e.__traceback__)
