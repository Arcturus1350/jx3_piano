#!/usr/bin/env python3
"""
自动化打包脚本
使用PyInstaller将Python脚本打包成单一的可执行文件
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path


def main():
    """主打包函数"""
    # 获取当前脚本所在目录
    current_dir = Path(__file__).parent.absolute()

    print("=" * 60)
    print("剑网三自动演奏工具 - 自动化打包脚本")
    print("=" * 60)

    # 检查必要文件是否存在
    required_files = ["gui.py", "build_music.py", "pydd.py", "dd.54900.dll", "icon.ico"]

    missing_files = []
    for file in required_files:
        if not (current_dir / file).exists():
            missing_files.append(file)

    if missing_files:
        print(f"错误：缺少必要文件: {', '.join(missing_files)}")
        return False

    print("✓ 所有必要文件检查完成")

    # 清理之前的构建文件
    build_dirs = ["build", "dist", "__pycache__"]
    for dir_name in build_dirs:
        dir_path = current_dir / dir_name
        if dir_path.exists():
            print(f"清理目录: {dir_path}")
            try:
                shutil.rmtree(dir_path)
            except PermissionError as e:
                print(f"警告：无法删除 {dir_path}，可能文件正在使用中")
                print(f"错误详情: {e}")
                # 尝试重命名旧目录
                backup_path = current_dir / f"{dir_name}_backup_{int(time.time())}"
                try:
                    dir_path.rename(backup_path)
                    print(f"已将旧目录重命名为: {backup_path}")
                except Exception as e2:
                    print(f"重命名也失败了: {e2}")
                    print("请手动关闭可能正在运行的程序后重试")

    # 删除旧的spec文件
    spec_file = current_dir / "gui.spec"
    if spec_file.exists():
        spec_file.unlink()

    print("✓ 清理完成")

    # 获取Python环境路径
    python_exe = sys.executable
    venv_dir = Path(python_exe).parent
    pyinstaller_exe = venv_dir / "pyinstaller.exe"

    # 如果找不到pyinstaller.exe，尝试Scripts目录
    if not pyinstaller_exe.exists():
        pyinstaller_exe = venv_dir / "Scripts" / "pyinstaller.exe"

    if not pyinstaller_exe.exists():
        print("错误：找不到pyinstaller.exe")
        return False

    # 构建PyInstaller命令
    cmd = [
        str(pyinstaller_exe),
        "--onefile",  # 打包成单一exe文件
        "--windowed",  # GUI模式，不显示控制台
        "--noconfirm",  # 不询问确认
        f"--icon={current_dir / 'icon.ico'}",  # 设置图标
        f"--add-data={current_dir / 'dd.54900.dll'};.",  # 添加DLL文件
        "--uac-admin",  # 请求管理员权限
        "--clean",  # 清理临时文件
        "gui.py",  # 主脚本
    ]

    print("开始打包...")
    print(f"执行命令: {' '.join(cmd)}")
    print("-" * 40)

    try:
        # 执行打包命令
        result = subprocess.run(
            cmd, cwd=current_dir, capture_output=False, text=True, check=True
        )

        print("-" * 40)
        print("✓ 打包完成！")

        # 检查输出文件
        exe_file = current_dir / "dist" / "gui.exe"
        if exe_file.exists():
            file_size = exe_file.stat().st_size / (1024 * 1024)  # MB
            print(f"输出文件: {exe_file}")
            print(f"文件大小: {file_size:.2f} MB")

            # 创建发布目录
            release_dir = current_dir / "release"
            release_dir.mkdir(exist_ok=True)

            # 复制exe到发布目录
            release_exe = release_dir / "剑网三自动演奏工具.exe"
            shutil.copy2(exe_file, release_exe)
            print(f"发布文件: {release_exe}")

            print("\n" + "=" * 60)
            print("打包成功完成！")
            print("=" * 60)
            return True
        else:
            print("错误：未找到输出的exe文件")
            return False

    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        return False
    except Exception as e:
        print(f"发生错误: {e}")
        return False


if __name__ == "__main__":
    if main():
        input("按任意键退出...")
    else:
        input("按任意键退出...")
        sys.exit(1)
