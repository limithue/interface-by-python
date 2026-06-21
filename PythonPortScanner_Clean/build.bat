@echo off
chcp 936 >nul
echo ============================================================
echo   Python Port Scanner - Windows EXE Build Script
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [INFO] Python version: %PYVER%

echo.
echo [1/5] Checking project structure...
if not exist "main.py" (
    echo [ERROR] main.py not found. Please run this script in project root.
    pause
    exit /b 1
)
if not exist "core\__init__.py" (
    echo [ERROR] core package incomplete, missing __init__.py
    pause
    exit /b 1
)
if not exist "gui\__init__.py" (
    echo [ERROR] gui package incomplete, missing __init__.py
    pause
    exit /b 1
)
if not exist "utils\__init__.py" (
    echo [ERROR] utils package incomplete, missing __init__.py
    pause
    exit /b 1
)
echo   Project structure OK

echo.
echo [2/5] Checking dependencies...
python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo   PyQt6 not found, installing...
    python -m pip install PyQt6
    if errorlevel 1 (
        echo [ERROR] PyQt6 installation failed
        pause
        exit /b 1
    )
)
echo   PyQt6 ready

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo   PyInstaller not found, installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller installation failed
        pause
        exit /b 1
    )
)
for /f "tokens=2" %%v in ('python -m PyInstaller --version 2^>^&1') do set PIVER=%%v
echo   PyInstaller %PIVER% ready

echo.
echo [3/5] Cleaning old builds...
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist" rmdir /s /q "dist" 2>nul
if exist "*.spec" del /q "*.spec" 2>nul
echo   Clean done

echo.
echo [4/5] Building EXE...
echo   Mode: onedir + windowed (GUI mode)
echo   Feature: config/logs/reports persistent
echo.

REM Build PyInstaller command using SET to avoid long line issues
set "PI_CMD=python -m PyInstaller"
set "PI_ARGS=--onedir --windowed --name PortScanner --clean --noconfirm"
set "PI_ARGS=%PI_ARGS% --paths %~dp0"
set "PI_ARGS=%PI_ARGS% --collect-all core --collect-all gui --collect-all utils"
set "PI_ARGS=%PI_ARGS% --hidden-import PyQt6.sip --hidden-import PyQt6.QtCore"
set "PI_ARGS=%PI_ARGS% --hidden-import PyQt6.QtGui --hidden-import PyQt6.QtWidgets"
set "PI_SCRIPT=main.py"

echo Running: %PI_CMD% %PI_ARGS% %PI_SCRIPT%
%PI_CMD% %PI_ARGS% %PI_SCRIPT%

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    echo.
    echo [Common causes and solutions]
    echo   1. Path contains Chinese or special chars -^> Move to pure English path
    echo   2. Some modules not installed -^> Run: python -m pip install -r requirements.txt
    echo   3. Antivirus blocked PyInstaller -^> Add exclusion or disable temporarily
    echo   4. Insufficient permissions -^> Run as administrator
    echo   5. PyQt6 version incompatible -^> Try: python -m pip install PyQt6==6.4.2
    echo.
    pause
    exit /b 1
)

echo.
echo [5/5] Post-build...
if not exist "dist\PortScanner\reports" mkdir "dist\PortScanner\reports"
if not exist "dist\PortScanner\logs" mkdir "dist\PortScanner\logs"
echo   Created reports/ directory
echo   Created logs/ directory

echo.
echo ============================================================
echo   Build Success!
echo ============================================================
echo.
echo Output: dist\PortScanner\
echo Executable: dist\PortScanner\PortScanner.exe
echo.
echo Directory structure:
echo   PortScanner\
echo   +-- PortScanner.exe      (main program)
echo   +-- _internal\            (dependencies)
echo   +-- reports\              (scan reports output)
echo   +-- logs\                 (log output)
echo.
echo Usage:
echo   1. Double-click PortScanner.exe to launch GUI
echo   2. Command line: PortScanner.exe --help
echo   3. Run as admin for SYN stealth scan support
echo   4. Config file scanner_config.json auto-saved next to exe
echo.
echo Distribution:
echo   Copy dist\PortScanner\ folder to target PC (no Python needed)
echo.
pause
