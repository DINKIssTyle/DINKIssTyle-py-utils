#pqr cat "Video"
# pip install PySide6 Pillow numpy

import sys
import os
import shutil
import subprocess
import re
import glob
import uuid
import json
from PIL import Image

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                               QComboBox, QSpinBox, QCheckBox, QProgressBar, 
                               QFrame, QMessageBox, QTextEdit, QScrollArea, QLineEdit, QGridLayout)
from PySide6.QtCore import Qt, QThread, Signal

# =============================================================================
# 1. 핵심 유틸리티 (로직 유지)
# =============================================================================

def get_file_pattern_and_firstnum(selected_file):
    dir_name = os.path.dirname(selected_file)
    base_name = os.path.basename(selected_file)
    match = re.search(r'^(.*?)(\d+)(\.[^.]+)$', base_name)
    if not match: return None
    prefix, digits, extension = match.group(1), match.group(2), match.group(3)
    num_len = len(digits)
    pattern_regex = re.compile(r'^' + re.escape(prefix) + r'(\d{' + str(num_len) + r'})' + re.escape(extension) + r'$')
    seq_files = []
    if os.path.isdir(dir_name):
        for f in sorted(os.listdir(dir_name)):
            if pattern_regex.match(f): seq_files.append(os.path.join(dir_name, f))
    return seq_files

def extract_frames(input_path, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", "format=rgba", "-vsync", "0", os.path.join(output_dir, "frame_%06d.png")]
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    return sorted(glob.glob(os.path.join(output_dir, "*.png")))

def analyze_crop_area(file_list):
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    found_content = False
    for f_path in file_list:
        with Image.open(f_path) as img:
            if img.mode != 'RGBA': img = img.convert('RGBA')
            bbox = img.getchannel('A').getbbox()
            if bbox:
                found_content = True
                min_x, min_y, max_x, max_y = min(min_x, bbox[0]), min(min_y, bbox[1]), max(max_x, bbox[2]), max(max_y, bbox[3])
    return (min_x, min_y, max_x, max_y) if found_content else None

def is_frame_empty(f_path):
    with Image.open(f_path) as img:
        if img.mode != 'RGBA': img = img.convert('RGBA')
        return img.getchannel('A').getextrema()[1] == 0

def get_media_info(path):
    if not os.path.exists(path): return ""
    
    seq = get_file_pattern_and_firstnum(path)
    if seq and len(seq) > 1:
        try:
            with Image.open(seq[0]) as img:
                w, h = img.size
            return f"[Image Sequence] {w}x{h} | {len(seq)} Frames"
        except: return "Unknown Sequence"

    ext = os.path.splitext(path)[1].lower()
    if ext in ['.webp', '.gif', '.png', '.jpg', '.jpeg', '.tiff', '.exr']:
        try:
            with Image.open(path) as img:
                w, h = img.size
                frames = getattr(img, 'n_frames', 1)
                type_str = "Animation" if frames > 1 else "Image"
                return f"[{type_str}] {w}x{h} | {frames} Frames"
        except: pass

    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-select_streams", "v:0", path]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        data = json.loads(result.stdout)
        if data.get('streams'):
            v = data['streams'][0]
            return f"[Video] {v.get('codec_name','?')} | {v.get('width','?')}x{v.get('height','?')}"
    except: pass
    return "Unknown Media"

# =============================================================================
# 2. 작업 스레드
# =============================================================================
class ConversionWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.is_cancelled = False

    def cancel(self): self.is_cancelled = True
    def log(self, msg): self.log_signal.emit(msg)

    def run(self):
        temp_dir = None
        try:
            p = self.params
            self.log(f"▶ Processing: {os.path.basename(p['input_path'])}")
            
            temp_dir = os.path.join(os.path.dirname(p['output_path']), f".temp_{uuid.uuid4().hex}")
            os.makedirs(temp_dir, exist_ok=True)
            
            frames = []
            seq = get_file_pattern_and_firstnum(p['input_path'])
            if seq and len(seq) > 1: frames = seq
            else: frames = extract_frames(p['input_path'], temp_dir)
            
            if not frames: raise ValueError("No frames found.")
            if self.is_cancelled: raise InterruptedError("Cancelled")

            if p['trim_empty']:
                s, e = 0, len(frames) - 1
                while s <= e and is_frame_empty(frames[s]): s += 1
                while e >= s and is_frame_empty(frames[e]): e -= 1
                frames = frames[s : e + 1]
                if not frames: raise ValueError("Frames are all empty.")

            if self.is_cancelled: raise InterruptedError("Cancelled")
            crop_box = analyze_crop_area(frames) if p['auto_crop'] else None
            
            proc_dir = os.path.join(temp_dir, "processed")
            os.makedirs(proc_dir, exist_ok=True)
            
            pil_cache = []
            final_durs = []
            target_fps = p['fps']
            base_duration_ms = int(1000.0 / target_fps)
            step = p['speed'] / 100.0 
            
            current_idx = 0.0
            total_src_frames = len(frames)
            processed_count = 0

            while current_idx < total_src_frames:
                if self.is_cancelled: raise InterruptedError("Cancelled")
                idx = int(current_idx)
                f_path = frames[idx]
                with Image.open(f_path) as img:
                    img = img.convert("RGBA")
                    if crop_box: img = img.crop(crop_box)
                    
                    if p['margin'] > 0:
                        bg = Image.new("RGBA", (img.width + p['margin']*2, img.height + p['margin']*2), (0,0,0,0))
                        bg.paste(img, (p['margin'], p['margin']))
                        img = bg
                    
                    if p['resize_enabled'] and p['resize_value'] > 0:
                        cur_w, cur_h = img.size
                        new_w, new_h = cur_w, cur_h
                        if p['resize_mode'] == 'width':
                            if cur_w != p['resize_value']:
                                ratio = p['resize_value'] / cur_w
                                new_w, new_h = p['resize_value'], int(cur_h * ratio)
                        else:
                            if cur_h != p['resize_value']:
                                ratio = p['resize_value'] / cur_h
                                new_h, new_w = p['resize_value'], int(cur_w * ratio)
                        
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                    
                    if p['format'] in ['animated webp', 'gif']:
                        pil_cache.append(img)
                        final_durs.append(base_duration_ms)
                    else:
                        img.save(os.path.join(proc_dir, f"frame_{processed_count:06d}.png"))
                
                processed_count += 1
                self.progress_signal.emit(int((current_idx / total_src_frames) * 50))
                current_idx += step

            out = p['output_path']
            loop_cnt = 0 if p['infinite_loop'] else p['loop_count']

            if p['format'] == 'animated webp':
                if not out.lower().endswith('.webp'): out += '.webp'
                pil_cache[0].save(out, save_all=True, append_images=pil_cache[1:], duration=final_durs, loop=loop_cnt, quality=p['quality'], format='WEBP', optimize=True, background=(0,0,0,0))
            
            elif p['format'] == 'gif':
                if not out.lower().endswith('.gif'): out += '.gif'
                pil_cache[0].save(out, save_all=True, append_images=pil_cache[1:], duration=final_durs, loop=loop_cnt, optimize=True, disposal=2, transparency=0)
            
            elif p['format'] in ['mov', 'mp4']:
                cmd = ["ffmpeg", "-y", "-f", "image2", "-framerate", str(target_fps), "-i", os.path.join(proc_dir, "frame_%06d.png")]
                if p['format'] == 'mov':
                    if not out.lower().endswith('.mov'): out += '.mov'
                    cmd.extend(["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-q:v", str(int((100-p['quality'])/2))])
                else:
                    if not out.lower().endswith('.mp4'): out += '.mp4'
                    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(int((100-p['quality'])/5 + 18))])
                
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                cmd.append(out)
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

            self.progress_signal.emit(100)
            sz = os.path.getsize(out) / (1024*1024) if os.path.exists(out) else 0
            self.finished_signal.emit(f"Successfully Saved!\n{out}\n({sz:.2f} MB)")

        except InterruptedError:
            self.error_signal.emit("Task Cancelled.")
        except Exception as e:
            self.error_signal.emit(f"Error: {str(e)}")
        finally:
            if temp_dir and os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)

# =============================================================================
# 3. Modern UI Components
# =============================================================================

class ModernCard(QFrame):
    """ 섹션을 구분하는 둥근 모서리의 카드 위젯 (다크 테마) """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("ModernCard")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # 타이틀
        lbl_title = QLabel(title)
        lbl_title.setObjectName("CardTitle")
        self.main_layout.addWidget(lbl_title)

        # 내용
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(12)
        self.main_layout.addLayout(self.content_layout)

class VideoConverterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DINKIssTyle - Clip to Animated Meme v2.0")
        self.resize(600, 1000)
        self.input_path = ""
        self.output_dir = ""
        self.is_processing = False
        
        self.apply_stylesheet()
        self.setup_ui()

    def apply_stylesheet(self):
        # [핵심] 배경색을 #121212로 통일하여 카드(#1E1E1E)와 자연스럽게 어우러지도록 수정
        self.setStyleSheet("""
            /* 메인 윈도우 및 기본 위젯 배경 설정 */
            QMainWindow, QWidget#MainWidget, QScrollArea, QWidget#ScrollContent {
                background-color: #121212;
            }
            
            QWidget { 
                font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif; 
                font-size: 14px; 
                color: #E0E0E0; 
            }
            
            /* 스크롤바 커스텀 (다크) */
            QScrollBar:vertical { border: none; background: #121212; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #333; min-height: 20px; border-radius: 5px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollArea { border: none; }

            /* 카드 스타일 (살짝 밝은 다크 그레이) */
            #ModernCard { 
                background-color: #1E1E1E; 
                border: 1px solid #333333; 
                border-radius: 12px; 
            }
            #CardTitle { 
                color: #BB86FC; /* 포인트 컬러 (연보라) */
                font-size: 16px; 
                font-weight: bold; 
                margin-bottom: 5px;
            }

            /* 입력 필드 */
            QLineEdit { 
                background-color: #2C2C2C; 
                border: 1px solid #444; 
                border-radius: 6px; 
                padding: 10px; 
                color: #FFF; 
            }
            QLineEdit:read-only { color: #888; background-color: #252525; }
            
            /* 콤보박스 & 스핀박스 */
            QComboBox, QSpinBox {
                background-color: #2C2C2C;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 8px;
                min-height: 20px;
                color: #FFF;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2C2C2C;
                color: #FFF;
                selection-background-color: #BB86FC;
                selection-color: #000;
            }
            
            /* 버튼 */
            QPushButton {
                background-color: #333;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 10px 15px;
                font-weight: bold;
                color: #E0E0E0;
            }
            QPushButton:hover { background-color: #444; border-color: #777; }
            
            /* 주요 액션 버튼 (보라색) */
            #PrimaryButton {
                background-color: #BB86FC;
                color: #000;
                border: none;
                font-size: 15px;
            }
            #PrimaryButton:hover { background-color: #A370F7; }
            
            #CancelButton { background-color: #CF6679; color: #000; border: none; }
            
            /* 체크박스 */
            QCheckBox { spacing: 8px; color: #E0E0E0; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #666; background: #2C2C2C; }
            QCheckBox::indicator:checked { background-color: #BB86FC; border-color: #BB86FC; }

            /* 로그창 */
            QTextEdit {
                background-color: #000;
                border: 1px solid #333;
                border-radius: 8px;
                font-family: Consolas, monospace;
                color: #00FF7F;
            }
            
            /* 프로그레스바 */
            QProgressBar {
                border: none;
                background-color: #2C2C2C;
                border-radius: 4px;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #BB86FC;
                border-radius: 4px;
            }
            
            #InfoLabel { color: #03DAC6; font-size: 13px; font-weight: bold; }
        """)

    def setup_ui(self):
        # 메인 위젯에 ObjectName 부여 (CSS 타겟팅용)
        main_widget = QWidget()
        main_widget.setObjectName("MainWidget")
        self.setCentralWidget(main_widget)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        # 스크롤 내부 컨텐츠 위젯
        content_widget = QWidget()
        content_widget.setObjectName("ScrollContent")
        
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ---------------------------------------------------------
        # 1. 파일 섹션
        # ---------------------------------------------------------
        card_file = ModernCard("📂 File Input & Output")
        
        layout_in = QHBoxLayout()
        self.txt_input = QLineEdit(); self.txt_input.setPlaceholderText("Select input file..."); self.txt_input.setReadOnly(True)
        btn_in = QPushButton("Select File"); btn_in.setCursor(Qt.PointingHandCursor); btn_in.clicked.connect(self.select_input)
        layout_in.addWidget(self.txt_input, 1); layout_in.addWidget(btn_in)
        
        layout_out = QHBoxLayout()
        self.txt_output = QLineEdit(); self.txt_output.setPlaceholderText("Select output folder..."); self.txt_output.setReadOnly(True)
        btn_out = QPushButton("Select Folder"); btn_out.setCursor(Qt.PointingHandCursor); btn_out.clicked.connect(self.select_output)
        layout_out.addWidget(self.txt_output, 1); layout_out.addWidget(btn_out)

        self.lbl_info = QLabel("No file selected")
        self.lbl_info.setObjectName("InfoLabel")
        self.lbl_info.setAlignment(Qt.AlignRight)

        card_file.content_layout.addLayout(layout_in)
        card_file.content_layout.addLayout(layout_out)
        card_file.content_layout.addWidget(self.lbl_info)
        main_layout.addWidget(card_file)

        # ---------------------------------------------------------
        # 2. 설정 섹션
        # ---------------------------------------------------------
        card_settings = ModernCard("⚙️ Settings & Format")
        grid = QGridLayout()
        grid.setSpacing(15)

        self.combo_fmt = QComboBox(); self.combo_fmt.addItems(["animated webp", "mov", "mp4", "gif"])
        self.combo_fmt.currentTextChanged.connect(self.update_loop_ui)
        grid.addWidget(QLabel("Output Format"), 0, 0)
        grid.addWidget(self.combo_fmt, 0, 1)

        self.spin_fps = QSpinBox(); self.spin_fps.setRange(1, 144); self.spin_fps.setValue(30)
        grid.addWidget(QLabel("Frame Rate (FPS)"), 0, 2)
        grid.addWidget(self.spin_fps, 0, 3)

        self.spin_speed = QSpinBox(); self.spin_speed.setRange(1, 1000); self.spin_speed.setValue(100); self.spin_speed.setSuffix(" %")
        grid.addWidget(QLabel("Play Speed"), 1, 0)
        grid.addWidget(self.spin_speed, 1, 1)

        self.spin_q = QSpinBox(); self.spin_q.setRange(1, 100); self.spin_q.setValue(90)
        grid.addWidget(QLabel("Quality (1-100)"), 1, 2)
        grid.addWidget(self.spin_q, 1, 3)

        card_settings.content_layout.addLayout(grid)
        main_layout.addWidget(card_settings)

        # ---------------------------------------------------------
        # 3. 변환 옵션
        # ---------------------------------------------------------
        card_transform = ModernCard("🎨 Transform & Edit")
        
        # Resize
        layout_resize = QHBoxLayout()
        self.chk_resize = QCheckBox("Enable Resize") 
        self.combo_res_mode = QComboBox(); self.combo_res_mode.addItems(["Width", "Height"])
        self.spin_val = QSpinBox(); self.spin_val.setRange(1, 7680); self.spin_val.setValue(1080); self.spin_val.setSuffix(" px")
        self.combo_res_mode.setEnabled(False)
        self.spin_val.setEnabled(False)
        self.chk_resize.toggled.connect(self.toggle_resize)

        layout_resize.addWidget(self.chk_resize)
        layout_resize.addStretch()
        layout_resize.addWidget(QLabel("Mode:"))
        layout_resize.addWidget(self.combo_res_mode)
        layout_resize.addWidget(self.spin_val)
        card_transform.content_layout.addLayout(layout_resize)

        # Loop
        layout_loop = QHBoxLayout()
        self.chk_infinite = QCheckBox("Infinite Loop")
        self.chk_infinite.setChecked(True)
        self.spin_loop = QSpinBox(); self.spin_loop.setRange(1, 100); self.spin_loop.setValue(1); self.spin_loop.setPrefix("Repeat: ")
        self.spin_loop.setEnabled(False) 
        self.chk_infinite.toggled.connect(self.toggle_infinite_loop)

        layout_loop.addWidget(self.chk_infinite)
        layout_loop.addStretch()
        layout_loop.addWidget(self.spin_loop)
        card_transform.content_layout.addLayout(layout_loop)

        # Etc
        layout_opts = QHBoxLayout()
        self.chk_crop = QCheckBox("Auto-crop Margins"); self.chk_crop.setChecked(True)
        self.chk_trim = QCheckBox("Trim Empty Frames"); self.chk_trim.setChecked(True)
        layout_opts.addWidget(self.chk_crop)
        layout_opts.addWidget(self.chk_trim)
        card_transform.content_layout.addLayout(layout_opts)
        
        layout_margin = QHBoxLayout()
        lbl_margin = QLabel("Add Margin (Padding):")
        self.spin_margin = QSpinBox(); self.spin_margin.setRange(0, 500); self.spin_margin.setSuffix(" px")
        layout_margin.addWidget(lbl_margin)
        layout_margin.addWidget(self.spin_margin)
        card_transform.content_layout.addLayout(layout_margin)

        main_layout.addWidget(card_transform)

        # ---------------------------------------------------------
        # 4. 실행 및 로그
        # ---------------------------------------------------------
        self.log_view = QTextEdit(); self.log_view.setReadOnly(True); self.log_view.setFixedHeight(120)
        self.pbar = QProgressBar(); self.pbar.setValue(0); self.pbar.setTextVisible(False)
        
        self.btn_run = QPushButton("START CONVERSION")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setFixedHeight(50)
        self.btn_run.clicked.connect(self.start_conversion)

        main_layout.addWidget(self.log_view)
        main_layout.addWidget(self.pbar)
        main_layout.addWidget(self.btn_run)
        main_layout.addStretch()

        scroll.setWidget(content_widget)
        
        # 메인 레이아웃 적용
        final_layout = QVBoxLayout(main_widget)
        final_layout.setContentsMargins(0,0,0,0)
        final_layout.addWidget(scroll)

    # --- UI 로직 ---
    def toggle_resize(self, checked):
        self.combo_res_mode.setEnabled(checked)
        self.spin_val.setEnabled(checked)

    def toggle_infinite_loop(self, checked):
        self.spin_loop.setEnabled(not checked)

    def update_loop_ui(self, txt):
        is_anim = txt in ['animated webp', 'gif']
        self.chk_infinite.setEnabled(is_anim)
        self.spin_loop.setEnabled(is_anim and not self.chk_infinite.isChecked())

    def select_input(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Media (*.png *.jpg *.gif *.mov *.mp4 *.webp);;All (*.*)")
        if f: 
            self.input_path = f
            self.txt_input.setText(os.path.basename(f))
            self.lbl_info.setText(get_media_info(f))
            self.log_msg(f"Selected: {f}")

    def select_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d: 
            self.output_dir = d
            self.txt_output.setText(d)

    def log_msg(self, m):
        self.log_view.append(m)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def start_conversion(self):
        if self.is_processing:
            self.cancel_process()
            return

        if not self.input_path or not self.output_dir:
            QMessageBox.warning(self, "Missing Info", "Please select input file and output folder.")
            return

        bn = os.path.splitext(os.path.basename(self.input_path))[0]
        bn = re.sub(r'\d+$', '', bn).strip('_-') or "output"

        mode_text = self.combo_res_mode.currentText()
        resize_mode = 'width' if mode_text == "Width" else 'height'

        p = {
            'input_path': self.input_path, 
            'output_path': os.path.join(self.output_dir, bn),
            'format': self.combo_fmt.currentText(), 
            'fps': self.spin_fps.value(), 
            'speed': self.spin_speed.value(),
            'resize_enabled': self.chk_resize.isChecked(), 
            'resize_mode': resize_mode, 
            'resize_value': self.spin_val.value(),
            'infinite_loop': self.chk_infinite.isChecked(), 
            'loop_count': self.spin_loop.value(),
            'auto_crop': self.chk_crop.isChecked(), 
            'trim_empty': self.chk_trim.isChecked(), 
            'margin': self.spin_margin.value(), 
            'quality': self.spin_q.value()
        }

        self.set_processing_state(True)
        self.pbar.setValue(0)
        self.log_view.clear()
        
        self.worker = ConversionWorker(p)
        self.worker.log_signal.connect(self.log_msg)
        self.worker.progress_signal.connect(self.pbar.setValue)
        self.worker.finished_signal.connect(self.done)
        self.worker.error_signal.connect(self.err)
        self.worker.start()

    def cancel_process(self):
        if self.worker and self.worker.isRunning():
            self.log_msg("Cancelling...")
            self.btn_run.setEnabled(False)
            self.worker.cancel()

    def set_processing_state(self, processing):
        self.is_processing = processing
        if processing:
            self.btn_run.setText("CANCEL TASK")
            self.btn_run.setObjectName("CancelButton")
        else:
            self.btn_run.setText("START CONVERSION")
            self.btn_run.setObjectName("PrimaryButton")
            self.btn_run.setEnabled(True)
        self.style().unpolish(self.btn_run)
        self.style().polish(self.btn_run)

    def done(self, m):
        self.set_processing_state(False)
        self.pbar.setValue(100)
        QMessageBox.information(self, "Success", m)

    def err(self, m):
        self.set_processing_state(False)
        if "Cancelled" in m: QMessageBox.information(self, "Info", m)
        else: QMessageBox.critical(self, "Error", m)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoConverterApp()
    window.show()
    sys.exit(app.exec())