"""
utils/path_helper.py
PyInstaller 打包环境下的路径兼容处理
"""
import sys
import os

def is_frozen():
    """判断是否处于 PyInstaller 打包后的环境"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_resource_path(relative_path):
    """
    获取资源文件路径（如图标、默认模板）。
    打包后指向 PyInstaller 的临时解压目录 (_MEIPASS)。
    """
    if is_frozen():
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def get_data_path(relative_path=""):
    """
    获取运行时数据路径（如日志、用户配置、导出文件）。
    必须指向 EXE 所在的真实物理目录，防止数据丢失或权限拒绝。
    """
    if is_frozen():
        # sys.executable 是打包后 EXE 的真实绝对路径
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境下，指向项目根目录 (utils 的上一级)
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 确保目录存在
    full_path = os.path.join(base_path, relative_path)
    dir_name = os.path.dirname(full_path) if os.path.splitext(full_path)[1] else full_path
    os.makedirs(dir_name, exist_ok=True)
    return full_path
