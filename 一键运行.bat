@echo off
chcp 65001 >nul
title Agent 工具清理助手
cd /d "%~dp0"

echo ============================================
echo   正在启动 Agent 工具清理助手...
echo ============================================
echo.

where py >nul 2>nul
if not errorlevel 1 goto use_py

where python >nul 2>nul
if not errorlevel 1 goto use_python

echo [错误] 未检测到 Python。
echo.
echo 请先安装 Python 3.8 或更高版本，然后重新双击本文件。
echo 下载地址: https://www.python.org/downloads/
echo.
pause
exit /b 1

:use_py
py agent_tool_cleaner.py
goto end

:use_python
python agent_tool_cleaner.py
goto end

:end
echo.
echo 按任意键关闭窗口...
pause >nul
