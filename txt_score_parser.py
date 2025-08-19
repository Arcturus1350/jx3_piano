#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TXT乐谱解析器
支持从TXT文件解析乐谱并转换为JX3演奏JSON格式

语法规范：
- 第一行：BPM（如120）
- 第二行：节拍（如4/4）
- 音轨：使用|作为小节分割线

音符规范：
- 基本音符：1234567（do re mi fa so la xi），0（休止符）
- 音区标记：+（高八度），-（低八度），--（超低八度），无标记（中音区）
- 升降号：#（升半音），b（降半音）
- 时值标记：_（八分音符），__（十六分音符），.（附点，延长1.5倍）
- 演奏技巧：~（上颤音），*（下颤音），&（泛音），@（轮指）
- 和弦：[135]（同时按下多个音符）
- 装饰音：{123}（前面是装饰音，最后一个是主音）
- 三连音：<123>（在指定时值内平均演奏三个音符）

空格处理：
- 空格不敏感，会被自动忽略
- 可以用空格分隔音符以提高可读性

重要概念区分：
- 音区（+、-、--）：控制八度高低，如+1是高八度的do
- 升降号（#、b）：控制半音升降，如#1是升do，在游戏中通过+/-键切换

作者：AI Assistant
日期：2024-12
"""

import re
import json
import math
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Note:
    """音符数据结构"""
    pitch: int           # 音高 (1-7)
    octave: str          # 音区 ('', '+', '-', '--')
    accidental: str      # 升降号 ('', '#', 'b')
    duration: str        # 时值 ('', '_', '__', '.')
    modifier: str        # 修饰符 ('', '~', '*', '&', '@')
    is_rest: bool = False  # 是否为休止符


@dataclass
class Chord:
    """和弦数据结构"""
    notes: List[Note]    # 和弦中的音符
    duration: str        # 时值
    modifier: str        # 修饰符


@dataclass
class Grace:
    """装饰音数据结构"""
    grace_notes: List[Note]  # 装饰音符
    main_note: Union[Note, Chord]  # 主音（可能是单音或和弦）
    duration: str        # 时值
    modifier: str        # 修饰符


@dataclass
class Triplet:
    """三连音数据结构"""
    notes: List[Union[Note, Chord]]    # 三个音符（固定3个，可以是单音符、和弦或休止符）
    duration: str        # 时值
    modifier: str        # 修饰符
    accidental: str      # 整体升降号


@dataclass
class ParseError:
    """解析错误信息"""
    line: int
    position: int
    message: str
    context: str


@dataclass
class TimeEvent:
    """时间轴事件"""
    time: float          # 事件发生的时间（秒）
    event_type: str      # 事件类型：'key_press', 'key_release', 'modifier_press', 'modifier_release'
    key: str            # 按键名称
    track_id: int       # 音轨ID


class TxtScoreParser:
    """TXT乐谱解析器"""
    
    def __init__(self):
        # 音符到游戏按键的映射
        self.note_to_key = {
            1: 'Q', 2: 'W', 3: 'E', 4: 'R', 
            5: 'T', 6: 'Y', 7: 'U'
        }
        
        # 小键盘对应关系（仅用于提示）
        self.numpad_reference = {
            1: '小键盘1', 2: '小键盘2', 3: '小键盘3', 4: '小键盘4',
            6: '小键盘6', 7: '小键盘7'
        }
        
        # 音区偏移映射（以MIDI音符号为单位）
        self.octave_offset = {
            '--': -24,  # 下下八度（超低音区）
            '-': -12,   # 下八度（低音区）
            '': 0,      # 中音区（标准音区）
            '+': 12     # 上八度（高音区）
        }
        
        # 支持的节拍
        self.supported_beats = ['2/4', '3/4', '4/4']
        
        # 修饰符对应的特殊按键
        self.modifier_keys = {
            '~': '↑',     # 上颤音
            '*': '↓',     # 下颤音 
            '&': 'shift', # 泛音
            '@': 'ctrl'   # 轮指
        }
        
        # 时值对应的持续时间（以四分音符为1.0）
        self.duration_values = {
            '': 1.0,      # 四分音符
            '_': 0.5,     # 八分音符
            '__': 0.25,   # 十六分音符
            '.': 1.5      # 浮点（四分音符的1.5倍）
        }
        
        # 解析状态
        self.reset_parse_state()
    
    def reset_parse_state(self):
        """重置解析状态"""
        self.bpm = 0
        self.time_signature = ""
        self.beats_per_measure = 4
        self.beat_unit = 4
        self.errors = []
        self.warnings = []
        self.total_measures = 0
        self.total_notes = 0
        self.total_duration = 0.0
        self.current_line = 0
        self.current_sharp_flat_state = {'sharp': False, 'flat': False}
    
    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        解析TXT乐谱文件
        
        Args:
            file_path: TXT文件路径
            
        Returns:
            解析结果字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_content(content)
        except Exception as e:
            return {
                "success": False,
                "error": f"文件读取失败: {str(e)}",
                "errors": [ParseError(0, 0, f"文件读取失败: {str(e)}", "")]
            }
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """
        解析TXT乐谱内容
        
        Args:
            content: 乐谱文本内容
            
        Returns:
            解析结果字典
        """
        self.reset_parse_state()
        lines = content.strip().split('\n')
        
        if len(lines) < 3:
            self.errors.append(ParseError(
                1, 0, "文件内容不完整，至少需要BPM、节拍和一行音符", content
            ))
            return self._create_error_result()
        
        # 第一轮：语法检查
        result = self._first_pass_validation(lines)
        if not result["success"]:
            return result
        
        # 第二轮：时间和按键计算
        result = self._second_pass_generation(lines)
        return result
    
    def _first_pass_validation(self, lines: List[str]) -> Dict[str, Any]:
        """第一轮：语法验证"""
        print("🔍 第一轮检查：语法验证")
        print("=" * 40)
        
        # 检查BPM
        try:
            self.bpm = int(lines[0].strip())
            if self.bpm <= 0 or self.bpm > 300:
                self.errors.append(ParseError(
                    1, 0, f"BPM值无效: {self.bpm}，应在1-300之间", lines[0]
                ))
        except ValueError:
            self.errors.append(ParseError(
                1, 0, f"BPM格式错误: '{lines[0].strip()}'，应为数字", lines[0]
            ))
        
        # 检查节拍
        self.time_signature = lines[1].strip()
        if self.time_signature not in self.supported_beats:
            self.errors.append(ParseError(
                2, 0, f"不支持的节拍: '{self.time_signature}'，支持: {', '.join(self.supported_beats)}", 
                lines[1]
            ))
        else:
            beats, unit = map(int, self.time_signature.split('/'))
            self.beats_per_measure = beats
            self.beat_unit = unit
        
        # 检查音轨内容
        score_lines = lines[2:]
        measures = []
        
        for line_idx, line in enumerate(score_lines, start=3):
            self.current_line = line_idx
            line = line.strip()
            if not line:
                continue
                
            # 分割小节
            if line.startswith('|') and line.endswith('|'):
                line = line[1:-1]  # 移除首尾的|
            
            measure_parts = line.split('|')
            for part_idx, measure in enumerate(measure_parts):
                if measure.strip():
                    measures.append((line_idx, part_idx, measure.strip()))
        
        # 验证每个小节
        for line_idx, part_idx, measure in measures:
            self._validate_measure(measure, line_idx, part_idx)
        
        self.total_measures = len(measures)
        
        if self.errors:
            return self._create_error_result()
        
        # 输出第一轮检查结果
        print(f"✅ BPM: {self.bpm}")
        print(f"✅ 节拍: {self.time_signature}")
        print(f"✅ 小节数: {self.total_measures}")
        print(f"✅ 音符数: {self.total_notes}")
        
        if self.warnings:
            print("\n⚠️ 警告:")
            for warning in self.warnings:
                print(f"   第{warning.line}行: {warning.message}")
        
        return {"success": True, "measures": measures}
    
    def _validate_measure(self, measure: str, line_idx: int, part_idx: int):
        """验证单个小节的语法和节拍"""
        tokens = self._tokenize_measure(measure)
        measure_duration = 0.0
        note_count = 0
        
        for token in tokens:
            try:
                parsed_token = self._parse_token(token)
                if parsed_token:
                    duration = self._get_token_duration(parsed_token)
                    measure_duration += duration
                    note_count += self._count_notes_in_token(parsed_token)
            except Exception as e:
                self.errors.append(ParseError(
                    line_idx, part_idx, f"音符语法错误: '{token}' - {str(e)}", measure
                ))
        
        # 检查小节时值是否正确
        expected_duration = float(self.beats_per_measure)
        if abs(measure_duration - expected_duration) > 0.001:
            self.errors.append(ParseError(
                line_idx, part_idx, 
                f"小节时值不匹配: 期望{expected_duration}拍，实际{measure_duration:.3f}拍", 
                measure
            ))
        
        self.total_notes += note_count
    
    def _tokenize_measure(self, measure: str) -> List[str]:
        """将小节分解为token"""
        tokens = []
        i = 0
        
        while i < len(measure):
            char = measure[i]
            
            # 跳过空格
            if char == ' ':
                i += 1
                continue
            
            if char == '<':
                # 三连音开始
                angle_count = 1
                j = i + 1
                triplet_token = char
                
                while j < len(measure) and angle_count > 0:
                    triplet_token += measure[j]
                    if measure[j] == '<':
                        angle_count += 1
                    elif measure[j] == '>':
                        angle_count -= 1
                    j += 1
                
                if angle_count > 0:
                    raise ValueError(f"未匹配的三连音括号: {triplet_token}")
                
                # 继续读取时值和修饰符
                while j < len(measure) and measure[j] in '_.~*&@':
                    triplet_token += measure[j]
                    j += 1
                
                tokens.append(triplet_token)
                i = j
                continue
            
            if char == '{':
                # 装饰音开始
                brace_count = 1
                j = i + 1
                grace_token = char
                
                while j < len(measure) and brace_count > 0:
                    grace_token += measure[j]
                    if measure[j] == '{':
                        brace_count += 1
                    elif measure[j] == '}':
                        brace_count -= 1
                    j += 1
                
                if brace_count > 0:
                    raise ValueError(f"未匹配的装饰音括号: {grace_token}")
                
                # 继续读取时值和修饰符
                while j < len(measure) and measure[j] in '_.~*&@':
                    grace_token += measure[j]
                    j += 1
                
                tokens.append(grace_token)
                i = j
                continue
            
            if char == '[':
                # 和弦开始
                chord_token = char
                
                # 找到匹配的]
                bracket_count = 1
                j = i + 1
                
                while j < len(measure) and bracket_count > 0:
                    chord_token += measure[j]
                    if measure[j] == '[':
                        bracket_count += 1
                    elif measure[j] == ']':
                        bracket_count -= 1
                    j += 1
                
                if bracket_count > 0:
                    raise ValueError(f"未匹配的和弦括号: {chord_token}")
                
                # 继续读取时值和修饰符
                while j < len(measure) and measure[j] in '_.~*&@':
                    chord_token += measure[j]
                    j += 1
                
                tokens.append(chord_token)
                i = j
                continue
            
            # 普通音符或带升降号的和弦：解析单个音符及其修饰符
            current_token = ""
            
            # 读取升降号
            if char in '#b':
                current_token += char
                i += 1
                if i >= len(measure):
                    break
                char = measure[i]
                
                # 检查升降号后面是否是和弦或三连音
                if char == '[':
                    # 带升降号的和弦
                    bracket_count = 1
                    j = i + 1
                    chord_token = current_token + char
                    
                    while j < len(measure) and bracket_count > 0:
                        chord_token += measure[j]
                        if measure[j] == '[':
                            bracket_count += 1
                        elif measure[j] == ']':
                            bracket_count -= 1
                        j += 1
                    
                    if bracket_count > 0:
                        raise ValueError(f"未匹配的和弦括号: {chord_token}")
                    
                    # 继续读取时值和修饰符
                    while j < len(measure) and measure[j] in '_.~*&@':
                        chord_token += measure[j]
                        j += 1
                    
                    tokens.append(chord_token)
                    i = j
                    continue
                elif char == '<':
                    # 带升降号的三连音
                    angle_count = 1
                    j = i + 1
                    triplet_token = current_token + char
                    
                    while j < len(measure) and angle_count > 0:
                        triplet_token += measure[j]
                        if measure[j] == '<':
                            angle_count += 1
                        elif measure[j] == '>':
                            angle_count -= 1
                        j += 1
                    
                    if angle_count > 0:
                        raise ValueError(f"未匹配的三连音括号: {triplet_token}")
                    
                    # 继续读取时值和修饰符
                    while j < len(measure) and measure[j] in '_.~*&@':
                        triplet_token += measure[j]
                        j += 1
                    
                    tokens.append(triplet_token)
                    i = j
                    continue
            
            # 读取音区标记
            while i < len(measure) and char in '+-':
                current_token += char
                i += 1
                if i >= len(measure):
                    break
                char = measure[i]
            
            # 读取音符（数字）
            if i < len(measure) and char.isdigit():
                current_token += char
                i += 1
                if i >= len(measure):
                    if current_token:
                        tokens.append(current_token)
                    break
                char = measure[i] if i < len(measure) else ''
            else:
                if current_token:
                    tokens.append(current_token)
                i += 1
                continue
            
            # 读取时值
            while i < len(measure) and char in '_.':
                current_token += char
                i += 1
                if i >= len(measure):
                    break
                char = measure[i]
            
            # 读取修饰符
            if i < len(measure) and char in '~*&@':
                current_token += char
                i += 1
            
            if current_token:
                tokens.append(current_token)
        
        return tokens
    
    def _parse_token(self, token: str) -> Union[Note, Chord, Grace, Triplet, None]:
        """解析单个token"""
        if not token:
            return None
        
        # 三连音 <123> 或 #<123>
        if (token.startswith('<') or (len(token) > 1 and token[0] in '#b' and token[1] == '<')) and '>' in token:
            return self._parse_triplet(token)
        
        # 装饰音 {123} 或 #{123}
        if (token.startswith('{') or (len(token) > 1 and token[0] in '#b' and token[1] == '{')) and '}' in token:
            return self._parse_grace_note(token)
        
        # 和弦 [123] 或 #[123]
        if (token.startswith('[') or (len(token) > 1 and token[0] in '#b' and token[1] == '[')) and ']' in token:
            return self._parse_chord(token)
        
        # 单音符
        return self._parse_single_note(token)
    
    def _parse_single_note(self, token: str) -> Note:
        """解析单个音符"""
        # 正则表达式匹配: (升降号)(音区)(音符)(时值)(修饰符)
        pattern = r'^([#b]?)([+\-]*)([0-7])([_.]*)([~*&@]?)$'
        match = re.match(pattern, token)
        
        if not match:
            raise ValueError(f"音符格式错误: {token}")
        
        accidental, octave, pitch_str, duration, modifier = match.groups()
        
        pitch = int(pitch_str)
        is_rest = (pitch == 0)
        
        if not is_rest and pitch not in range(1, 8):
            raise ValueError(f"音符超出范围: {pitch}，应在1-7之间")
        
        # 检查音区是否过高或过低
        if octave in ['++', '+++'] or len(octave) > 2:
            self.warnings.append(ParseError(
                self.current_line, 0, 
                f"音区过高: {octave}{pitch}，游戏中可能无法演奏", 
                token
            ))
        
        # 处理特殊的无法映射的音符
        if octave == '+' and pitch in [6, 7]:
            self.warnings.append(ParseError(
                self.current_line, 0,
                f"音符+{pitch}超出游戏音域，参考小键盘{self.numpad_reference.get(pitch, '?')}",
                token
            ))
        
        if octave == '--' and pitch in [1, 2, 3, 4]:
            self.warnings.append(ParseError(
                self.current_line, 0,
                f"音符--{pitch}超出游戏音域，参考小键盘{self.numpad_reference.get(pitch, '?')}",
                token
            ))
        
        return Note(
            pitch=pitch,
            octave=octave,
            accidental=accidental,
            duration=duration,
            modifier=modifier,
            is_rest=is_rest
        )
    
    def _parse_chord(self, token: str) -> Chord:
        """解析和弦"""
        # 检查是否有前置升降号
        chord_accidental = ''
        chord_start = 0
        
        if token.startswith(('#', 'b')):
            chord_accidental = token[0]
            chord_start = 1
        
        # 提取和弦内容和后缀
        bracket_start = token.find('[', chord_start)
        bracket_end = token.rfind(']')
        
        if bracket_start == -1 or bracket_end == -1:
            raise ValueError(f"和弦格式错误: {token}")
        
        chord_content = token[bracket_start + 1:bracket_end]  # 去掉[]
        suffix = token[bracket_end + 1:]  # 时值和修饰符
        
        # 解析后缀
        duration_match = re.search(r'[_.]+', suffix)
        modifier_match = re.search(r'[~*&@]', suffix)
        
        duration = duration_match.group(0) if duration_match else ''
        modifier = modifier_match.group(0) if modifier_match else ''
        
        # 解析和弦中的音符（去除空格）
        chord_content = chord_content.replace(' ', '')
        notes = []
        i = 0
        while i < len(chord_content):
            # 提取单个音符 (音区)(音符) - 升降号统一应用到整个和弦
            note_match = re.match(r'([+\-]*)([1-7])', chord_content[i:])
            if not note_match:
                raise ValueError(f"和弦中音符格式错误: {chord_content[i:]}")
            
            octave, pitch_str = note_match.groups()
            pitch = int(pitch_str)
            
            notes.append(Note(
                pitch=pitch,
                octave=octave,
                accidental=chord_accidental,  # 整个和弦统一升降号
                duration='',  # 和弦中单个音符不单独设置时值
                modifier='',
                is_rest=False
            ))
            
            i += len(note_match.group(0))
        
        if not notes:
            raise ValueError(f"空和弦: {token}")
        
        return Chord(notes=notes, duration=duration, modifier=modifier)
    
    def _parse_triplet(self, token: str) -> Triplet:
        """解析三连音"""
        # 检查是否有前置升降号
        triplet_accidental = ''
        triplet_start = 0
        
        if token.startswith(('#', 'b')):
            triplet_accidental = token[0]
            triplet_start = 1
        
        # 提取三连音内容和后缀
        angle_start = token.find('<', triplet_start)
        angle_end = token.rfind('>')
        
        if angle_start == -1 or angle_end == -1:
            raise ValueError(f"三连音格式错误: {token}")
        
        triplet_content = token[angle_start + 1:angle_end]  # 去掉<>
        suffix = token[angle_end + 1:]  # 时值和修饰符
        
        # 解析后缀
        duration_match = re.search(r'[_.]+', suffix)
        modifier_match = re.search(r'[~*&@]', suffix)
        
        duration = duration_match.group(0) if duration_match else ''
        modifier = modifier_match.group(0) if modifier_match else ''
        
        # 解析三连音中的音符（去除空格）
        triplet_content = triplet_content.replace(' ', '')
        notes = []
        i = 0
        
        # 必须有且只有3个音符（可能是单音符或和弦）
        note_count = 0
        while i < len(triplet_content) and note_count < 3:
            if triplet_content[i] == '[':
                # 当前位置是和弦
                bracket_end = triplet_content.find(']', i)
                if bracket_end == -1:
                    raise ValueError(f"三连音中和弦格式错误: {triplet_content[i:]}")
                
                chord_content = triplet_content[i + 1:bracket_end]  # 和弦内容
                chord_notes = []
                
                # 解析和弦中的音符
                j = 0
                while j < len(chord_content):
                    note_match = re.match(r'([+\-]*)([0-7])', chord_content[j:])
                    if not note_match:
                        raise ValueError(f"三连音和弦中音符格式错误: {chord_content[j:]}")
                    
                    octave, pitch_str = note_match.groups()
                    pitch = int(pitch_str)
                    is_rest = (pitch == 0)
                    
                    chord_notes.append(Note(
                        pitch=pitch,
                        octave=octave,
                        accidental=triplet_accidental,
                        duration='',
                        modifier='',
                        is_rest=is_rest
                    ))
                    
                    j += len(note_match.group(0))
                
                # 创建和弦对象
                chord = Chord(notes=chord_notes, duration='', modifier='')
                notes.append(chord)
                
                i = bracket_end + 1
                note_count += 1
            else:
                # 当前位置是单个音符
                note_match = re.match(r'([+\-]*)([0-7])', triplet_content[i:])
                if not note_match:
                    raise ValueError(f"三连音中音符格式错误: {triplet_content[i:]}")
                
                octave, pitch_str = note_match.groups()
                pitch = int(pitch_str)
                is_rest = (pitch == 0)
                
                notes.append(Note(
                    pitch=pitch,
                    octave=octave,
                    accidental=triplet_accidental,  # 整个三连音统一升降号
                    duration='',  # 三连音中单个音符不单独设置时值
                    modifier='',
                    is_rest=is_rest
                ))
                
                i += len(note_match.group(0))
                note_count += 1
        
        # 检查是否正好有3个音符
        if note_count != 3:
            raise ValueError(f"三连音必须包含正好3个音符，实际: {note_count} ({token})")
        
        # 检查是否还有多余的字符
        if i < len(triplet_content):
            raise ValueError(f"三连音包含多余的字符: {triplet_content[i:]} ({token})")
        
        return Triplet(notes=notes, duration=duration, modifier=modifier, accidental=triplet_accidental)
    
    def _parse_grace_note(self, token: str) -> Grace:
        """解析装饰音"""
        # 检查是否有前置升降号
        grace_accidental = ''
        grace_start = 0
        
        if token.startswith(('#', 'b')):
            grace_accidental = token[0]
            grace_start = 1
        
        # 提取装饰音内容和后缀
        brace_start = token.find('{', grace_start)
        brace_end = token.rfind('}')
        
        if brace_end == -1:
            raise ValueError(f"装饰音格式错误: {token}")
        
        grace_content = token[brace_start + 1:brace_end]  # 去掉{}
        suffix = token[brace_end + 1:]  # 时值和修饰符
        
        # 解析后缀
        duration_match = re.search(r'[_.]+', suffix)
        modifier_match = re.search(r'[~*&@]', suffix)
        
        duration = duration_match.group(0) if duration_match else ''
        modifier = modifier_match.group(0) if modifier_match else ''
        
        # 去除空格后分解为tokens
        grace_content = grace_content.replace(' ', '')
        notes = []
        main_note_data = None
        i = 0
        
        while i < len(grace_content):
            if grace_content[i] == '<':
                # 主音是三连音
                angle_end = grace_content.find('>', i)
                if angle_end == -1:
                    raise ValueError(f"装饰音中三连音格式错误: {grace_content[i:]}")
                
                triplet_token = grace_accidental + grace_content[i:angle_end + 1] + duration + modifier
                main_note_data = self._parse_triplet(triplet_token)
                i = angle_end + 1
                break
            elif grace_content[i] == '[':
                # 主音是和弦
                bracket_end = grace_content.find(']', i)
                if bracket_end == -1:
                    raise ValueError(f"装饰音中和弦格式错误: {grace_content[i:]}")
                
                chord_token = grace_accidental + grace_content[i:bracket_end + 1] + duration + modifier
                main_note_data = self._parse_chord(chord_token)
                i = bracket_end + 1
                break
            else:
                # 单个音符
                note_match = re.match(r'([+\-]*)([1-7])', grace_content[i:])
                if not note_match:
                    raise ValueError(f"装饰音中音符格式错误: {grace_content[i:]}")
                
                octave, pitch_str = note_match.groups()
                pitch = int(pitch_str)
                
                note = Note(
                    pitch=pitch,
                    octave=octave,
                    accidental=grace_accidental,  # 整个装饰音统一升降号
                    duration='',
                    modifier='',
                    is_rest=False
                )
                
                notes.append(note)
                i += len(note_match.group(0))
        
        if not notes and main_note_data is None:
            raise ValueError(f"空装饰音: {token}")
        
        # 最后一个音符是主音（如果没有和弦或三连音的话）
        if main_note_data is None:
            if len(notes) < 1:
                raise ValueError(f"装饰音至少需要一个主音: {token}")
            
            main_note_data = notes[-1]
            main_note_data.duration = duration
            main_note_data.modifier = modifier
            grace_notes = notes[:-1]
        else:
            grace_notes = notes
        
        return Grace(
            grace_notes=grace_notes,
            main_note=main_note_data,
            duration=duration,
            modifier=modifier
        )
    
    def _get_token_duration(self, token: Union[Note, Chord, Grace, Triplet]) -> float:
        """获取token的时值"""
        if isinstance(token, Grace):
            duration_str = token.duration
        elif isinstance(token, Chord):
            duration_str = token.duration
        elif isinstance(token, Triplet):
            duration_str = token.duration
        else:  # Note
            duration_str = token.duration
        
        # 处理复合时值 (如 "_.")
        total_duration = 0.0
        
        if '_' in duration_str:
            underscore_count = duration_str.count('_')
            if underscore_count == 1:
                total_duration += self.duration_values['_']  # 八分音符
            elif underscore_count == 2:
                total_duration += self.duration_values['__']  # 十六分音符
        
        if '.' in duration_str:
            if '_' in duration_str:
                # 带浮点的八分音符 = 八分音符 * 1.5
                total_duration = total_duration * 1.5
            else:
                # 浮点四分音符
                total_duration += self.duration_values['.']
        
        if total_duration == 0.0:
            total_duration = self.duration_values['']  # 默认四分音符
        
        return total_duration
    
    def _count_notes_in_token(self, token: Union[Note, Chord, Grace, Triplet]) -> int:
        """计算token中的音符数量"""
        if isinstance(token, Note):
            return 1
        elif isinstance(token, Chord):
            return len(token.notes)
        elif isinstance(token, Grace):
            count = len(token.grace_notes)
            if isinstance(token.main_note, Chord):
                count += len(token.main_note.notes)
            else:
                count += 1
            return count
        elif isinstance(token, Triplet):
            # 三连音可能包含和弦，需要计算实际音符数
            count = 0
            for note_or_chord in token.notes:
                if isinstance(note_or_chord, Chord):
                    count += len(note_or_chord.notes)
                else:
                    count += 1
            return count
        return 0
    
    def _second_pass_generation(self, lines: List[str]) -> Dict[str, Any]:
        """第二轮：生成播放数据"""
        print("\n🎵 第二轮处理：生成播放数据")
        print("=" * 40)
        
        # 计算每拍的时间（秒）
        beat_duration = 60.0 / self.bpm  # 一拍的秒数
        
        # 解析所有音轨内容
        score_lines = lines[2:]
        track_events = []  # 存储每个音轨的时间事件
        
        for track_idx, line in enumerate(score_lines):
            line = line.strip()
            if not line:
                continue
            
            print(f"🎼 解析音轨{track_idx + 1}")
            track_events.append(self._parse_track_timeline(line, beat_duration, track_idx))
        
        if not track_events:
            raise ValueError("没有找到有效的音轨数据")
        
        # 合并所有音轨的时间轴事件
        print("🔀 合并多声部时间轴")
        merged_events = self._merge_track_events(track_events)
        
        # 生成最终的播放数据
        playback_data, total_key_presses, total_duration = self._generate_final_playback(merged_events)
        
        # 生成输出文件（兼容播放列表格式）
        output_data = {
            "type": "jx3_piano_complete",
            "version": "2.0",
            "filename": "TXT乐谱",
            "transpose": 0,
            "speed_multiplier": 1.0,
            "octave_transpose": 0,
            "metadata": {
                "title": "TXT乐谱转换",
                "bpm": self.bpm,
                "time_signature": self.time_signature,
                "total_measures": self.total_measures,
                "total_notes": self.total_notes,
                "speed_multiplier": 1.0,
                "octave_transpose": 0,
                "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parser_version": "1.0",
                "track_count": len(track_events)
            },
            "playback_data": playback_data
        }
        
        # 输出统计信息
        total_minutes = int(total_duration // 60)
        total_seconds = int(total_duration % 60)
        
        print(f"✅ 解析完成!")
        print(f"🎼 音轨数量: {len(track_events)}")
        print(f"📊 演奏时长: {total_minutes}分{total_seconds}秒 ({total_duration:.1f}秒)")
        print(f"🎹 按键次数: {total_key_presses}")
        print(f"🎵 平均按键频率: {total_key_presses/total_duration:.1f} 按键/秒")
        
        return {
            "success": True,
            "output_data": output_data,
            "statistics": {
                "duration_seconds": total_duration,
                "total_key_presses": total_key_presses,
                "bpm": self.bpm,
                "time_signature": self.time_signature,
                "total_measures": self.total_measures,
                "total_notes": self.total_notes,
                "track_count": len(track_events)
            }
        }
    
    def _parse_track_timeline(self, line: str, beat_duration: float, track_id: int) -> List[TimeEvent]:
        """解析单个音轨的时间轴事件"""
        events = []
        current_time = 0.0
        
        # 分割小节
        if line.startswith('|') and line.endswith('|'):
            line = line[1:-1]
        
        measures = line.split('|')
        
        for measure in measures:
            measure = measure.strip()
            if not measure:
                continue
            
            tokens = self._tokenize_measure(measure)
            
            for token in tokens:
                parsed_token = self._parse_token(token)
                if parsed_token:
                    # 生成这个token的时间事件
                    token_events = self._generate_token_events(parsed_token, current_time, beat_duration, track_id)
                    events.extend(token_events)
                    
                    # 更新时间位置
                    duration = self._get_token_duration(parsed_token)
                    current_time += duration * beat_duration
        
        return events
    
    def _generate_token_events(self, token: Union[Note, Chord, Grace, Triplet], 
                              start_time: float, beat_duration: float, track_id: int) -> List[TimeEvent]:
        """为单个token生成时间事件"""
        events = []
        
        if isinstance(token, Note):
            events.extend(self._generate_note_events(token, start_time, track_id))
            
        elif isinstance(token, Chord):
            events.extend(self._generate_chord_events(token, start_time, track_id))
            
        elif isinstance(token, Grace):
            events.extend(self._generate_grace_events(token, start_time, beat_duration, track_id))
            
        elif isinstance(token, Triplet):
            events.extend(self._generate_triplet_events(token, start_time, beat_duration, track_id))
        
        return events
    
    def _generate_note_events(self, note: Note, start_time: float, track_id: int) -> List[TimeEvent]:
        """生成单音符的时间事件"""
        events = []
        
        if note.is_rest:
            return events
        
        # 升降号处理
        if note.accidental == '#':
            if not self.current_sharp_flat_state['sharp']:
                events.append(TimeEvent(start_time, 'key_press', '+', track_id))
                self.current_sharp_flat_state['sharp'] = True
                self.current_sharp_flat_state['flat'] = False
        elif note.accidental == 'b':
            if not self.current_sharp_flat_state['flat']:
                events.append(TimeEvent(start_time, 'key_press', '-', track_id))
                self.current_sharp_flat_state['flat'] = True
                self.current_sharp_flat_state['sharp'] = False
        elif note.accidental == '':
            # 恢复自然音
            if self.current_sharp_flat_state['sharp']:
                events.append(TimeEvent(start_time, 'key_press', '-', track_id))
            elif self.current_sharp_flat_state['flat']:
                events.append(TimeEvent(start_time, 'key_press', '+', track_id))
            self.current_sharp_flat_state['sharp'] = False
            self.current_sharp_flat_state['flat'] = False
        
        # 修饰符前置
        if note.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time, 'modifier_press', self.modifier_keys[note.modifier], track_id))
        
        # 主音符
        if note.pitch in self.note_to_key:
            events.append(TimeEvent(start_time, 'key_press', self.note_to_key[note.pitch], track_id))
        
        # 修饰符后置
        if note.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time + 0.001, 'modifier_release', self.modifier_keys[note.modifier], track_id))
        
        return events
    
    def _generate_chord_events(self, chord: Chord, start_time: float, track_id: int) -> List[TimeEvent]:
        """生成和弦的时间事件"""
        events = []
        
        # 修饰符前置
        if chord.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time, 'modifier_press', self.modifier_keys[chord.modifier], track_id))
        
        # 同时按下所有音符
        for note in chord.notes:
            note_events = self._generate_note_events(note, start_time, track_id)
            # 只取按键事件，不要修饰符事件（因为和弦统一处理）
            for event in note_events:
                if event.event_type == 'key_press' and event.key in self.note_to_key.values():
                    events.append(event)
        
        # 修饰符后置
        if chord.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time + 0.001, 'modifier_release', self.modifier_keys[chord.modifier], track_id))
        
        return events
    
    def _generate_grace_events(self, grace: Grace, start_time: float, beat_duration: float, track_id: int) -> List[TimeEvent]:
        """生成装饰音的时间事件"""
        events = []
        
        # 修饰符前置
        if grace.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time, 'modifier_press', self.modifier_keys[grace.modifier], track_id))
        
        # 装饰音快速演奏
        grace_time = start_time
        for grace_note in grace.grace_notes:
            note_events = self._generate_note_events(grace_note, grace_time, track_id)
            events.extend(note_events)
            grace_time += 0.05  # 50ms间隔
        
        # 主音
        if isinstance(grace.main_note, Chord):
            main_events = self._generate_chord_events(grace.main_note, grace_time, track_id)
        elif isinstance(grace.main_note, Triplet):
            main_events = self._generate_triplet_events(grace.main_note, grace_time, beat_duration, track_id)
        else:
            main_events = self._generate_note_events(grace.main_note, grace_time, track_id)
        events.extend(main_events)
        
        # 修饰符后置
        if grace.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time + 0.001, 'modifier_release', self.modifier_keys[grace.modifier], track_id))
        
        return events
    
    def _generate_triplet_events(self, triplet: Triplet, start_time: float, beat_duration: float, track_id: int) -> List[TimeEvent]:
        """生成三连音的时间事件"""
        events = []
        
        # 修饰符前置
        if triplet.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time, 'modifier_press', self.modifier_keys[triplet.modifier], track_id))
        
        # 升降号处理
        if triplet.accidental == '#':
            if not self.current_sharp_flat_state['sharp']:
                events.append(TimeEvent(start_time, 'key_press', '+', track_id))
                self.current_sharp_flat_state['sharp'] = True
                self.current_sharp_flat_state['flat'] = False
        elif triplet.accidental == 'b':
            if not self.current_sharp_flat_state['flat']:
                events.append(TimeEvent(start_time, 'key_press', '-', track_id))
                self.current_sharp_flat_state['flat'] = True
                self.current_sharp_flat_state['sharp'] = False
        elif triplet.accidental == '':
            # 恢复自然音
            if self.current_sharp_flat_state['sharp']:
                events.append(TimeEvent(start_time, 'key_press', '-', track_id))
            elif self.current_sharp_flat_state['flat']:
                events.append(TimeEvent(start_time, 'key_press', '+', track_id))
            self.current_sharp_flat_state['sharp'] = False
            self.current_sharp_flat_state['flat'] = False
        
        # 计算三连音时间分配
        duration = self._get_token_duration(triplet)
        total_duration = duration * beat_duration
        total_ms = int(total_duration * 1000)
        
        # 平均分配时间，余数加到最后一个音符
        base_ms = total_ms // 3
        remainder = total_ms % 3
        note_durations = [base_ms, base_ms, base_ms + remainder]
        
        # 按顺序演奏三个音符（可能是单音符或和弦）
        current_triplet_time = start_time
        for i, note_or_chord in enumerate(triplet.notes):
            if isinstance(note_or_chord, Chord):
                # 和弦：同时按下所有音符
                for chord_note in note_or_chord.notes:
                    if not chord_note.is_rest and chord_note.pitch in self.note_to_key:
                        events.append(TimeEvent(current_triplet_time, 'key_press', self.note_to_key[chord_note.pitch], track_id))
            else:
                # 单音符
                if not note_or_chord.is_rest and note_or_chord.pitch in self.note_to_key:
                    events.append(TimeEvent(current_triplet_time, 'key_press', self.note_to_key[note_or_chord.pitch], track_id))
            
            if i < 2:  # 前两个音符需要延迟
                current_triplet_time += note_durations[i] / 1000.0
        
        # 修饰符后置
        if triplet.modifier in self.modifier_keys:
            events.append(TimeEvent(start_time + 0.001, 'modifier_release', self.modifier_keys[triplet.modifier], track_id))
        
        return events
    
    def _merge_track_events(self, track_events: List[List[TimeEvent]]) -> List[TimeEvent]:
        """合并所有音轨的时间事件"""
        all_events = []
        
        # 合并所有音轨的事件
        for track_event_list in track_events:
            all_events.extend(track_event_list)
        
        # 按时间排序
        all_events.sort(key=lambda event: (event.time, event.event_type == 'modifier_press'))
        
        return all_events
    
    def _generate_final_playback(self, events: List[TimeEvent]) -> Tuple[List[Union[str, float]], int, float]:
        """生成最终的播放数据"""
        playback_data = []
        total_key_presses = 0
        last_time = 0.0
        
        # 按时间分组事件
        current_time_events = []
        current_time = 0.0
        
        for event in events:
            if abs(event.time - current_time) > 0.001:  # 时间差超过1ms认为是不同时间点
                # 处理当前时间点的所有事件
                if current_time_events:
                    self._add_time_events_to_playback(current_time_events, playback_data)
                    total_key_presses += len([e for e in current_time_events 
                                            if e.event_type == 'key_press' and e.key in self.note_to_key.values()])
                    
                    # 添加到下一个时间点的延迟
                    if event.time > current_time:
                        delay = event.time - current_time
                        if delay > 0:
                            playback_data.append(round(delay, 3))
                
                current_time_events = [event]
                current_time = event.time
            else:
                current_time_events.append(event)
        
        # 处理最后的事件
        if current_time_events:
            self._add_time_events_to_playback(current_time_events, playback_data)
            total_key_presses += len([e for e in current_time_events 
                                    if e.event_type == 'key_press' and e.key in self.note_to_key.values()])
        
        total_duration = events[-1].time if events else 0.0
        
        return playback_data, total_key_presses, total_duration
    
    def _add_time_events_to_playback(self, events: List[TimeEvent], playback_data: List[Union[str, float]]):
        """将同一时间点的事件添加到播放数据"""
        # 按优先级排序：modifier_press -> key_press -> modifier_release -> key_release
        priority_order = {'modifier_press': 0, 'key_press': 1, 'modifier_release': 2, 'key_release': 3}
        events.sort(key=lambda e: (priority_order.get(e.event_type, 4), e.key))
        
        # 去重（同样的按键只按一次）
        seen_keys = set()
        for event in events:
            if event.event_type == 'key_press' and event.key not in seen_keys:
                playback_data.append(event.key)
                seen_keys.add(event.key)
            elif event.event_type == 'modifier_press' and event.key not in seen_keys:
                playback_data.append(event.key)
                seen_keys.add(event.key)
            elif event.event_type == 'modifier_release':
                playback_data.append(f"release_{event.key}")
            # key_release 通常不需要，音符按下后自动释放
    
    def _generate_keys(self, token: Union[Note, Chord, Grace, Triplet]) -> Tuple[List[str], int]:
        """生成按键序列"""
        keys = []
        key_count = 0
        
        if isinstance(token, Note):
            key_seq, count = self._generate_note_keys(token)
            keys.extend(key_seq)
            key_count += count
            
        elif isinstance(token, Chord):
            key_seq, count = self._generate_chord_keys(token)
            keys.extend(key_seq)
            key_count += count
            
        elif isinstance(token, Grace):
            key_seq, count = self._generate_grace_keys(token)
            keys.extend(key_seq)
            key_count += count
            

        
        return keys, key_count
    
    def _generate_note_keys(self, note: Note) -> Tuple[List[str], int]:
        """生成单音符按键"""
        if note.is_rest:
            return [], 0
        
        keys = []
        
        # 升降号处理
        if note.accidental == '#':
            if not self.current_sharp_flat_state['sharp']:
                keys.append('+')
                self.current_sharp_flat_state['sharp'] = True
                self.current_sharp_flat_state['flat'] = False
        elif note.accidental == 'b':
            if not self.current_sharp_flat_state['flat']:
                keys.append('-')
                self.current_sharp_flat_state['flat'] = True
                self.current_sharp_flat_state['sharp'] = False
        elif note.accidental == '':
            # 恢复自然音
            if self.current_sharp_flat_state['sharp']:
                keys.append('-')
            elif self.current_sharp_flat_state['flat']:
                keys.append('+')
            self.current_sharp_flat_state['sharp'] = False
            self.current_sharp_flat_state['flat'] = False
        
        # 修饰符前置按键
        if note.modifier in self.modifier_keys:
            keys.append(self.modifier_keys[note.modifier])
        
        # 主音符按键
        if note.pitch in self.note_to_key:
            keys.append(self.note_to_key[note.pitch])
        
        # 修饰符后置处理（立即松开修饰键）
        if note.modifier in self.modifier_keys:
            keys.append(f"release_{self.modifier_keys[note.modifier]}")
        
        return keys, len([k for k in keys if not k.startswith('release_')])
    
    def _generate_chord_keys(self, chord: Chord) -> Tuple[List[str], int]:
        """生成和弦按键"""
        keys = []
        
        # 修饰符前置按键
        if chord.modifier in self.modifier_keys:
            keys.append(self.modifier_keys[chord.modifier])
        
        # 同时按下所有音符
        for note in chord.notes:
            note_keys, _ = self._generate_note_keys(note)
            # 只取音符按键，不要修饰符
            for key in note_keys:
                if key in self.note_to_key.values():
                    keys.append(key)
        
        # 修饰符后置处理
        if chord.modifier in self.modifier_keys:
            keys.append(f"release_{self.modifier_keys[chord.modifier]}")
        
        return keys, len(chord.notes)
    
    def _generate_grace_keys(self, grace: Grace) -> Tuple[List[str], int]:
        """生成装饰音按键"""
        keys = []
        total_count = 0
        
        # 修饰符前置按键
        if grace.modifier in self.modifier_keys:
            keys.append(self.modifier_keys[grace.modifier])
        
        # 先演奏装饰音
        for grace_note in grace.grace_notes:
            note_keys, count = self._generate_note_keys(grace_note)
            keys.extend(note_keys)
            total_count += count
            
            # 装饰音之间的短暂延迟
            keys.append(0.05)  # 50ms延迟
        
        # 再演奏主音
        if isinstance(grace.main_note, Chord):
            main_keys, count = self._generate_chord_keys(grace.main_note)
        else:
            main_keys, count = self._generate_note_keys(grace.main_note)
        
        keys.extend(main_keys)
        total_count += count
        
        # 修饰符后置处理
        if grace.modifier in self.modifier_keys:
            keys.append(f"release_{self.modifier_keys[grace.modifier]}")
        
        return keys, total_count
    
    def _generate_triplet_keys(self, triplet: Triplet, beat_duration: float) -> Tuple[List[str], int]:
        """生成三连音按键"""
        keys = []
        total_count = 0
        
        # 修饰符前置按键
        if triplet.modifier in self.modifier_keys:
            keys.append(self.modifier_keys[triplet.modifier])
        
        # 升降号处理
        if triplet.accidental == '#':
            if not self.current_sharp_flat_state['sharp']:
                keys.append('+')
                self.current_sharp_flat_state['sharp'] = True
                self.current_sharp_flat_state['flat'] = False
        elif triplet.accidental == 'b':
            if not self.current_sharp_flat_state['flat']:
                keys.append('-')
                self.current_sharp_flat_state['flat'] = True
                self.current_sharp_flat_state['sharp'] = False
        elif triplet.accidental == '':
            # 恢复自然音
            if self.current_sharp_flat_state['sharp']:
                keys.append('-')
            elif self.current_sharp_flat_state['flat']:
                keys.append('+')
            self.current_sharp_flat_state['sharp'] = False
            self.current_sharp_flat_state['flat'] = False
        
        # 获取三连音总时值
        duration = self._get_token_duration(triplet)
        total_duration = duration * beat_duration  # 三连音总时长（秒）
        
        # 将总时长分配给3个音符，保证毫秒级精度
        total_ms = int(total_duration * 1000)  # 转换为毫秒
        
        # 平均分配时间，余数加到最后一个音符
        base_ms = total_ms // 3
        remainder = total_ms % 3
        
        note_durations = [base_ms, base_ms, base_ms + remainder]  # 毫秒
        
        # 按顺序演奏三个音符
        for i, note in enumerate(triplet.notes):
            if not note.is_rest:
                # 生成音符按键（但不包括升降号，因为已经统一处理）
                if note.pitch in self.note_to_key:
                    keys.append(self.note_to_key[note.pitch])
                    total_count += 1
            
            # 如果不是最后一个音符，添加对应的延迟
            if i < 2:  # 前两个音符需要延迟
                delay_seconds = note_durations[i] / 1000.0
                if delay_seconds > 0:
                    keys.append(round(delay_seconds, 3))
        
        # 修饰符后置处理
        if triplet.modifier in self.modifier_keys:
            keys.append(f"release_{self.modifier_keys[triplet.modifier]}")
        
        return keys, total_count
    
    def _create_error_result(self) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "success": False,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_summary": f"发现{len(self.errors)}个错误",
            "detailed_errors": [
                f"第{error.line}行位置{error.position}: {error.message} ('{error.context}')"
                for error in self.errors
            ]
        }
    
    def save_to_json(self, output_data: Dict[str, Any], output_path: str) -> bool:
        """保存为JSON文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存文件失败: {str(e)}")
            return False


def test_parser():
    """测试解析器"""
    # 创建测试文件，包含多声部和复杂三连音
    test_content = """120
4/4
|1_ 0_ 1_ 0_ 1_ 0_ 1_ 0_|1_ 0_ 1_ 0_ 1_ 0_ 1_ 0_|
|0_ 1_ 0_ 1_ 0_ 1_ 0_ 1_|0_ 1_ 0_ 1_ 0_ 1_ 0_ 1_|
|<1[23]4> 0 0 0|{12<[13][24][35]>} 0 0 0|
|[135] 0 0 0|#<123> b<456> 0 0|"""
    
    parser = TxtScoreParser()
    result = parser.parse_content(test_content)
    
    if result["success"]:
        print("🎉 测试成功!")
        if "statistics" in result:
            stats = result["statistics"]
            print(f"演奏时长: {stats['duration_seconds']:.1f}秒")
            print(f"按键次数: {stats['total_key_presses']}")
        
        # 保存测试结果
        if "output_data" in result:
            parser.save_to_json(result["output_data"], "test_output.json")
            print("📁 测试文件已保存为 test_output.json")
    else:
        print("❌ 测试失败:")
        for error in result.get("detailed_errors", []):
            print(f"   {error}")


if __name__ == "__main__":
    test_parser()
