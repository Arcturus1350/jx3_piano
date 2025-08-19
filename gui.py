import sys
import os
import shutil
import threading
import subprocess
import json
import time
import glob
from datetime import datetime
from typing import Optional
import ctypes

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QListWidget,
    QTextEdit,
    QLabel,
    QFileDialog,
    QMessageBox,
    QFrame,
    QListWidgetItem,
    QProgressBar,
    QStatusBar,
    QToolBar,
    QAction,
    QGroupBox,
    QComboBox,
    QSlider,
    QTabWidget,
)
from PyQt5.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QRect,
)
from PyQt5.QtGui import (
    QFont,
    QIcon,
    QPalette,
    QColor,
    QPixmap,
    QPainter,
    QBrush,
    QLinearGradient,
    QTextCharFormat,
)

# 导入主程序模块
try:
    from build_music import (
        MidiToKeysConverter,
        build_music,
        MID_DIR_PATH,
        PLAY_CODE_DIR,
        get_midi_dir_path,
        get_play_code_dir_path,
    )
    from midi_file_helper import MidiFileHelper
    from txt_score_parser import TxtScoreParser
except ImportError:
    print("错误: 无法导入主程序模块，请确保主程序文件在同一目录下")
    sys.exit(1)


class TxtConversionWorker(QThread):
    """TXT乐谱转换工作线程"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.log_signal.emit(f"🎵 开始解析TXT乐谱: {os.path.basename(self.file_path)}")
            
            parser = TxtScoreParser()
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result = parser.parse_content(content)
            
            if result["success"]:
                # 生成输出文件名
                basename = os.path.splitext(os.path.basename(self.file_path))[0]
                output_path = os.path.join(get_play_code_dir_path(), f"{basename}.json")
                
                # 设置实际文件名
                result["output_data"]["filename"] = basename
                
                # 保存JSON文件
                if parser.save_to_json(result["output_data"], output_path):
                    stats = result.get("statistics", {})
                    self.log_signal.emit(f"✅ 转换成功!")
                    self.log_signal.emit(f"📊 BPM: {stats.get('bpm', 0)}")
                    self.log_signal.emit(f"🎵 节拍: {stats.get('time_signature', '')}")
                    self.log_signal.emit(f"📏 小节数: {stats.get('total_measures', 0)}")
                    self.log_signal.emit(f"🎼 音符数: {stats.get('total_notes', 0)}")
                    self.log_signal.emit(f"⏱️ 演奏时长: {stats.get('duration_seconds', 0):.1f}秒")
                    self.log_signal.emit(f"🎹 按键次数: {stats.get('total_key_presses', 0)}")
                    self.log_signal.emit(f"💾 输出文件: {output_path}")
                    
                    self.finished_signal.emit(True, output_path)
                else:
                    self.log_signal.emit("❌ 保存文件失败")
                    self.finished_signal.emit(False, "")
            else:
                self.log_signal.emit("❌ 解析失败:")
                for error in result.get("detailed_errors", []):
                    self.log_signal.emit(f"   {error}")
                self.finished_signal.emit(False, "")
                
        except Exception as e:
            self.log_signal.emit(f"❌ 转换过程出错: {str(e)}")
            self.finished_signal.emit(False, "")


class BatchConversionWorker(QThread):
    """批量MIDI转换工作线程"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, file_paths, speed_multiplier=1.0, octave_transpose=0):
        super().__init__()
        self.file_paths = file_paths
        self.speed_multiplier = speed_multiplier
        self.octave_transpose = octave_transpose

    def run(self):
        try:
            total_files = len(self.file_paths)
            successful_conversions = 0
            failed_conversions = 0

            self.log_signal.emit(f"🔄 开始批量处理 {total_files} 个MIDI文件...")

            for i, file_path in enumerate(self.file_paths, 1):
                try:
                    filename = os.path.basename(file_path)
                    target_path = os.path.join(get_midi_dir_path(), filename)

                    self.log_signal.emit(f"📁 [{i}/{total_files}] 正在处理: {filename}")

                    # 复制文件（如果目标文件不存在或者源文件更新）
                    if not os.path.exists(target_path) or os.path.getmtime(
                        file_path
                    ) > os.path.getmtime(target_path):
                        try:
                            # 如果目标文件存在，先删除
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            shutil.copy2(file_path, target_path)
                            self.log_signal.emit(
                                f"📋 [{i}/{total_files}] 已复制文件到工作目录"
                            )
                        except Exception as copy_error:
                            self.log_signal.emit(
                                f"⚠️ [{i}/{total_files}] 文件复制失败，尝试直接使用源文件: {str(copy_error)}"
                            )
                            target_path = file_path  # 直接使用源文件路径
                    else:
                        self.log_signal.emit(
                            f"📋 [{i}/{total_files}] 文件已存在，跳过复制"
                        )

                    # 创建转换器实例
                    converter = MidiToKeysConverter(self.log_callback)

                    # 分析文件
                    analysis = converter.analyze_midi_file(target_path)
                    if "error" in analysis:
                        # 显示详细错误信息
                        self.log_signal.emit(
                            f"❌ [{i}/{total_files}] {filename} 分析失败: {analysis['error']}"
                        )
                        
                        # 如果有详细错误，也显示
                        if "detailed_error" in analysis:
                            self.log_signal.emit(f"   🔍 详细错误: {analysis['detailed_error']}")
                        
                        # 显示解决建议
                        if "suggestions" in analysis:
                            self.log_signal.emit("   💡 解决建议:")
                            for suggestion in analysis["suggestions"]:
                                self.log_signal.emit(f"      {suggestion}")
                        
                        # 使用诊断工具提供更详细的报告
                        try:
                            helper = MidiFileHelper()
                            diagnostic = helper.validate_midi_file(target_path)
                            
                            if diagnostic.get("file_info"):
                                self.log_signal.emit("   📋 文件信息:")
                                info = diagnostic["file_info"]
                                if "size" in info:
                                    self.log_signal.emit(f"      文件大小: {info['size']} 字节")
                                if "format" in info:
                                    self.log_signal.emit(f"      MIDI格式: 类型 {info['format']}")
                                if "tracks" in info:
                                    self.log_signal.emit(f"      音轨数量: {info['tracks']}")
                            
                            # 提供替代方案
                            alternatives = helper.suggest_alternatives(target_path)
                            if alternatives:
                                self.log_signal.emit("   🔄 替代方案:")
                                for alt in alternatives[:5]:  # 只显示前5条
                                    if alt.strip():
                                        self.log_signal.emit(f"      {alt}")
                        except Exception as diag_error:
                            self.log_signal.emit(f"   ⚠️ 诊断工具错误: {diag_error}")
                        
                        self.log_signal.emit("")  # 空行分隔
                        failed_conversions += 1
                        continue

                    # 智能变调分析
                    transpose_result = converter.find_best_transpose_smart(target_path, [0, 1])
                    transpose = transpose_result.get("transpose", 0)
                    
                    # 显示变调决策信息
                    self.log_signal.emit(f"🎯 [{i}/{total_files}] 变调分析: {transpose_result.get('reason', '未知原因')}")
                    
                    # 显示音轨覆盖率详情
                    if "details" in transpose_result:
                        details = transpose_result["details"]
                        for track_key, track_info in details.items():
                            track_num = track_info.get("track_num", "?")
                            coverage = track_info.get("coverage_rate", 0)
                            total = track_info.get("total_notes", 0)
                            mapped = track_info.get("mapped_notes", 0)
                            self.log_signal.emit(
                                f"   🎵 音轨{track_num}: {coverage:.1f}% 覆盖率 ({mapped}/{total} 音符)"
                            )
                    
                    if transpose != 0:
                        self.log_signal.emit(f"📐 [{i}/{total_files}] 最终移调: {transpose}半音")
                    else:
                        self.log_signal.emit(f"✅ [{i}/{total_files}] 保持原调")

                    # 选择前2个音轨
                    track_filter = [0, 1]

                    if not track_filter:
                        self.log_signal.emit(
                            f"⚠️ [{i}/{total_files}] {filename} 没有找到合适的音轨"
                        )
                        failed_conversions += 1
                        continue

                    # 生成完整数据文件（新模式）
                    result = converter.generate_complete_data_file(
                        target_path,
                        track_filter=track_filter,
                        transpose=transpose,
                        speed_multiplier=self.speed_multiplier,
                        octave_transpose=self.octave_transpose,
                    )

                    if not result.get("success"):
                        self.log_signal.emit(
                            f"❌ [{i}/{total_files}] {filename} 生成失败: {result.get('error', '未知错误')}"
                        )
                        failed_conversions += 1
                        continue

                    self.log_signal.emit(f"✅ [{i}/{total_files}] {filename} 转换完成")
                    successful_conversions += 1

                    # 添加小延迟避免文件操作冲突
                    time.sleep(0.1)

                except Exception as e:
                    self.log_signal.emit(
                        f"❌ [{i}/{total_files}] {os.path.basename(file_path)} 转换失败: {str(e)}"
                    )
                    failed_conversions += 1
                    continue

            # 汇总结果
            if successful_conversions > 0:
                self.log_signal.emit(
                    f"🎉 批量转换完成! 成功: {successful_conversions}, 失败: {failed_conversions}"
                )
                self.finished_signal.emit(
                    True, f"成功转换 {successful_conversions} 个文件"
                )
            else:
                self.finished_signal.emit(False, "所有文件转换失败")

        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def log_callback(self, message):
        # 这里可以选择是否输出详细的转换日志
        pass


class PlayThread(QThread):
    """使用新播放器模块的播放线程"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)  # True=正常完成, False=被中断

    def __init__(self, json_file_path, speed_multiplier=1.0):
        super().__init__()
        self.json_file_path = json_file_path
        self.speed_multiplier = speed_multiplier
        self.player = None
        self.should_stop = False

    def run(self):
        try:
            # 导入播放器模块
            from player import JX3Player

            # 创建播放器实例，设置日志回调和倍速
            self.player = JX3Player(log_callback=self.log_signal.emit, speed_multiplier=self.speed_multiplier)

            # 开始播放
            success = self.player.play_from_json(self.json_file_path)

            self.finished_signal.emit(success)

        except Exception as e:
            self.log_signal.emit(f"❌ 播放器启动失败: {e}")
            self.finished_signal.emit(False)

    def stop(self):
        """停止播放"""
        self.should_stop = True
        if self.player:
            self.player.stop()

        self.log_signal.emit("🛑 正在停止播放...")

        # 等待线程结束
        if self.isRunning():
            self.wait(3000)  # 等待最多3秒
            if self.isRunning():
                self.terminate()  # 强制终止


class MidiConverterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 剑网三自动演奏工具")
        self.setGeometry(100, 100, 1000, 700)

        # 播放相关变量
        self.play_thread = None
        self.is_playing = False

        # 设置应用样式
        self.setup_style()

        # 创建界面
        self.setup_ui()

        # 初始化
        self.refresh_play_list()
        self.log("🎵 剑网三自动演奏工具已启动")
        self.log("💡 请导入MIDI文件开始使用")

    def setup_style(self):
        """设置应用程序样式"""
        self.setStyleSheet(
            """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2C3E50, stop:1 #34495E);
            }
            
            QWidget {
                background-color: transparent;
                color: #ECF0F1;
                font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial;
                font-size: 14px;
            }
            
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498DB, stop:1 #2980B9);
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 18px;
                min-height: 25px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5DADE2, stop:1 #3498DB);
                transform: translateY(-2px);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2980B9, stop:1 #21618C);
            }
            
            QPushButton#importBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #27AE60, stop:1 #229954);
            }
            
            QPushButton#importBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #58D68D, stop:1 #27AE60);
            }
            
            QPushButton#importTxtBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF9800, stop:1 #F57F17);
            }
            
            QPushButton#importTxtBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFB74D, stop:1 #FF9800);
            }
            
            QPushButton#diagnoseBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2196F3, stop:1 #1976D2);
            }
            
            QPushButton#diagnoseBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #64B5F6, stop:1 #2196F3);
            }
            
            QPushButton#playBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F39C12, stop:1 #E67E22);
                min-width: 50px;
                font-size: 16px;
                font-weight: bold;
            }
            
            QPushButton#playBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F8C471, stop:1 #F39C12);
            }
            
            QPushButton#stopBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E74C3C, stop:1 #C0392B);
            }
            
            QPushButton#stopBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F1948A, stop:1 #E74C3C);
            }
            
            QPushButton#refreshBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8E44AD, stop:1 #7D3C98);
                min-width: 30px;
                max-width: 35px;
                padding: 8px 8px;
                font-size: 12px;
            }
            
            QPushButton#clearBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E74C3C, stop:1 #C0392B);
                font-size: 10px;
                padding: 5px 10px;
                min-height: 15px;
            }
            
            QListWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(52, 73, 94, 0.8), stop:1 rgba(44, 62, 80, 0.8));
                border: 2px solid #34495E;
                border-radius: 10px;
                padding: 5px;
                font-size: 13px;
                selection-background-color: #3498DB;
            }
            
            QListWidget::item {
                background: rgba(52, 152, 219, 0.1);
                border: 1px solid rgba(52, 152, 219, 0.3);
                border-radius: 5px;
                padding: 8px;
                margin: 2px;
            }
            
            QListWidget::item:hover {
                background: rgba(52, 152, 219, 0.3);
                border: 1px solid rgba(52, 152, 219, 0.6);
            }
            
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498DB, stop:1 #2980B9);
                border: 1px solid #2980B9;
            }
            
            QTextEdit {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(44, 62, 80, 0.9), stop:1 rgba(52, 73, 94, 0.9));
                border: 2px solid #34495E;
                border-radius: 10px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
                color: #ECF0F1;
                selection-background-color: #3498DB;
            }
            
            QLabel {
                color: #ECF0F1;
                font-weight: bold;
                font-size: 15px;
            }
            
            QLabel#creditLabel {
                color: #7F8C8D;
                font-size: 9px;
                font-weight: normal;
                font-style: italic;
            }
            
            QGroupBox {
                border: 2px solid #34495E;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #ECF0F1;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498DB, stop:1 #2980B9);
                border-radius: 5px;
                color: white;
            }
            
            QFrame#leftPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(52, 73, 94, 0.7), stop:1 rgba(44, 62, 80, 0.7));
                border: 2px solid #34495E;
                border-radius: 15px;
                margin: 5px;
            }
            
            QFrame#rightPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(44, 62, 80, 0.7), stop:1 rgba(52, 73, 94, 0.7));
                border: 2px solid #34495E;
                border-radius: 15px;
                margin: 5px;
            }
            
            QSplitter::handle {
                background: #34495E;
                width: 3px;
                border-radius: 1px;
            }
            
            QSplitter::handle:hover {
                background: #3498DB;
            }
            
            QComboBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #34495E, stop:1 #2C3E50);
                border: 2px solid #3498DB;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: #ECF0F1;
                min-width: 120px;
            }
            
            QComboBox:hover {
                border: 2px solid #5DADE2;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498DB, stop:1 #34495E);
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border: 2px solid #ECF0F1;
                width: 6px;
                height: 6px;
                border-top: none;
                border-left: none;
                margin-right: 8px;
            }
            
            QComboBox QAbstractItemView {
                background-color: #2C3E50;
                border: 2px solid #3498DB;
                color: #ECF0F1;
                selection-background-color: #3498DB;
            }
            
        """
        )

    def setup_ui(self):
        """设置用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧面板
        left_frame = QFrame()
        left_frame.setObjectName("leftPanel")
        left_frame.setFixedWidth(350)
        splitter.addWidget(left_frame)

        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(15, 15, 15, 15)

        # 控制按钮组
        control_group = QGroupBox("🎛️ 控制面板")
        left_layout.addWidget(control_group)

        control_layout = QVBoxLayout(control_group)
        
        # 播放设置组
        settings_group = QGroupBox("⚙️ 播放设置")
        control_layout.addWidget(settings_group)
        
        settings_layout = QVBoxLayout(settings_group)
        
        # 速度控制
        speed_row = QHBoxLayout()
        speed_label = QLabel("🚀 播放速度:")
        speed_row.addWidget(speed_label)
        
        self.speed_combo = QComboBox()
        self.speed_combo.addItems([
            "1.0x (正常)", 
            "1.25x (1.25倍速)", 
            "1.5x (1.5倍速)", 
            "1.75x (1.75倍速)", 
            "2.0x (2倍速)"
        ])
        self.speed_combo.setCurrentIndex(0)
        speed_row.addWidget(self.speed_combo)
        settings_layout.addLayout(speed_row)
        
        # 八度变调控制
        octave_row = QHBoxLayout()
        octave_label = QLabel("🎼 八度变调:")
        octave_row.addWidget(octave_label)
        
        self.octave_combo = QComboBox()
        self.octave_combo.addItems(["-8度 (低八度)", "0度 (不变调)", "+8度 (高八度)"])
        self.octave_combo.setCurrentIndex(1)  # 默认不变调
        octave_row.addWidget(self.octave_combo)
        settings_layout.addLayout(octave_row)

        # 按钮行1
        btn_row1 = QHBoxLayout()

        self.import_midi_btn = QPushButton("📁 导入MIDI")
        self.import_midi_btn.setObjectName("importBtn")
        self.import_midi_btn.clicked.connect(self.import_midi_file)
        btn_row1.addWidget(self.import_midi_btn)

        self.import_txt_btn = QPushButton("📝 导入TXT乐谱")
        self.import_txt_btn.setObjectName("importTxtBtn")
        self.import_txt_btn.clicked.connect(self.import_txt_file)
        btn_row1.addWidget(self.import_txt_btn)

        self.diagnose_btn = QPushButton("🔍 诊断")
        self.diagnose_btn.setObjectName("diagnoseBtn")
        self.diagnose_btn.setToolTip("诊断MIDI文件问题")
        self.diagnose_btn.clicked.connect(self.diagnose_midi_file)
        btn_row1.addWidget(self.diagnose_btn)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setToolTip("刷新列表")
        self.refresh_btn.clicked.connect(self.refresh_play_list)
        btn_row1.addWidget(self.refresh_btn)

        control_layout.addLayout(btn_row1)

        # 按钮行2
        btn_row2 = QHBoxLayout()

        self.play_btn = QPushButton("▶️ 播放")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.clicked.connect(self.toggle_play)
        btn_row2.addWidget(self.play_btn)

        control_layout.addLayout(btn_row2)

        # 添加作者信息
        credit_label = QLabel("by 66maer")
        credit_label.setObjectName("creditLabel")
        credit_label.setAlignment(Qt.AlignCenter)
        control_layout.addWidget(credit_label)

        # 播放列表组
        list_group = QGroupBox("🎼 播放列表")
        left_layout.addWidget(list_group)

        list_layout = QVBoxLayout(list_group)

        self.play_listbox = QListWidget()
        self.play_listbox.itemSelectionChanged.connect(self.on_select_play_file)
        list_layout.addWidget(self.play_listbox)

        # 右侧面板
        right_frame = QFrame()
        right_frame.setObjectName("rightPanel")
        splitter.addWidget(right_frame)

        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(15, 15, 15, 15)

        # 日志标题和功能按钮
        log_header = QHBoxLayout()

        log_label = QLabel("📋 操作日志")
        log_label.setFont(QFont("Microsoft YaHei UI", 14, QFont.Bold))
        log_header.addWidget(log_label)

        log_header.addStretch()

        self.topmost_btn = QPushButton("📌 置顶")
        self.topmost_btn.setObjectName("clearBtn")
        self.topmost_btn.setCheckable(True)
        self.topmost_btn.clicked.connect(self.toggle_topmost)
        log_header.addWidget(self.topmost_btn)

        self.clear_btn = QPushButton("🗑️ 清空")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self.clear_log)
        log_header.addWidget(self.clear_btn)

        right_layout.addLayout(log_header)

        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text)

        # 设置分割器比例
        splitter.setSizes([350, 650])

    def get_speed_multiplier(self) -> float:
        """获取当前选择的播放速度倍数"""
        speed_map = {0: 1.0, 1: 1.25, 2: 1.5, 3: 1.75, 4: 2.0}
        return speed_map.get(self.speed_combo.currentIndex(), 1.0)
    
    def get_octave_transpose(self) -> int:
        """获取当前选择的八度变调"""
        octave_map = {0: -1, 1: 0, 2: 1}  # -8度, 不变, +8度
        return octave_map.get(self.octave_combo.currentIndex(), 0)

    def log(self, message: str):
        """添加日志信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"

        # 添加到日志框
        self.log_text.append(log_message)

        # 自动滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor)

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.log("📋 日志已清空")

    def toggle_topmost(self):
        """切换窗口置顶状态"""
        if self.topmost_btn.isChecked():
            # 设置窗口置顶
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.topmost_btn.setText("📌 取消置顶")
            self.log("📌 窗口已置顶")
        else:
            # 取消窗口置顶
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
            self.topmost_btn.setText("📌 置顶")
            self.log("📌 窗口已取消置顶")

    def import_midi_file(self):
        """导入MIDI文件（支持多选）"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择MIDI文件", "", "MIDI files (*.mid *.midi);;All files (*.*)"
        )

        if file_paths:
            try:
                # 获取当前设置
                speed_multiplier = self.get_speed_multiplier()
                octave_transpose = self.get_octave_transpose()
                
                self.log(f"📁 准备导入 {len(file_paths)} 个文件...")
                if speed_multiplier != 1.0:
                    self.log(f"⚡ 播放速度: {speed_multiplier}倍")
                if octave_transpose != 0:
                    octave_desc = f"+{octave_transpose}" if octave_transpose > 0 else str(octave_transpose)
                    self.log(f"🎼 八度变调: {octave_desc}度")

                # 开始批量转换
                self.batch_conversion_worker = BatchConversionWorker(
                    file_paths, speed_multiplier, octave_transpose
                )
                self.batch_conversion_worker.log_signal.connect(self.log)
                self.batch_conversion_worker.finished_signal.connect(
                    self.on_batch_conversion_finished
                )
                self.batch_conversion_worker.start()

                # 禁用导入按钮和设置控件
                self.import_midi_btn.setEnabled(False)
                self.import_midi_btn.setText("🔄 批量转换中...")
                self.import_txt_btn.setEnabled(False)
                self.speed_combo.setEnabled(False)
                self.octave_combo.setEnabled(False)

            except Exception as e:
                self.log(f"❌ 导入失败: {str(e)}")
                QMessageBox.critical(self, "错误", f"导入文件失败：{str(e)}")

    def diagnose_midi_file(self):
        """诊断MIDI文件问题"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择要诊断的MIDI文件", "", "MIDI files (*.mid *.midi);;All files (*.*)"
        )

        if file_path:
            self.log("=" * 50)
            self.log("🔍 开始诊断MIDI文件...")
            self.log(f"📁 文件: {os.path.basename(file_path)}")
            self.log("")

            try:
                helper = MidiFileHelper()
                diagnostic_report = helper.create_diagnostic_report(file_path)
                
                # 将报告按行显示在日志中
                for line in diagnostic_report.split('\n'):
                    if line.strip():
                        self.log(line)
                
                self.log("")
                self.log("🔍 诊断完成！")
                
            except Exception as e:
                self.log(f"❌ 诊断过程中发生错误: {str(e)}")
                self.log("💡 建议:")
                self.log("   • 检查文件是否存在")
                self.log("   • 确认文件不在使用中")
                self.log("   • 尝试使用其他MIDI文件测试")

    def import_txt_file(self):
        """导入TXT乐谱文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择TXT乐谱文件", "", "TXT files (*.txt);;All files (*.*)"
        )

        if file_path:
            try:
                self.log(f"📝 准备导入TXT乐谱: {os.path.basename(file_path)}")
                
                # 开始TXT转换
                self.txt_conversion_worker = TxtConversionWorker(file_path)
                self.txt_conversion_worker.log_signal.connect(self.log)
                self.txt_conversion_worker.finished_signal.connect(
                    self.on_txt_conversion_finished
                )
                self.txt_conversion_worker.start()

                # 禁用导入按钮
                self.import_txt_btn.setEnabled(False)
                self.import_txt_btn.setText("🔄 解析中...")
                self.import_midi_btn.setEnabled(False)

            except Exception as e:
                self.log(f"❌ 导入失败: {str(e)}")
                QMessageBox.critical(self, "错误", f"导入TXT文件失败：{str(e)}")
        else:
            self.log("🚫 未选择文件")

    def on_txt_conversion_finished(self, success: bool, output_path: str):
        """TXT转换完成回调"""
        # 重新启用导入按钮
        self.import_txt_btn.setEnabled(True)
        self.import_txt_btn.setText("📝 导入TXT乐谱")
        self.import_midi_btn.setEnabled(True)
        
        if success:
            self.log("🎉 TXT乐谱转换完成!")
            self.refresh_play_list()
        else:
            self.log("❌ TXT乐谱转换失败")
            QMessageBox.warning(self, "转换失败", "TXT乐谱转换失败，请检查文件格式和语法。")
        
        self.log("=" * 50)

    def on_batch_conversion_finished(self, success: bool, result: str):
        """批量转换完成回调"""
        # 恢复导入按钮和设置控件
        self.import_midi_btn.setEnabled(True)
        self.import_midi_btn.setText("📁 导入MIDI")
        self.import_txt_btn.setEnabled(True)
        self.speed_combo.setEnabled(True)
        self.octave_combo.setEnabled(True)

        if success:
            self.refresh_play_list()
            self.log("🎊 批量导入和转换完成!")
        else:
            self.log(f"❌ 批量转换失败: {result}")
            QMessageBox.critical(self, "批量转换失败", f"批量转换失败：{result}")

    def refresh_play_list(self):
        """刷新播放文件列表"""
        self.play_listbox.clear()

        try:
            # 查找JSON文件（新格式）
            json_files = glob.glob(os.path.join(get_play_code_dir_path(), "*.json"))

            valid_files = 0
            for file_path in sorted(json_files):
                filename = os.path.basename(file_path)

                # 尝试加载JSON文件
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 检查是否是我们的完整数据文件
                    if (
                        data.get("type") == "jx3_piano_complete"
                        and data.get("version") == "2.0"
                    ):
                        display_name = f"🎵 {data['filename']}"
                        if data.get("transpose", 0) != 0:
                            display_name += f" (移调{data['transpose']})"

                        item = QListWidgetItem(display_name)
                        item.setData(Qt.UserRole, file_path)
                        self.play_listbox.addItem(item)
                        valid_files += 1
                    else:
                        # 不是我们的格式，跳过
                        continue

                except Exception:
                    # 文件格式不对，跳过
                    continue

            if valid_files > 0:
                self.log(f"🔄 已刷新列表，找到 {valid_files} 个播放文件")
            else:
                self.log("📝 暂无播放文件，请导入MIDI文件")

        except Exception as e:
            self.log(f"❌ 刷新列表失败: {str(e)}")

    def on_select_play_file(self):
        """选择播放文件时的处理"""
        current_item = self.play_listbox.currentItem()
        if not current_item:
            return

        try:
            json_file_path = current_item.data(Qt.UserRole)
            filename = os.path.basename(json_file_path)

            self.log(f"📄 已选择: {filename}")

            # 加载JSON文件
            try:
                with open(json_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.log("=" * 50)
                self.log("📊 文件信息:")
                self.log(f"  🎵 曲目名称: {data['filename']}")
                self.log(f"  🎼 音轨数量: {data['statistics']['total_tracks']}")
                self.log(f"  ⏱️ 总时长: {data['statistics']['total_duration']:.2f}秒")
                self.log(f"  🎵 移调: {data['transpose']}半音")
                
                # 显示新的播放设置
                if 'speed_multiplier' in data and data['speed_multiplier'] != 1.0:
                    self.log(f"  ⚡ 播放速度: {data['speed_multiplier']}倍")
                if 'octave_transpose' in data and data['octave_transpose'] != 0:
                    octave_desc = f"+{data['octave_transpose']}" if data['octave_transpose'] > 0 else str(data['octave_transpose'])
                    self.log(f"  🎼 八度变调: {octave_desc}度")
                
                self.log(f"  🎹 处理音轨: {data['processed_tracks']}")
                self.log(f"  🔢 音符数量: {data['statistics']['note_count']}")
                self.log(f"  ⚙️ 操作数量: {data['statistics']['operation_count']}")
                self.log(f"  🎹 按键数量: {data['statistics']['key_count']}")
                self.log(f"  ⏰ 延迟数量: {data['statistics']['delay_count']}")
                self.log("=" * 50)

            except Exception as e:
                self.log(f"⚠️ 无法读取文件信息: {str(e)}")

        except Exception as e:
            self.log(f"❌ 选择文件时出错: {str(e)}")

    def toggle_play(self):
        """切换播放状态"""
        if self.is_playing:
            self.stop_playing()
        else:
            self.start_playing()

    def start_playing(self):
        """开始播放"""
        current_item = self.play_listbox.currentItem()
        if not current_item:
            QMessageBox.warning(self, "警告", "请先选择一个播放文件")
            return

        try:
            json_file_path = current_item.data(Qt.UserRole)
            filename = os.path.basename(json_file_path)

            # 获取当前倍速设置
            current_speed = self.get_speed_multiplier()
            
            self.log("")
            self.log(f"▶️ 开始播放: {filename}")
            if current_speed != 1.0:
                self.log(f"⚡ 播放倍速: {current_speed}x")

            # 使用新的播放线程，传递倍速参数
            self.play_thread = PlayThread(json_file_path, current_speed)
            self.play_thread.log_signal.connect(self.log)
            self.play_thread.finished_signal.connect(self.on_play_finished)
            self.play_thread.start()

            self.is_playing = True

            # 更新按钮
            self.play_btn.setText("⏹️ 停止(ESC)")
            self.play_btn.setObjectName("stopBtn")
            self.play_btn.setStyleSheet("")  # 重新应用样式

        except Exception as e:
            self.log(f"❌ 播放失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"播放失败：{str(e)}")

    def stop_playing(self):
        """停止播放"""
        self.log("🛑 正在停止播放...")

        # 停止新的播放线程
        if hasattr(self, "play_thread") and self.play_thread:
            try:
                self.play_thread.stop()
                if self.play_thread.isRunning():
                    self.play_thread.wait(3000)  # 等待最多3秒
                self.play_thread = None
            except:
                pass

        self.is_playing = False

        # 更新按钮
        self.play_btn.setText("▶️ 播放")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setStyleSheet("")  # 重新应用样式

        self.log("⏹️ 播放已停止")

    def closeEvent(self, event):
        """程序关闭事件"""
        if self.is_playing:
            self.stop_playing()
        event.accept()

    def on_play_finished(self, success: bool):
        """播放完成后的回调"""
        if self.is_playing:  # 只在确实在播放时才更新状态
            self.is_playing = False
            self.play_thread = None

            # 更新按钮
            self.play_btn.setText("▶️ 播放")
            self.play_btn.setObjectName("playBtn")
            self.play_btn.setStyleSheet("")  # 重新应用样式

            if success:
                self.log("✅ 播放完成")
            else:
                self.log("⏹️ 播放被中断")


def is_admin():
    """检查程序是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """请求以管理员权限重新运行程序"""
    if is_admin():
        return True
    else:
        try:
            # 获取当前脚本路径
            if getattr(sys, "frozen", False):
                # 如果是打包后的exe
                script = sys.executable
                params = " ".join(sys.argv[1:])
            else:
                # 如果是Python脚本
                script = sys.argv[0]
                params = " ".join(sys.argv[1:])

            # 使用ShellExecute以管理员权限运行
            ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
            return False
        except:
            return False


def main():
    """主程序入口"""
    # 检查管理员权限
    if not is_admin():
        # 如果不是管理员权限，请求重新以管理员权限运行
        if run_as_admin():
            return  # 如果已经是管理员权限，继续执行
        else:
            sys.exit(1)  # 重新启动程序或用户拒绝，退出当前实例

    # 检查并创建必要的文件夹
    from build_music import ensure_directories_exist

    ensure_directories_exist()

    app = QApplication(sys.argv)

    # 设置应用程序信息
    app.setApplicationName("剑网三自动演奏工具")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Jx3 Piano")

    # 设置全局字体
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 创建并显示主窗口
    window = MidiConverterGUI()
    window.show()

    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
