# 这是对原始代码的修改版本，添加了GUI支持功能
# 主要修改了 MidiToKeysConverter 类，增加了信息返回功能

import mido
from typing import List, Tuple, Optional, Dict, Any
from collections import defaultdict
import json
import os
import sys
import sys
from datetime import datetime

# MIDI文件存放目录
MID_DIR_PATH = "midi/"
# 生成的播放代码存放目录
PLAY_CODE_DIR = "play_code/"


def get_base_directory():
    """
    获取程序的基础目录（exe或脚本所在目录）
    """
    if getattr(sys, "frozen", False):
        # 如果是通过pyinstaller打包的exe
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行的Python脚本
        return os.path.dirname(os.path.abspath(__file__))


def get_midi_dir_path():
    """获取midi文件夹的完整路径"""
    return os.path.join(get_base_directory(), "midi")


def get_play_code_dir_path():
    """获取play_code文件夹的完整路径"""
    return os.path.join(get_base_directory(), "play_code")


def ensure_directories_exist():
    """
    检查并创建必要的文件夹
    确保midi文件夹和play_code文件夹存在于exe所在目录
    """
    try:
        # 获取当前脚本所在目录（如果是exe文件，则是exe所在目录）
        if getattr(sys, "frozen", False):
            # 如果是通过pyinstaller打包的exe
            current_dir = os.path.dirname(sys.executable)
        else:
            # 如果是直接运行的Python脚本
            current_dir = os.path.dirname(os.path.abspath(__file__))

        # 需要创建的文件夹列表
        directories = [
            os.path.join(current_dir, "midi"),
            os.path.join(current_dir, "play_code"),
        ]

        created_count = 0
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                print(f"已创建文件夹: {directory}")
                created_count += 1
            else:
                print(f"文件夹已存在: {directory}")

        if created_count > 0:
            print(f"成功创建了 {created_count} 个文件夹")
        else:
            print("所有必要的文件夹都已存在")

    except Exception as e:
        print(f"创建文件夹时出现错误: {e}")
        # 即使创建文件夹失败，程序也应该继续运行


class MidiToKeysConverter:
    def __init__(self, log_callback=None):
        """
        初始化转换器
        log_callback: 用于GUI日志输出的回调函数
        """
        self.log_callback = log_callback

        # 标准音符映射 - 只映射自然音符（白键）
        # 标准中央C (C4) = MIDI 60
        self.base_note_mapping = {
            # 倍低音域 (只有5,6,7)
            36: "B",  # 倍低5 (C2)
            38: "N",  # 倍低6 (D2)
            40: "M",  # 倍低7 (E2)
            # 低音域 1234567
            48: "A",  # 低1 (C3)
            50: "S",  # 低2 (D3)
            52: "D",  # 低3 (E3)
            53: "F",  # 低4 (F3)
            55: "G",  # 低5 (G3)
            57: "H",  # 低6 (A3)
            59: "J",  # 低7 (B3)
            # 中音域 1234567
            60: "Q",  # 中1 (C4)
            62: "W",  # 中2 (D4)
            64: "E",  # 中3 (E4)
            65: "R",  # 中4 (F4)
            67: "T",  # 中5 (G4)
            69: "Y",  # 中6 (A4)
            71: "U",  # 中7 (B4)
            # 高音域 12345
            72: "1",  # 高1 (C5)
            74: "2",  # 高2 (D5)
            76: "3",  # 高3 (E5)
            77: "4",  # 高4 (F5)
            79: "5",  # 高5 (G5)
        }

        # 半音映射表（升号音符）
        self.sharp_notes = {
            # 倍低音域
            37: (36, True),  # C#2 -> 倍低5#
            39: (38, True),  # D#2 -> 倍低6#
            # 低音域
            49: (48, True),  # C#3 -> 低1#
            51: (50, True),  # D#3 -> 低2#
            54: (53, True),  # F#3 -> 低4#
            56: (55, True),  # G#3 -> 低5#
            58: (57, True),  # A#3 -> 低6#
            # 中音域
            61: (60, True),  # C#4 -> 中1#
            63: (62, True),  # D#4 -> 中2#
            66: (65, True),  # F#4 -> 中4#
            68: (67, True),  # G#4 -> 中5#
            70: (69, True),  # A#4 -> 中6#
            # 高音域
            73: (72, True),  # C#5 -> 高1#
            75: (74, True),  # D#5 -> 高2#
            78: (77, True),  # F#5 -> 高4#
            80: (79, True),  # G#5 -> 高5#
        }

        # 特殊功能键
        self.special_keys = {
            "sharp": "+",  # 升半音
            "flat": "-",  # 降半音
            "harmonic": "shift",  # 泛音
            "trill": "ctrl",  # 轮指
            "slide_up": "up",  # 上滑
            "slide_down": "down",  # 下滑
        }

    def _log(self, message: str):
        """内部日志方法"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def transpose_note(self, midi_note: int, semitones: int) -> int:
        """移调音符"""
        return midi_note + semitones

    def midi_note_to_key_sequence(
        self, midi_note: int, current_state: dict = None
    ) -> Tuple[List[str], dict]:
        """
        将MIDI音符转换为按键序列（包含升降音处理和状态管理）
        current_state: 当前的升降状态 {'sharp': bool, 'flat': bool}
        返回: (按键序列, 新状态)
        """
        if current_state is None:
            current_state = {"sharp": False, "flat": False}

        new_state = current_state.copy()
        key_sequence = []

        # 首先检查是否为自然音符
        if midi_note in self.base_note_mapping:
            # 如果当前有升降状态，需要复原到自然状态
            if current_state["sharp"]:
                key_sequence.append("-")  # 复原升号
                new_state["sharp"] = False
            elif current_state["flat"]:
                key_sequence.append("+")  # 复原降号
                new_state["flat"] = False

            key_sequence.append(self.base_note_mapping[midi_note])
            return key_sequence, new_state

        # 检查是否为升号音符
        if midi_note in self.sharp_notes:
            base_note, is_sharp = self.sharp_notes[midi_note]
            base_key = self.base_note_mapping[base_note]

            # 如果当前不是升号状态，需要切换到升号状态
            if current_state["flat"]:
                key_sequence.append("+")  # 先复原降号
                key_sequence.append("+")  # 再切换到升号
                new_state["flat"] = False
                new_state["sharp"] = True
            elif not current_state["sharp"]:
                key_sequence.append("+")  # 切换到升号状态
                new_state["sharp"] = True

            key_sequence.append(base_key)
            return key_sequence, new_state

        # 检查是否为降号音符（通过查找高一个半音的音符）
        higher_note = midi_note + 1
        if higher_note in self.base_note_mapping:
            base_key = self.base_note_mapping[higher_note]

            # 如果当前不是降号状态，需要切换到降号状态
            if current_state["sharp"]:
                key_sequence.append("-")  # 先复原升号
                key_sequence.append("-")  # 再切换到降号
                new_state["sharp"] = False
                new_state["flat"] = True
            elif not current_state["flat"]:
                key_sequence.append("-")  # 切换到降号状态
                new_state["flat"] = True

            key_sequence.append(base_key)
            return key_sequence, new_state

        # 如果无法映射，返回空列表而不是None，保持兼容性
        return [], current_state

    def midi_note_to_key(self, midi_note: int) -> Optional[str]:
        """向后兼容的简单映射函数"""
        key_sequence, _ = self.midi_note_to_key_sequence(midi_note)
        if key_sequence and len(key_sequence) == 1:
            return key_sequence[0]
        return None

    def get_note_name(self, midi_note: int) -> str:
        """获取MIDI音符的名称用于调试"""
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        octave = midi_note // 12 - 1
        note = note_names[midi_note % 12]
        return f"{note}{octave}"

    def analyze_midi_file(self, midi_file_path: str) -> dict:
        """分析MIDI文件的详细信息，用于调试"""
        try:
            # 首先检查文件是否存在
            if not os.path.exists(midi_file_path):
                return {"error": "文件不存在"}
            
            # 检查文件大小
            file_size = os.path.getsize(midi_file_path)
            if file_size == 0:
                return {"error": "文件为空"}
            
            # 检查文件是否为MIDI格式（基本头部检查）
            with open(midi_file_path, 'rb') as f:
                header = f.read(4)
                if header != b'MThd':
                    return {"error": "文件格式错误: 不是标准MIDI文件（缺少MThd头部标识）"}
            
            # 尝试读取MIDI文件
            mid = mido.MidiFile(midi_file_path)
            
        except Exception as e:
            error_msg = str(e)
            
            # 提供更友好的错误信息
            if "data byte must be in range 0..127" in error_msg:
                return {
                    "error": "MIDI文件格式错误: 包含非法数据字节（超出0-127范围）",
                    "detailed_error": error_msg,
                    "suggestions": [
                        "1. 检查文件是否损坏，尝试重新下载",
                        "2. 使用MIDI编辑软件（如MuseScore）重新导出为标准MIDI格式",
                        "3. 确认文件确实是MIDI格式而非其他音频格式",
                        "4. 尝试使用其他MIDI文件测试工具是否正常工作"
                    ]
                }
            elif "could not read" in error_msg.lower():
                return {
                    "error": "无法读取MIDI文件: 文件可能损坏或格式不正确",
                    "detailed_error": error_msg,
                    "suggestions": [
                        "1. 确认文件完整性（重新下载或复制）",
                        "2. 检查文件权限是否允许读取",
                        "3. 尝试用其他MIDI播放器测试文件"
                    ]
                }
            else:
                return {
                    "error": f"读取MIDI文件时发生未知错误: {error_msg}",
                    "detailed_error": error_msg,
                    "suggestions": [
                        "1. 检查文件是否为有效的MIDI格式",
                        "2. 尝试使用标准MIDI编辑器打开文件",
                        "3. 如果问题持续，请尝试其他MIDI文件"
                    ]
                }

        analysis = {
            "文件信息": {
                "音轨数量": len(mid.tracks),
                "时间分辨率": mid.ticks_per_beat,
                "文件类型": mid.type,
                "总时长": mid.length,
            },
            "音轨详情": [],
            "音符统计": defaultdict(int),
            "音域分析": {"最低音": 127, "最高音": 0, "未映射音符": set()},
        }

        for i, track in enumerate(mid.tracks):
            track_info = {
                "音轨号": i,
                "消息数量": len(track),
                "音符事件": 0,
                "程序变更": [],
                "音轨名称": None,
                "乐器名称": None,
            }

            for msg in track:
                if msg.type == "track_name":
                    track_info["音轨名称"] = msg.name
                elif msg.type == "program_change":
                    track_info["程序变更"].append(
                        f"通道{msg.channel}: 乐器{msg.program}"
                    )
                elif msg.type == "instrument_name":
                    track_info["乐器名称"] = msg.name
                elif msg.type == "note_on" and msg.velocity > 0:
                    track_info["音符事件"] += 1
                    analysis["音符统计"][msg.note] += 1
                    analysis["音域分析"]["最低音"] = min(
                        analysis["音域分析"]["最低音"], msg.note
                    )
                    analysis["音域分析"]["最高音"] = max(
                        analysis["音域分析"]["最高音"], msg.note
                    )
                    temp_state = {"sharp": False, "flat": False}
                    key_sequence, _ = self.midi_note_to_key_sequence(
                        msg.note, temp_state
                    )
                    if not key_sequence:
                        analysis["音域分析"]["未映射音符"].add(msg.note)

            analysis["音轨详情"].append(track_info)

        # 转换未映射音符为可读格式
        analysis["音域分析"]["未映射音符"] = [
            f"{note}({self.get_note_name(note)})"
            for note in sorted(analysis["音域分析"]["未映射音符"])
        ]

        return analysis

    def analyze_track_coverage(self, midi_file_path: str, track_num: int = 0, transpose: int = 0) -> dict:
        """分析单个音轨的音符覆盖率"""
        try:
            mid = mido.MidiFile(midi_file_path)
        except Exception as e:
            return {"error": f"无法读取MIDI文件: {e}"}
        
        if track_num >= len(mid.tracks):
            return {"error": f"音轨{track_num}不存在"}
        
        track = mid.tracks[track_num]
        track_notes = defaultdict(int)
        total_notes = 0
        mapped_notes = 0
        
        # 收集音轨中的音符
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                track_notes[msg.note] += 1
                total_notes += 1
        
        # 计算覆盖率
        temp_state = {"sharp": False, "flat": False}
        for note, count in track_notes.items():
            transposed_note = self.transpose_note(note, transpose)
            key_sequence, _ = self.midi_note_to_key_sequence(transposed_note, temp_state)
            if key_sequence:
                mapped_notes += count
        
        coverage_rate = (mapped_notes / total_notes * 100) if total_notes > 0 else 0
        
        return {
            "track_num": track_num,
            "total_notes": total_notes,
            "mapped_notes": mapped_notes,
            "coverage_rate": coverage_rate,
            "note_distribution": dict(track_notes)
        }
    
    def find_best_transpose_smart(self, midi_file_path: str, track_filter: List[int] = None) -> dict:
        """智能变调：优先保证主旋律不变调"""
        analysis = self.analyze_midi_file(midi_file_path)
        if "error" in analysis:
            return {"transpose": 0, "reason": "文件分析失败", "details": analysis}
        
        # 默认使用前2个音轨
        if track_filter is None:
            track_filter = [0, 1]
        
        # 确保音轨存在
        available_tracks = len(analysis["音轨详情"])
        track_filter = [t for t in track_filter if t < available_tracks]
        
        if not track_filter:
            return {"transpose": 0, "reason": "没有可用的音轨", "details": {}}
        
        # 分析每个音轨在不同变调下的覆盖率
        track_analysis = {}
        
        # 首先分析主旋律（第一个音轨）
        main_track = track_filter[0]
        main_track_coverage = {}
        
        # 尝试不同的变调值
        for transpose in range(-24, 25):
            coverage = self.analyze_track_coverage(midi_file_path, main_track, transpose)
            if "error" not in coverage:
                main_track_coverage[transpose] = coverage["coverage_rate"]
        
        # 检查主旋律在不变调时的覆盖率
        no_transpose_coverage = main_track_coverage.get(0, 0)
        
        # 如果主旋律不变调时覆盖率足够好（80%以上），则不变调
        if no_transpose_coverage >= 80.0:
            # 详细分析所有音轨在不变调时的情况
            details = {}
            for track_num in track_filter:
                coverage = self.analyze_track_coverage(midi_file_path, track_num, 0)
                if "error" not in coverage:
                    details[f"track_{track_num}"] = coverage
            
            return {
                "transpose": 0,
                "reason": f"主旋律(音轨{main_track})不变调覆盖率已达{no_transpose_coverage:.1f}%，保持不变调",
                "main_track_coverage": no_transpose_coverage,
                "details": details
            }
        
        # 如果主旋律覆盖率不够，寻找最佳的整体变调
        best_transpose = 0
        best_overall_score = 0
        
        for transpose in range(-24, 25):
            overall_score = 0
            track_details = {}
            
            for track_num in track_filter:
                coverage = self.analyze_track_coverage(midi_file_path, track_num, transpose)
                if "error" not in coverage:
                    # 主旋律权重更高
                    weight = 2.0 if track_num == main_track else 1.0
                    overall_score += coverage["coverage_rate"] * weight
                    track_details[f"track_{track_num}"] = coverage
            
            if overall_score > best_overall_score:
                best_overall_score = overall_score
                best_transpose = transpose
                best_details = track_details
        
        # 再次检查最佳变调下主旋律的覆盖率
        main_coverage_after = main_track_coverage.get(best_transpose, 0)
        
        return {
            "transpose": best_transpose,
            "reason": f"主旋律需要变调优化：{no_transpose_coverage:.1f}% → {main_coverage_after:.1f}%",
            "main_track_coverage": main_coverage_after,
            "overall_score": best_overall_score,
            "details": best_details
        }
    
    def find_best_transpose(self, midi_file_path: str) -> int:
        """找到最佳的移调半音数，使更多音符能被映射（保留原有接口）"""
        result = self.find_best_transpose_smart(midi_file_path, [0, 1])
        return result.get("transpose", 0)

    def convert_midi_file(
        self,
        midi_file_path: str,
        track_filter: List[int] = None,
        channel_filter: List[int] = None,
        transpose: int = 0,
    ) -> List[Tuple[float, List[str], dict]]:
        """
        转换MIDI文件为按键序列
        track_filter: 指定要处理的音轨列表，None表示处理所有音轨
        channel_filter: 指定要处理的MIDI通道列表，None表示处理所有通道
        transpose: 移调半音数（正数升调，负数降调）
        返回: [(时间戳, 按键序列, 调试信息), ...]
        """
        mid = mido.MidiFile(midi_file_path)
        events = []

        # 获取正确的tempo用于时间转换
        tempo = 500000  # 默认tempo (120 BPM)

        # 初始化状态管理
        current_state = {"sharp": False, "flat": False}

        for track_idx, track in enumerate(mid.tracks):
            if track_filter and track_idx not in track_filter:
                continue

            track_time = 0.0
            for msg in track:
                # 更新tempo
                if msg.type == "set_tempo":
                    tempo = msg.tempo

                # 更新时间
                track_time += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)

                # 处理音符事件
                if msg.type == "note_on" and msg.velocity > 0:
                    if channel_filter and msg.channel not in channel_filter:
                        continue

                    # 应用移调
                    transposed_note = self.transpose_note(msg.note, transpose)

                    # 使用状态管理的音符转换
                    result = self.midi_note_to_key_sequence(
                        transposed_note, current_state
                    )
                    key_sequence, new_state = result
                    current_state = new_state

                    # 跳过无法映射的音符
                    if not key_sequence:
                        continue

                    debug_info = {
                        "track": track_idx,
                        "channel": msg.channel,
                        "note": msg.note,
                        "transposed_note": transposed_note,
                        "note_name": self.get_note_name(msg.note),
                        "transposed_name": self.get_note_name(transposed_note),
                        "velocity": msg.velocity,
                        "mapped": key_sequence is not None,
                        "transpose": transpose,
                        "action": "press",
                    }
                    events.append((track_time, key_sequence, debug_info))

        # 按时间排序
        events.sort(key=lambda x: x[0])
        return events

    def convert_to_playback_data(
        self,
        midi_file_path: str,
        track_filter: List[int] = None,
        channel_filter: List[int] = None,
        transpose: int = 0,
        speed_multiplier: float = 1.0,
        octave_transpose: int = 0,
    ) -> List:
        """
        将MIDI文件转换为播放数据格式
        
        Args:
            speed_multiplier: 速度倍数（1.0=正常, 2.0=2倍速, 0.5=半速）
            octave_transpose: 八度变调（1=+8度, -1=-8度, 0=不变调）
        
        返回格式: [key1, key2, ..., delay, key1, key2, ..., delay, ...]
        """
        # 计算总变调量（半音变调 + 八度变调）
        total_transpose = transpose + (octave_transpose * 12)
        
        events = self.convert_midi_file(
            midi_file_path, track_filter, channel_filter, total_transpose
        )

        if not events:
            return []

        playback_data = []
        last_time = 0.0

        # 按时间分组事件
        grouped_events = {}
        for timestamp, key_sequence, debug_info in events:
            if timestamp not in grouped_events:
                grouped_events[timestamp] = []
            grouped_events[timestamp].extend(key_sequence)

        # 按时间顺序处理
        sorted_times = sorted(grouped_events.keys())

        for timestamp in sorted_times:
            # 添加延迟（如果需要）
            delay = timestamp - last_time
            if delay > 0 and last_time > 0:  # 第一个事件前不需要延迟
                # 应用倍速：倍速越高，延迟越短
                adjusted_delay = delay / speed_multiplier
                playback_data.append(round(adjusted_delay, 3))

            # 添加该时间点的所有按键
            playback_data.extend(grouped_events[timestamp])
            last_time = timestamp

        return playback_data

    def generate_playback_code(
        self,
        midi_file_path: str,
        output_file: str = None,
        track_filter: List[int] = None,
        channel_filter: List[int] = None,
        transpose: int = 0,
    ) -> str:
        """
        生成可直接运行的播放代码（新格式，支持GUI日志）
        """
        playback_data = self.convert_to_playback_data(
            midi_file_path, track_filter, channel_filter, transpose
        )

        if not playback_data:
            playback_data = []

        # 生成日志文件名（基于输出文件名）
        if output_file:
            log_file = output_file.replace(".py", "_log.txt")
        else:
            log_file = "play_log.txt"

        code_lines = []
        code_lines.append("import time")
        code_lines.append("import sys")
        code_lines.append("import os")
        code_lines.append("from datetime import datetime")
        code_lines.append("")
        code_lines.append("# 添加父目录到路径，以便导入pydd模块")
        code_lines.append(
            "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))"
        )
        code_lines.append("")

        # 日志文件路径
        code_lines.append(f"LOG_FILE = '{log_file}'")
        code_lines.append("")

        # 日志函数
        code_lines.append("def log_message(msg):")
        code_lines.append('    """写入日志到文件，供GUI读取"""')
        code_lines.append("    timestamp = datetime.now().strftime('%H:%M:%S')")
        code_lines.append("    log_entry = f'[{timestamp}] {msg}\\n'")
        code_lines.append("    try:")
        code_lines.append("        with open(LOG_FILE, 'a', encoding='utf-8') as f:")
        code_lines.append("            f.write(log_entry)")
        code_lines.append("        print(log_entry.strip())  # 同时输出到控制台")
        code_lines.append("    except:")
        code_lines.append(
            "        print(log_entry.strip())  # 如果文件写入失败，至少输出到控制台"
        )
        code_lines.append("")

        code_lines.append("# 清空日志文件")
        code_lines.append("try:")
        code_lines.append("    with open(LOG_FILE, 'w', encoding='utf-8') as f:")
        code_lines.append("        f.write('')")
        code_lines.append("except:")
        code_lines.append("    pass")
        code_lines.append("")

        code_lines.append("try:")
        code_lines.append("    # 在打包环境中，pydd模块应该已经可用")
        code_lines.append("    from pydd import PyDD")
        code_lines.append("except ImportError:")
        code_lines.append("    try:")
        code_lines.append("        # 尝试从父目录导入")
        code_lines.append("        import pydd")
        code_lines.append("        from pydd import PyDD")
        code_lines.append("    except ImportError:")
        code_lines.append("        log_message('❌ 错误: 找不到pydd模块')")
        code_lines.append("        log_message('💡 请确保pydd.py文件在项目根目录中')")
        code_lines.append("        sys.exit(1)")
        code_lines.append("")
        code_lines.append("try:")
        code_lines.append("    import keyboard")
        code_lines.append("    keyboard_available = True")
        code_lines.append("    log_message('✅ 键盘监听模块加载成功，按ESC可停止播放')")
        code_lines.append("except ImportError:")
        code_lines.append("    keyboard_available = False")
        code_lines.append(
            "    log_message('⚠️ 警告: 找不到keyboard模块，无法使用ESC停止功能')"
        )
        code_lines.append("    # 定义一个虚拟的keyboard模块")
        code_lines.append("    class DummyKeyboard:")
        code_lines.append("        @staticmethod")
        code_lines.append("        def is_pressed(key):")
        code_lines.append("            return False")
        code_lines.append("    keyboard = DummyKeyboard()")
        code_lines.append("")

        code_lines.append("try:")
        code_lines.append("    # 在打包环境中，DLL应该在exe同目录或临时目录")
        code_lines.append("    import sys")
        code_lines.append("    if getattr(sys, 'frozen', False):")
        code_lines.append("        # 打包环境，DLL在临时目录")
        code_lines.append(
            "        dll_path = os.path.join(sys._MEIPASS, 'dd.54900.dll')"
        )
        code_lines.append("    else:")
        code_lines.append("        # 开发环境")
        code_lines.append("        dll_path = './dd.54900.dll'")
        code_lines.append("    dd = PyDD(dll_path)")
        code_lines.append("    log_message('✅ 按键模拟模块加载成功')")
        code_lines.append("except Exception as e:")
        code_lines.append("    log_message(f'❌ 按键模拟模块加载失败: {e}')")
        code_lines.append("    sys.exit(1)")
        code_lines.append("")

        code_lines.append("# 按键映射说明:")
        code_lines.append("# 高音12345=12345, 中音1234567=QWERTYU")
        code_lines.append("# 低音1234567=ASDFGHJ, 倍低音567=BNM")
        code_lines.append("# 升半音=+, 降半音=- (状态管理，只在需要时切换)")
        code_lines.append("# 按ESC键可随时停止播放")
        if transpose != 0:
            direction = "升调" if transpose > 0 else "降调"
            code_lines.append(f"# 移调: {direction}{abs(transpose)}半音")
        if track_filter:
            code_lines.append(f"# 处理音轨: {track_filter}")
        code_lines.append("")

        # 生成播放数据
        code_lines.append("# 播放数据: 按键和延迟的混合列表")
        code_lines.append("# 数字代表延迟时间(秒)，字符串代表按键")
        code_lines.append("playback_data = [")

        # 将数据分组输出，方便阅读
        line_items = []
        for item in playback_data:
            if isinstance(item, (int, float)):
                if line_items:
                    code_lines.append(
                        "    "
                        + ", ".join(
                            f"'{i}'" if isinstance(i, str) else str(i)
                            for i in line_items
                        )
                        + ","
                    )
                    line_items = []
                line_items.append(item)
            else:
                line_items.append(item)

        if line_items:
            code_lines.append(
                "    "
                + ", ".join(
                    f"'{i}'" if isinstance(i, str) else str(i) for i in line_items
                )
            )

        code_lines.append("]")
        code_lines.append("")

        code_lines.append("def countdown():")
        code_lines.append('    """3秒倒计时"""')
        code_lines.append("    log_message('🎵 准备开始播放...')")
        code_lines.append("    log_message('💡 按ESC键可随时停止播放')")
        code_lines.append("    log_message('')")
        code_lines.append("    ")
        code_lines.append("    for i in range(3, 0, -1):")
        code_lines.append("        if keyboard.is_pressed('esc'):")
        code_lines.append(
            "            log_message('🛑 倒计时期间检测到ESC键，取消播放!')"
        )
        code_lines.append("            return False")
        code_lines.append("        log_message(f'⏰ {i}秒后开始播放...')")
        code_lines.append("        time.sleep(1)")
        code_lines.append("    ")
        code_lines.append("    log_message('🎶 开始播放!')")
        code_lines.append("    log_message('')")
        code_lines.append("    return True")
        code_lines.append("")
        code_lines.append("def play():")
        code_lines.append('    """播放MIDI转换后的按键序列"""')
        code_lines.append("    # 先进行3秒倒计时")
        code_lines.append("    if not countdown():")
        code_lines.append("        return")
        code_lines.append("    ")
        code_lines.append("    total_items = len(playback_data)")
        code_lines.append("    key_count = 0")
        code_lines.append("    delay_count = 0")
        code_lines.append("    ")
        code_lines.append("    # 统计按键和延迟数量")
        code_lines.append("    for item in playback_data:")
        code_lines.append("        if isinstance(item, (int, float)):")
        code_lines.append("            delay_count += 1")
        code_lines.append("        else:")
        code_lines.append("            key_count += 1")
        code_lines.append("    ")
        code_lines.append(
            "    log_message(f'📊 播放数据统计: {key_count}个按键, {delay_count}个延迟')"
        )
        code_lines.append("    log_message('')")
        code_lines.append("    ")
        code_lines.append("    start_time = time.time()")
        code_lines.append("    i = 0")
        code_lines.append(
            "    progress_step = max(1, total_items // 20)  # 显示20个进度点"
        )
        code_lines.append("    ")
        code_lines.append("    while i < len(playback_data):")
        code_lines.append("        if keyboard.is_pressed('esc'):")
        code_lines.append("            log_message('🛑 检测到ESC键，停止播放!')")
        code_lines.append("            elapsed = time.time() - start_time")
        code_lines.append("            log_message(f'⏱️ 播放时长: {elapsed:.1f}秒')")
        code_lines.append("            return")
        code_lines.append("        ")
        code_lines.append("        item = playback_data[i]")
        code_lines.append("        ")
        code_lines.append("        # 显示进度")
        code_lines.append("        if i % progress_step == 0:")
        code_lines.append("            progress = (i / total_items) * 100")
        code_lines.append("            log_message(f'🎼 播放进度: {progress:.1f}%')")
        code_lines.append("        ")
        code_lines.append("        # 如果是数字，则延迟")
        code_lines.append("        if isinstance(item, (int, float)):")
        code_lines.append("            time.sleep(item)")
        code_lines.append("        # 如果是字符串，则按键")
        code_lines.append("        else:")
        code_lines.append("            try:")
        code_lines.append("                # 状态切换按键需要额外延迟确保稳定")
        code_lines.append("                if item in ['+', '-']:")
        code_lines.append("                    dd.key_press(item, 0.03)")
        code_lines.append("                else:")
        code_lines.append("                    # 普通按键")
        code_lines.append("                    dd.key_press(item)")
        code_lines.append("            except Exception as e:")
        code_lines.append("                log_message(f'⚠️ 按键 {item} 执行失败: {e}')")
        code_lines.append("        ")
        code_lines.append("        i += 1")
        code_lines.append("")
        code_lines.append("    # 播放完成")
        code_lines.append("    elapsed = time.time() - start_time")
        code_lines.append("    log_message('✅ 播放完成')")
        code_lines.append("    log_message(f'⏱️ 总播放时长: {elapsed:.1f}秒')")
        code_lines.append("    log_message(f'🎹 共执行 {key_count} 个按键操作')")
        code_lines.append("")
        code_lines.append("if __name__ == '__main__':")
        code_lines.append("    try:")
        code_lines.append("        play()")
        code_lines.append("    except KeyboardInterrupt:")
        code_lines.append("        log_message('🛑 程序被中断')")
        code_lines.append("    except Exception as e:")
        code_lines.append("        log_message(f'❌ 播放出错: {e}')")
        code_lines.append("        import traceback")
        code_lines.append("        log_message(f'详细错误: {traceback.format_exc()}')")

        result = "\n".join(code_lines)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result)

        return result

    def generate_complete_data_file(
        self,
        midi_file_path: str,
        output_file: str = None,
        track_filter: List[int] = None,
        channel_filter: List[int] = None,
        transpose: int = 0,
        speed_multiplier: float = 1.0,
        octave_transpose: int = 0,
    ) -> Dict[str, Any]:
        """
        生成完整的播放数据文件（包含所有信息）

        Args:
            midi_file_path: MIDI文件路径
            output_file: 输出文件路径（可选，默认为MIDI同名JSON文件）
            track_filter: 音轨过滤器
            channel_filter: 通道过滤器
            transpose: 移调半音数
            speed_multiplier: 播放速度倍数（1.0=正常速度）
            octave_transpose: 八度变调（1=+8度, -1=-8度）

        Returns:
            Dict: 包含文件路径和处理结果的字典
        """
        # 分析MIDI文件
        analysis = self.analyze_midi_file(midi_file_path)
        if "error" in analysis:
            return {"error": analysis["error"], "success": False}

        # 转换为播放数据
        playback_data = self.convert_to_playback_data(
            midi_file_path, track_filter, channel_filter, transpose, 
            speed_multiplier, octave_transpose
        )

        if not playback_data:
            playback_data = []

        # 准备文件名
        base_name = (
            os.path.basename(midi_file_path).replace(".mid", "").replace(".midi", "")
        )

        # 如果没有指定输出文件路径，使用MIDI同名的JSON文件
        if not output_file:
            output_file = os.path.join(get_play_code_dir_path(), f"{base_name}.json")

        # 准备完整数据结构
        complete_data = {
            "version": "2.0",
            "type": "jx3_piano_complete",
            # 文件基本信息
            "filename": base_name,
            "midi_file": midi_file_path,
            "generation_time": datetime.now().isoformat(),
            # 处理参数
            "transpose": transpose,
            "speed_multiplier": speed_multiplier,
            "octave_transpose": octave_transpose,
            "processed_tracks": track_filter or [],
            "processed_channels": channel_filter or [],
            # MIDI文件分析信息
            "file_info": analysis["文件信息"],
            "track_details": analysis["音轨详情"],
            "note_statistics": analysis["音符统计"],
            # 播放数据
            "playback_data": playback_data,
            # 统计信息
            "statistics": {
                "total_tracks": len(analysis["音轨详情"]),
                "total_duration": analysis["文件信息"]["总时长"],
                "note_count": sum(analysis["音符统计"].values()),
                "operation_count": len(playback_data),
                "key_count": sum(1 for item in playback_data if isinstance(item, str)),
                "delay_count": sum(
                    1 for item in playback_data if isinstance(item, (int, float))
                ),
            },
            # 按键映射说明
            "key_mapping": {
                "description": "剑网三钢琴按键映射",
                "high_notes": "12345 -> 12345",
                "mid_notes": "1234567 -> QWERTYU",
                "low_notes": "1234567 -> ASDFGHJ",
                "extra_low_notes": "567 -> BNM",
                "sharp": "+ (升半音)",
                "flat": "- (降半音)",
            },
        }

        # 保存文件
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(complete_data, f, ensure_ascii=False, indent=2)

            if self.log_callback:
                self.log_callback(f"✅ 完整数据文件已生成: {output_file}")

            return {
                "output_file": output_file,
                "data": complete_data,
                "success": True,
            }

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ 保存文件失败: {e}")
            return {"error": str(e), "success": False}

    def print_analysis_summary(
        self, analysis: dict, transpose: int = 0
    ) -> Dict[str, Any]:
        """
        打印并返回分析摘要信息（修改为支持GUI）
        返回摘要信息字典，便于GUI使用
        """
        if "error" in analysis:
            error_msg = f"错误: {analysis['error']}"
            self._log(error_msg)
            return {"error": analysis["error"]}

        summary = {
            "tracks": analysis["文件信息"]["音轨数量"],
            "duration": analysis["文件信息"]["总时长"],
            "ticks_per_beat": analysis["文件信息"]["时间分辨率"],
            "transpose": transpose,
            "active_tracks": [],
            "note_range": {
                "lowest": analysis["音域分析"]["最低音"],
                "highest": analysis["音域分析"]["最高音"],
                "lowest_name": self.get_note_name(analysis["音域分析"]["最低音"]),
                "highest_name": self.get_note_name(analysis["音域分析"]["最高音"]),
            },
            "coverage": 0,
        }

        self._log("=" * 60)
        self._log("📄 MIDI文件分析摘要")
        self._log("=" * 60)

        # 基本信息
        self._log(f"🎵 音轨数量: {summary['tracks']}")
        self._log(f"⏱️  总时长: {summary['duration']:.2f}秒")
        self._log(f"🎼 时间分辨率: {summary['ticks_per_beat']} ticks/beat")

        # 音轨信息
        self._log(f"\n🎹 有效音轨:")
        for track_info in analysis["音轨详情"]:
            if track_info["音符事件"] > 0:
                name = track_info["音轨名称"] or "未命名"
                track_summary = {
                    "index": track_info["音轨号"],
                    "note_count": track_info["音符事件"],
                    "name": name,
                }
                summary["active_tracks"].append(track_summary)
                self._log(
                    f"  音轨{track_info['音轨号']}: {track_info['音符事件']}个音符 ({name})"
                )

        # 音域信息
        self._log(f"\n🎼 音域范围:")
        self._log(f"  最低音: {summary['note_range']['lowest_name']}")
        self._log(f"  最高音: {summary['note_range']['highest_name']}")

        # 移调信息
        if transpose != 0:
            direction = "升调" if transpose > 0 else "降调"
            self._log(f"  建议移调: {direction}{abs(transpose)}半音")

        # 覆盖率信息
        total_notes = sum(analysis["音符统计"].values())
        mapped_notes = 0
        temp_state = {"sharp": False, "flat": False}
        for note, count in analysis["音符统计"].items():
            transposed = self.transpose_note(note, transpose)
            key_sequence, _ = self.midi_note_to_key_sequence(transposed, temp_state)
            if key_sequence:
                mapped_notes += count

        coverage = (mapped_notes / total_notes) * 100 if total_notes > 0 else 0
        summary["coverage"] = coverage
        self._log(f"\n📊 音符覆盖率: {coverage:.1f}%")

        if coverage < 70:
            self._log("⚠️  覆盖率较低，可能需要调整移调设置")

        self._log("=" * 60)
        return summary

    def convert_midi(
        self, midi_file_path: str, track_filter: List[int] = None, transpose: int = None,
        speed_multiplier: float = 1.0, octave_transpose: int = 0
    ) -> Dict[str, Any]:
        """
        完整的MIDI转换流程（修改为返回结果信息）
        返回转换结果字典
        """
        self._log(f"🎵 正在转换: {midi_file_path}")
        self._log("")

        try:
            # 第一步：分析MIDI文件
            analysis = self.analyze_midi_file(midi_file_path)

            if "error" in analysis:
                error_msg = f"错误: {analysis['error']}"
                self._log(error_msg)
                return {"success": False, "error": analysis["error"]}

            # 第二步：确定最佳移调（如果未指定）
            if transpose is None:
                transpose = self.find_best_transpose(midi_file_path)

            # 第三步：确定要处理的音轨（如果未指定）
            if track_filter is None:
                best_tracks = []
                for i, track_info in enumerate(analysis["音轨详情"]):
                    if track_info["音符事件"] > 10:
                        best_tracks.append((i, track_info["音符事件"]))

                best_tracks.sort(key=lambda x: x[1], reverse=True)
                track_filter = [
                    track[0] for track in best_tracks[:2]
                ]  # 取前2个最佳音轨

            # 第四步：获取分析摘要
            summary = self.print_analysis_summary(analysis, transpose)

            # 第五步：生成播放文件
            if track_filter:
                base_name = os.path.basename(midi_file_path)
                base_name = base_name.replace(".mid", "").replace(".midi", "")
                output_file = os.path.join(
                    get_play_code_dir_path(), f"play_{base_name}_{transpose}.py"
                )

                self._log(f"\n正在生成播放文件...")
                code = self.generate_playback_code(
                    midi_file_path,
                    output_file,
                    track_filter=track_filter,
                    transpose=transpose,
                )

                self._log(f"✅ 转换完成!")
                self._log(f"📁 生成文件: {os.path.basename(output_file)}")
                self._log(f"🎼 处理音轨: {track_filter}")
                self._log(f"🎵 移调: {transpose}半音")
                if speed_multiplier != 1.0:
                    self._log(f"⚡ 播放速度: {speed_multiplier}倍")
                if octave_transpose != 0:
                    octave_desc = f"+{octave_transpose}" if octave_transpose > 0 else str(octave_transpose)
                    self._log(f"🎼 八度变调: {octave_desc}度")

                return {
                    "success": True,
                    "output_file": output_file,
                    "track_filter": track_filter,
                    "transpose": transpose,
                    "speed_multiplier": speed_multiplier,
                    "octave_transpose": octave_transpose,
                    "summary": summary,
                    "analysis": analysis,
                }
            else:
                error_msg = "❌ 没有找到合适的音轨"
                self._log(error_msg)
                return {"success": False, "error": "没有找到合适的音轨"}

        except Exception as e:
            error_msg = f"❌ 转换失败: {e}"
            self._log(error_msg)
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}


# 主逻辑（保持向后兼容）
def build_music(
    midi_file_path: str,
    track_nums: List[int] = None,
    transpose: int = None,
    speed_multiplier: float = 1.0,
    octave_transpose: int = 0,
    log_callback=None,
) -> Optional[str]:
    """
    快速转换MIDI文件

    参数:
    midi_file_path: MIDI文件路径
    track_nums: 要处理的音轨编号列表，None为自动选择
    transpose: 移调半音数，None为自动选择
    speed_multiplier: 播放速度倍数（1.0=正常, 1.25=1.25倍速, 1.5=1.5倍速, 1.75=1.75倍速, 2.0=2倍速）
    octave_transpose: 八度变调（1=+8度, -1=-8度, 0=不变调）
    log_callback: 日志回调函数（用于GUI）

    返回:
    转换成功时返回输出文件路径，失败时返回None
    """
    converter = MidiToKeysConverter(log_callback)
    ensure_directories_exist()
    result = converter.convert_midi(midi_file_path, track_nums, transpose, 
                                   speed_multiplier, octave_transpose)

    if result["success"]:
        return result["output_file"]
    else:
        return None


if __name__ == "__main__":
    # 检查并创建必要的文件夹
    ensure_directories_exist()

    # 测试代码
    midi_file = "我的祖国.mid"  # 替换为你的MIDI文件路径
    file_path = os.path.join(get_midi_dir_path(), midi_file)
    build_music(file_path, track_nums=[0, 1], transpose=None)
