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
except ImportError:
    print("错误: 无法导入主程序模块，请确保主程序文件在同一目录下")
    sys.exit(1)


class BatchConversionWorker(QThread):
    """批量MIDI转换工作线程"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

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
                        self.log_signal.emit(
                            f"❌ [{i}/{total_files}] {filename} 分析失败: {analysis['error']}"
                        )
                        failed_conversions += 1
                        continue

                    # 找到最佳移调
                    transpose = converter.find_best_transpose(target_path)

                    # 选择前2个音轨 TODO: 这里可以根据实际需求调整音轨选择逻辑
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

    def __init__(self, json_file_path):
        super().__init__()
        self.json_file_path = json_file_path
        self.player = None
        self.should_stop = False

    def run(self):
        try:
            # 导入播放器模块
            from player import JX3Player

            # 创建播放器实例，设置日志回调
            self.player = JX3Player(log_callback=self.log_signal.emit)

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

        # 按钮行1
        btn_row1 = QHBoxLayout()

        self.import_btn = QPushButton("📁 导入MIDI")
        self.import_btn.setObjectName("importBtn")
        self.import_btn.clicked.connect(self.import_midi_file)
        btn_row1.addWidget(self.import_btn)

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
                self.log(f"📁 准备导入 {len(file_paths)} 个文件...")

                # 开始批量转换
                self.batch_conversion_worker = BatchConversionWorker(file_paths)
                self.batch_conversion_worker.log_signal.connect(self.log)
                self.batch_conversion_worker.finished_signal.connect(
                    self.on_batch_conversion_finished
                )
                self.batch_conversion_worker.start()

                # 禁用导入按钮
                self.import_btn.setEnabled(False)
                self.import_btn.setText("🔄 批量转换中...")

            except Exception as e:
                self.log(f"❌ 导入失败: {str(e)}")
                QMessageBox.critical(self, "错误", f"导入文件失败：{str(e)}")

    def on_batch_conversion_finished(self, success: bool, result: str):
        """批量转换完成回调"""
        # 恢复导入按钮
        self.import_btn.setEnabled(True)
        self.import_btn.setText("📁 导入MIDI")

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

            self.log("")
            self.log(f"▶️ 开始播放: {filename}")

            # 使用新的播放线程
            self.play_thread = PlayThread(json_file_path)
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
