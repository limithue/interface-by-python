@echo off
chcp 65001 >nul
echo ============================================================
echo   Python Port Scanner - Windows EXE 打包脚本
echo ============================================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请安装 Python 3.8+ 并添加到环境变量
echo.
    pause
    exit /b 1
)

echo [1/4] 检查 PyQt6 依赖...
python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo   PyQt6 未安装，正在安装...
    pip install PyQt6
    if errorlevel 1 (
        echo [错误] PyQt6 安装失败
        pause
        exit /b 1
    )
)
echo   PyQt6 已就绪

echo.
echo [2/4] 检查 pyinstaller 依赖...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo   pyinstaller 未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [错误] pyinstaller 安装失败
        pause
        exit /b 1
    )
)
echo   pyinstaller 已就绪

echo.
echo [3/4] 清理旧构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"
echo   清理完成

echo.
echo [4/4] 开始打包...
echo   模式: 单文件 EXE + 无控制台窗口（GUI模式）
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "PortScanner" ^
    --add-data "config.py;." ^
    --add-data "core;core" ^
    --add-data "gui;gui" ^
    --add-data "utils;utils" ^
    --hidden-import PyQt6.sip ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import PyQt6.QtWidgets ^
    main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查错误信息
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包成功！
echo ============================================================
echo.
echo 输出文件: dist\PortScanner.exe
echo.
echo 使用说明:
echo   1. 双击运行 PortScanner.exe 启动 GUI 模式
echo   2. 命令行运行: PortScanner.exe --help
echo   3. 管理员权限运行可支持 SYN 半连接扫描
echo.
pause
