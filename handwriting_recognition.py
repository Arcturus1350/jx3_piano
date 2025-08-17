#!/usr/bin/env python3
"""
手写音乐识别模块
支持图片和手写输入转换为剑网三按键序列

依赖:
pip install opencv-python pillow pytesseract
"""

import cv2
import numpy as np
from PIL import Image
import pytesseract
import re
from typing import Dict, List, Any
import json
from datetime import datetime


class HandwritingMusicRecognizer:
    """手写音乐识别器"""
    
    def __init__(self):
        # 配置Tesseract路径（需要根据安装位置调整）
        # Windows: pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        self.simple_parser = self._init_simple_parser()
    
    def _init_simple_parser(self):
        """初始化简谱解析器"""
        # 这里可以导入刚才创建的简谱解析器
        try:
            from simple_notation_parser import SimpleNotationParser
            return SimpleNotationParser()
        except ImportError:
            print("警告：简谱解析器未找到，将使用简化版本")
            return None
    
    def recognize_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        从图片识别音乐符号
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            识别结果字典
        """
        try:
            # 1. 预处理图片
            processed_image = self._preprocess_image(image_path)
            
            # 2. OCR识别
            text = self._extract_text_from_image(processed_image)
            
            # 3. 音乐符号识别
            music_data = self._parse_music_notation(text)
            
            return {
                "success": True,
                "source": "image",
                "image_path": image_path,
                "extracted_text": text,
                "music_data": music_data,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "source": "image",
                "image_path": image_path
            }
    
    def _preprocess_image(self, image_path: str) -> np.ndarray:
        """预处理图片以提高OCR识别率"""
        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法读取图片: {image_path}")
        
        # 转换为灰度图
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 去噪
        denoised = cv2.medianBlur(gray, 5)
        
        # 二值化
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 形态学操作，清理图像
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        return cleaned
    
    def _extract_text_from_image(self, image: np.ndarray) -> str:
        """从预处理后的图片中提取文本"""
        # 配置Tesseract参数
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789#b.|-+♯♭ '
        
        # OCR识别
        text = pytesseract.image_to_string(image, config=custom_config)
        
        # 清理文本
        text = text.strip()
        text = re.sub(r'\n+', ' | ', text)  # 换行转换为小节分隔符
        
        return text
    
    def _parse_music_notation(self, text: str) -> Dict[str, Any]:
        """解析音乐记号"""
        if not self.simple_parser:
            # 简化版解析
            return self._basic_parse(text)
        
        # 使用完整解析器
        return self.simple_parser.parse_handwritten_notation(text)
    
    def _basic_parse(self, text: str) -> Dict[str, Any]:
        """基础解析（当简谱解析器不可用时）"""
        # 基本的数字音符识别
        notes = re.findall(r'[1-7][#b♯♭]?[.]?', text)
        
        # 简单映射
        key_mapping = {
            '1': 'A', '2': 'S', '3': 'D', '4': 'F', '5': 'G', '6': 'H', '7': 'J',
            '1.': 'Q', '2.': 'W', '3.': 'E', '4.': 'R', '5.': 'T', '6.': 'Y', '7.': 'U'
        }
        
        playback_data = []
        for note in notes:
            if note in key_mapping:
                playback_data.append(key_mapping[note])
                playback_data.append(0.5)  # 默认延迟
        
        return {
            "success": True,
            "playback_data": playback_data,
            "recognized_notes": notes,
            "method": "basic_parse"
        }


class CameraInput:
    """摄像头实时输入"""
    
    def __init__(self):
        self.recognizer = HandwritingMusicRecognizer()
    
    def start_camera_recognition(self):
        """启动摄像头识别"""
        cap = cv2.VideoCapture(0)
        
        print("按空格键拍照识别，按q键退出")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 显示实时画面
            cv2.imshow('手写音乐识别 - 按空格拍照', frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                # 拍照并识别
                temp_image = "temp_capture.jpg"
                cv2.imwrite(temp_image, frame)
                
                result = self.recognizer.recognize_from_image(temp_image)
                if result["success"]:
                    print("识别成功!")
                    print(f"提取文本: {result['extracted_text']}")
                else:
                    print(f"识别失败: {result['error']}")
            
            elif key == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()


# GUI集成示例
def add_handwriting_support_to_gui():
    """为现有GUI添加手写支持的示例代码"""
    
    code_example = '''
    # 在 gui.py 中添加以下功能
    
    def add_handwriting_button(self):
        """添加手写输入按钮"""
        self.handwriting_btn = QPushButton("✏️ 手写输入")
        self.handwriting_btn.clicked.connect(self.open_handwriting_dialog)
        # 添加到现有布局中
    
    def open_handwriting_dialog(self):
        """打开手写输入对话框"""
        dialog = HandwritingDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            result = dialog.get_result()
            if result["success"]:
                # 保存为JSON文件
                output_file = os.path.join(get_play_code_dir_path(), 
                                         f"handwritten_{int(time.time())}.json")
                
                # 转换为完整数据格式
                complete_data = self.convert_to_complete_format(result)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(complete_data, f, ensure_ascii=False, indent=2)
                
                self.refresh_play_list()
                self.log(f"✅ 手写输入完成: {os.path.basename(output_file)}")
    '''
    
    print("GUI集成示例代码:")
    print(code_example)


if __name__ == "__main__":
    print("=== 手写音乐识别测试 ===")
    
    # 测试1: 图片识别
    recognizer = HandwritingMusicRecognizer()
    
    # 如果有测试图片，可以这样使用：
    # result = recognizer.recognize_from_image("test_notation.jpg")
    # print(result)
    
    # 测试2: 摄像头输入
    print("启动摄像头测试请运行:")
    print("camera = CameraInput()")
    print("camera.start_camera_recognition()")
    
    # 显示GUI集成示例
    add_handwriting_support_to_gui()
