# MIDI文件帮助工具
# 提供MIDI文件验证、诊断和修复建议

import os
import struct
from typing import Dict, List, Optional, Tuple

class MidiFileHelper:
    """MIDI文件帮助工具类"""
    
    def __init__(self):
        self.common_midi_extensions = ['.mid', '.midi', '.kar']
        
    def validate_midi_file(self, file_path: str) -> Dict:
        """
        验证MIDI文件的完整性和格式
        
        Args:
            file_path: MIDI文件路径
            
        Returns:
            Dict: 验证结果，包含错误信息和修复建议
        """
        result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "file_info": {}
        }
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                result["errors"].append("文件不存在")
                return result
            
            # 检查文件扩展名
            _, ext = os.path.splitext(file_path.lower())
            if ext not in self.common_midi_extensions:
                result["warnings"].append(f"文件扩展名 '{ext}' 不是常见的MIDI格式")
            
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            result["file_info"]["size"] = file_size
            
            if file_size == 0:
                result["errors"].append("文件为空")
                result["suggestions"].append("重新下载或获取一个有效的MIDI文件")
                return result
            
            if file_size < 14:  # MIDI文件头部至少需要14字节
                result["errors"].append("文件太小，不能是有效的MIDI文件")
                result["suggestions"].append("检查文件是否完整下载")
                return result
            
            # 读取并验证文件头部
            with open(file_path, 'rb') as f:
                # 检查MIDI头部标识
                header_chunk_type = f.read(4)
                if header_chunk_type != b'MThd':
                    result["errors"].append("缺少MIDI文件头部标识 'MThd'")
                    result["suggestions"].extend([
                        "文件可能不是标准MIDI格式",
                        "尝试用MIDI编辑器重新保存为标准格式",
                        "确认文件确实是MIDI文件而非其他格式"
                    ])
                    return result
                
                # 检查头部长度
                header_length = struct.unpack('>I', f.read(4))[0]
                if header_length != 6:
                    result["warnings"].append(f"MIDI头部长度异常: {header_length} (标准为6)")
                
                # 读取MIDI格式信息
                if header_length >= 6:
                    format_type = struct.unpack('>H', f.read(2))[0]
                    num_tracks = struct.unpack('>H', f.read(2))[0]
                    division = struct.unpack('>H', f.read(2))[0]
                    
                    result["file_info"]["format"] = format_type
                    result["file_info"]["tracks"] = num_tracks
                    result["file_info"]["division"] = division
                    
                    # 验证格式类型
                    if format_type not in [0, 1, 2]:
                        result["errors"].append(f"不支持的MIDI格式类型: {format_type}")
                        result["suggestions"].append("尝试转换为格式0或格式1的MIDI文件")
                    
                    # 验证音轨数量
                    if num_tracks == 0:
                        result["errors"].append("MIDI文件没有音轨")
                    elif num_tracks > 100:
                        result["warnings"].append(f"音轨数量过多: {num_tracks}")
                
                # 快速检查是否包含音轨数据
                track_found = False
                f.seek(14)  # 跳过头部
                while f.tell() < file_size - 4:
                    try:
                        chunk_type = f.read(4)
                        if chunk_type == b'MTrk':
                            track_found = True
                            # 读取音轨长度
                            track_length = struct.unpack('>I', f.read(4))[0]
                            if track_length > file_size:
                                result["errors"].append("音轨长度超出文件大小")
                                break
                            f.seek(track_length, 1)  # 跳过音轨数据
                        elif len(chunk_type) == 4:
                            # 其他chunk，跳过
                            try:
                                chunk_length = struct.unpack('>I', f.read(4))[0]
                                f.seek(chunk_length, 1)
                            except:
                                break
                        else:
                            break
                    except:
                        break
                
                if not track_found:
                    result["errors"].append("未找到有效的音轨数据 (MTrk)")
                    result["suggestions"].append("文件可能损坏或格式不正确")
            
            # 如果没有严重错误，标记为有效
            if not result["errors"]:
                result["is_valid"] = True
            else:
                # 提供通用修复建议
                result["suggestions"].extend([
                    "使用专业MIDI编辑软件（如MuseScore、REAPER）打开并重新保存",
                    "检查原始文件来源，尝试重新下载",
                    "转换为标准MIDI格式（格式0或格式1）"
                ])
                
        except Exception as e:
            result["errors"].append(f"验证过程中发生错误: {str(e)}")
            result["suggestions"].append("文件可能严重损坏，建议重新获取")
        
        return result
    
    def suggest_alternatives(self, file_path: str) -> List[str]:
        """
        为问题文件提供替代方案建议
        
        Args:
            file_path: 原始文件路径
            
        Returns:
            List[str]: 建议列表
        """
        suggestions = []
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        
        suggestions.extend([
            f"🔍 搜索建议:",
            f"   • 在网上搜索 '{name_without_ext} midi' 寻找其他版本",
            f"   • 尝试在 freemidi.org、8notes.com 等网站查找",
            f"   • 查看是否有同名的 .kar 或 .midi 文件",
            "",
            f"🛠️ 修复建议:",
            f"   • 使用 MuseScore 打开原文件并导出为MIDI",
            f"   • 尝试在线MIDI转换工具",
            f"   • 使用 Audacity 或其他音频软件重新生成MIDI",
            "",
            f"🎵 替代方案:",
            f"   • 寻找同一首歌的其他MIDI版本",
            f"   • 考虑使用相似风格的其他MIDI文件",
            f"   • 如果有乐谱，可以用 MuseScore 重新制作MIDI"
        ])
        
        return suggestions
    
    def create_diagnostic_report(self, file_path: str) -> str:
        """
        创建详细的诊断报告
        
        Args:
            file_path: MIDI文件路径
            
        Returns:
            str: 格式化的诊断报告
        """
        validation = self.validate_midi_file(file_path)
        alternatives = self.suggest_alternatives(file_path)
        
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("🔍 MIDI文件诊断报告")
        report_lines.append("=" * 60)
        report_lines.append(f"📁 文件: {os.path.basename(file_path)}")
        
        if validation["file_info"]:
            info = validation["file_info"]
            report_lines.append(f"📊 文件大小: {info.get('size', 0)} 字节")
            if 'format' in info:
                report_lines.append(f"🎼 MIDI格式: 类型 {info['format']}")
            if 'tracks' in info:
                report_lines.append(f"🎵 音轨数量: {info['tracks']}")
            if 'division' in info:
                report_lines.append(f"⏱️ 时间分辨率: {info['division']}")
        
        report_lines.append("")
        
        if validation["is_valid"]:
            report_lines.append("✅ 文件验证: 通过")
            
            # 如果文件有效，添加音轨覆盖率分析
            try:
                from build_music import MidiToKeysConverter
                converter = MidiToKeysConverter()
                
                # 获取变调分析
                transpose_result = converter.find_best_transpose_smart(file_path, [0, 1])
                
                report_lines.append("")
                report_lines.append("🎯 变调分析:")
                report_lines.append(f"   决策: {transpose_result.get('reason', '未知')}")
                report_lines.append(f"   最佳移调: {transpose_result.get('transpose', 0)}半音")
                
                if "details" in transpose_result:
                    report_lines.append("")
                    report_lines.append("🎵 音轨覆盖率分析:")
                    details = transpose_result["details"]
                    
                    for track_key in sorted(details.keys()):
                        track_info = details[track_key]
                        track_num = track_info.get("track_num", "?")
                        coverage = track_info.get("coverage_rate", 0)
                        total = track_info.get("total_notes", 0)
                        mapped = track_info.get("mapped_notes", 0)
                        
                        status = "✅" if coverage >= 80 else "⚠️" if coverage >= 60 else "❌"
                        main_indicator = " (主旋律)" if track_num == 0 else " (副手)"
                        
                        report_lines.append(
                            f"   {status} 音轨{track_num}{main_indicator}: {coverage:.1f}% ({mapped}/{total} 音符)"
                        )
                
                # 添加音轨评估
                report_lines.append("")
                report_lines.append("📋 音轨质量评估:")
                main_coverage = transpose_result.get("main_track_coverage", 0)
                if main_coverage >= 90:
                    report_lines.append("   🌟 主旋律覆盖率优秀，适合演奏")
                elif main_coverage >= 80:
                    report_lines.append("   ✅ 主旋律覆盖率良好，推荐使用")
                elif main_coverage >= 60:
                    report_lines.append("   ⚠️ 主旋律覆盖率一般，部分音符可能无法演奏")
                else:
                    report_lines.append("   ❌ 主旋律覆盖率较低，不推荐使用")
                    
            except Exception as e:
                report_lines.append("")
                report_lines.append(f"⚠️ 音轨分析失败: {str(e)}")
                
        else:
            report_lines.append("❌ 文件验证: 失败")
        
        if validation["errors"]:
            report_lines.append("")
            report_lines.append("🚨 发现的错误:")
            for error in validation["errors"]:
                report_lines.append(f"   • {error}")
        
        if validation["warnings"]:
            report_lines.append("")
            report_lines.append("⚠️ 警告:")
            for warning in validation["warnings"]:
                report_lines.append(f"   • {warning}")
        
        if validation["suggestions"]:
            report_lines.append("")
            report_lines.append("💡 修复建议:")
            for suggestion in validation["suggestions"]:
                report_lines.append(f"   • {suggestion}")
        
        report_lines.append("")
        report_lines.extend(alternatives)
        
        return "\n".join(report_lines)

# 提供快速诊断函数
def diagnose_midi_file(file_path: str) -> str:
    """
    快速诊断MIDI文件并返回报告
    
    Args:
        file_path: MIDI文件路径
        
    Returns:
        str: 诊断报告
    """
    helper = MidiFileHelper()
    return helper.create_diagnostic_report(file_path)

if __name__ == "__main__":
    # 测试代码
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(diagnose_midi_file(file_path))
    else:
        print("用法: python midi_file_helper.py <midi文件路径>")
