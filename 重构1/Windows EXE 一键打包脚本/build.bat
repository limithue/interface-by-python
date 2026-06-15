@echo off
chcp 936 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo   Python Port Scanner - 终极防乱码打包脚本 (稳妥版)
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 1. 严格检查源文件
if not exist "统一入口\main.py" (
    echo [致命错误] 找不到 "统一入口\main.py"！请确保脚本在 重构1 根目录下。
    pause
    exit /b 1
)

REM 2. 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python。
    pause
    exit /b 1
)

echo [1/4] 检查并安装依赖...
python -m pip install PyQt6 pyinstaller -q >nul 2>&1

echo [2/4] 准备纯英文临时构建环境...
REM 使用系统临时目录，避免 C 盘根目录权限问题
set "TEMP_BUILD=%TEMP%\PortScanner_Build"
if exist "%TEMP_BUILD%" rmdir /s /q "%TEMP_BUILD%"
mkdir "%TEMP_BUILD%"

echo    复制 core, gui, utils, config.py...
xcopy /e /i /q "core" "%TEMP_BUILD%\core" >nul
xcopy /e /i /q "gui" "%TEMP_BUILD%\gui" >nul
xcopy /e /i /q "utils" "%TEMP_BUILD%\utils" >nul
copy /y "config.py" "%TEMP_BUILD%\" >nul

echo    复制 main.py 到临时目录根节点...
REM 强制读取一次文件，触发 OneDrive 下载（如果是云文件）
type "统一入口\main.py" >nul 2>&1 
copy /y "统一入口\main.py" "%TEMP_BUILD%\main.py" >nul

REM 严格校验文件是否真的复制过去了
if not exist "%TEMP_BUILD%\main.py" (
    echo.
    echo [致命错误] main.py 复制失败！
    echo 这通常是因为 OneDrive 文件未下载到本地（显示为云朵图标）。
    echo 请右键 "main.py" -^> 选择 "始终保留在此设备上"，然后再试。
    pause
    exit /b 1
)
echo    文件校验通过，准备打包。

echo [3/4] 在纯英文环境中执行打包...
cd /d "%TEMP_BUILD%"

python -m PyInstaller ^
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
    echo [错误] PyInstaller 打包失败！请查看上方详细日志。
    cd /d "%SCRIPT_DIR%"
    pause
    exit /b 1
)

echo [4/4] 提取打包结果并清理...
cd /d "%SCRIPT_DIR%"
if not exist "dist" mkdir "dist"
copy /y "%TEMP_BUILD%\dist\PortScanner.exe" "dist\PortScanner.exe" >nul
rmdir /s /q "%TEMP_BUILD%"

echo.
echo ============================================================
echo   打包成功！
echo ============================================================
echo 输出文件: dist\PortScanner.exe
echo.
pause
