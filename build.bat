chcp 65001
@echo off
echo ============================================================
echo 剑网三自动演奏工具 - 快速打包批处理脚本
echo ============================================================
echo.

REM 检查Python环境
if not exist ".venv\Scripts\python.exe" (
    echo 错误：未找到虚拟环境，请确保已正确设置Python虚拟环境
    pause
    exit /b 1
)

echo 正在启动打包程序...
echo.

echo 正在激活虚拟环境...
conda activate music

echo 正在运行打包程序...
python build_exe.py

echo.
echo 打包完成！
pause
