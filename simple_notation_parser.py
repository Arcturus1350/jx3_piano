#!/usr/bin/env python3
"""
简谱手写输入解析器
支持手写数字简谱转换为剑网三按键序列

作者: 基于jx3_piano项目扩展
"""

import re
import json
from typing import List, Dict, Any
from datetime import datetime


class SimpleNotationParser:
    """简谱解析器"""
    
    def __init__(self):
        # 简谱数字到剑网三按键的映射
        self.note_mapping = {
            # 低音区 (用点在下面表示，这里用L前缀)
            'L5': 'B',  # 倍低音5
            'L6': 'N',  # 倍低音6  
            'L7': 'M',  # 倍低音7
            '1': 'A',   # 低音1
            '2': 'S',   # 低音2
            '3': 'D',   # 低音3
            '4': 'F',   # 低音4
            '5': 'G',   # 低音5
            '6': 'H',   # 低音6
            '7': 'J',   # 低音7
            
            # 中音区 (标准)
            '1.': 'Q',  # 中音1
            '2.': 'W',  # 中音2
            '3.': 'E',  # 中音3
            '4.': 'R',  # 中音4
            '5.': 'T',  # 中音5
            '6.': 'Y',  # 中音6
            '7.': 'U',  # 中音7
            
            # 高音区 (用点在上面表示，这里用H前缀)
            'H1': '1',  # 高音1
            'H2': '2',  # 高音2
            'H3': '3',  # 高音3
            'H4': '4',  # 高音4
            'H5': '5',  # 高音5
        }
        
        # 升降号处理
        self.sharp_flat_mapping = {
            '#': '+',   # 升号
            'b': '-',   # 降号
            '♯': '+',   # 升号符号
            '♭': '-',   # 降号符号
        }
    
    def parse_handwritten_notation(self, notation_text: str) -> Dict[str, Any]:
        """
        解析手写简谱文本
        
        Args:
            notation_text: 手写简谱文本，例如：
                "1 2 3 4 | 5 6 7 1. | 2. 3. 4. 5. |"
                "1# 2 3b 4 | 5 - 6 7 |"  (# 表示升号，b 表示降号，- 表示休止符)
        
        Returns:
            解析结果字典
        """
        try:
            # 清理输入文本
            clean_text = self._clean_notation_text(notation_text)
            
            # 解析小节
            measures = self._parse_measures(clean_text)
            
            # 转换为按键序列
            playback_data = self._convert_to_playback_data(measures)
            
            # 生成统计信息
            stats = self._generate_statistics(playback_data)
            
            return {
                "success": True,
                "original_notation": notation_text,
                "cleaned_notation": clean_text,
                "measures": measures,
                "playback_data": playback_data,
                "statistics": stats,
                "generation_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "original_notation": notation_text
            }
    
    def _clean_notation_text(self, text: str) -> str:
        """清理和规范化输入文本"""
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text.strip())
        # 标准化分隔符
        text = text.replace('|', ' | ')
        text = text.replace('||', ' || ')
        return text
    
    def _parse_measures(self, text: str) -> List[List[str]]:
        """解析小节"""
        measures = []
        current_measure = []
        
        # 按空格分割
        tokens = text.split()
        
        for token in tokens:
            if token == '|':
                # 小节线，保存当前小节
                if current_measure:
                    measures.append(current_measure)
                    current_measure = []
            elif token == '||':
                # 终止线
                if current_measure:
                    measures.append(current_measure)
                break
            elif token == '-' or token == '0':
                # 休止符
                current_measure.append('REST')
            else:
                # 音符
                current_measure.append(token)
        
        # 添加最后一个小节
        if current_measure:
            measures.append(current_measure)
        
        return measures
    
    def _convert_to_playback_data(self, measures: List[List[str]]) -> List:
        """转换为播放数据"""
        playback_data = []
        current_sharp_flat_state = {'sharp': False, 'flat': False}
        
        for measure_idx, measure in enumerate(measures):
            for note_idx, note in enumerate(measure):
                if note == 'REST':
                    # 休止符，添加延迟
                    playback_data.append(0.5)  # 默认半拍休止
                    continue
                
                # 解析音符（处理升降号）
                key_sequence, new_state = self._parse_single_note(note, current_sharp_flat_state)
                current_sharp_flat_state = new_state
                
                # 添加按键序列
                playback_data.extend(key_sequence)
                
                # 添加音符间延迟（除了小节最后一个音符）
                if note_idx < len(measure) - 1:
                    playback_data.append(0.25)  # 四分音符间隔
            
            # 小节间延迟
            if measure_idx < len(measures) - 1:
                playback_data.append(0.1)
        
        return playback_data
    
    def _parse_single_note(self, note: str, current_state: Dict) -> tuple:
        """解析单个音符"""
        key_sequence = []
        new_state = current_state.copy()
        
        # 检查升降号
        has_sharp = '#' in note or '♯' in note
        has_flat = 'b' in note or '♭' in note
        
        # 移除升降号标记，获取纯音符
        clean_note = re.sub(r'[#b♯♭]', '', note)
        
        # 处理升降号状态变化
        if has_sharp and not current_state['sharp']:
            key_sequence.append('+')
            new_state['sharp'] = True
            new_state['flat'] = False
        elif has_flat and not current_state['flat']:
            key_sequence.append('-')
            new_state['flat'] = True
            new_state['sharp'] = False
        elif not has_sharp and not has_flat and (current_state['sharp'] or current_state['flat']):
            # 恢复自然音
            if current_state['sharp']:
                key_sequence.append('-')
            else:
                key_sequence.append('+')
            new_state['sharp'] = False
            new_state['flat'] = False
        
        # 转换音符到按键
        if clean_note in self.note_mapping:
            key_sequence.append(self.note_mapping[clean_note])
        else:
            # 尝试其他格式
            alt_formats = [
                clean_note + '.',  # 尝试中音格式
                'H' + clean_note,  # 尝试高音格式
                'L' + clean_note,  # 尝试低音格式
            ]
            
            mapped = False
            for alt in alt_formats:
                if alt in self.note_mapping:
                    key_sequence.append(self.note_mapping[alt])
                    mapped = True
                    break
            
            if not mapped:
                print(f"警告：无法映射音符 {note}")
        
        return key_sequence, new_state
    
    def _generate_statistics(self, playback_data: List) -> Dict:
        """生成统计信息"""
        key_count = sum(1 for item in playback_data if isinstance(item, str))
        delay_count = sum(1 for item in playback_data if isinstance(item, (int, float)))
        total_duration = sum(item for item in playback_data if isinstance(item, (int, float)))
        
        return {
            "total_operations": len(playback_data),
            "key_count": key_count,
            "delay_count": delay_count,
            "estimated_duration": total_duration
        }
    
    def save_to_json(self, parsed_data: Dict, output_file: str):
        """保存为JSON格式，兼容现有播放器"""
        if not parsed_data.get("success"):
            raise ValueError("解析失败，无法保存")
        
        # 生成兼容格式
        complete_data = {
            "version": "2.0",
            "type": "jx3_piano_complete",
            "filename": f"手写简谱_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "midi_file": None,
            "generation_time": parsed_data["generation_time"],
            "transpose": 0,
            "processed_tracks": ["手写输入"],
            "processed_channels": [],
            "file_info": {
                "音轨数量": 1,
                "时间分辨率": "手写",
                "文件类型": "简谱",
                "总时长": parsed_data["statistics"]["estimated_duration"]
            },
            "playback_data": parsed_data["playback_data"],
            "statistics": {
                "total_tracks": 1,
                "total_duration": parsed_data["statistics"]["estimated_duration"],
                "note_count": parsed_data["statistics"]["key_count"],
                "operation_count": parsed_data["statistics"]["total_operations"],
                "key_count": parsed_data["statistics"]["key_count"],
                "delay_count": parsed_data["statistics"]["delay_count"],
            },
            "original_notation": parsed_data["original_notation"],
            "key_mapping": {
                "description": "简谱数字到剑网三按键映射",
                "notation": "1234567 -> 低音, 1.2.3.4.5.6.7. -> 中音, H1H2H3H4H5 -> 高音",
                "sharp": "# 或 ♯ -> 升半音",
                "flat": "b 或 ♭ -> 降半音",
                "rest": "- 或 0 -> 休止符"
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, ensure_ascii=False, indent=2)
        
        return output_file


# 使用示例
if __name__ == "__main__":
    parser = SimpleNotationParser()
    
    # 测试简谱输入
    test_notation = """
    1 2 3 4 | 5 6 7 1. | 
    2. 3. 4. 5. | 6. 7. 1. - |
    1# 2 3b 4 | 5 - 6 7 ||
    """
    
    print("=== 简谱解析测试 ===")
    result = parser.parse_handwritten_notation(test_notation)
    
    if result["success"]:
        print("✅ 解析成功!")
        print(f"原始简谱: {result['original_notation']}")
        print(f"小节数: {len(result['measures'])}")
        print(f"按键数: {result['statistics']['key_count']}")
        print(f"预计时长: {result['statistics']['estimated_duration']:.2f}秒")
        
        # 保存为JSON文件
        output_file = "test_notation.json"
        parser.save_to_json(result, output_file)
        print(f"已保存到: {output_file}")
        
        print("\n播放数据前10项:")
        print(result['playback_data'][:10])
    else:
        print("❌ 解析失败:", result["error"])
