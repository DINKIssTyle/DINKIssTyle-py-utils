#pqr cat "Video"
import sys
import os
import warnings
import numpy as np
from PIL import Image

# Qt Libraries
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QFileDialog, 
                               QCheckBox, QSpinBox, QTextEdit, QMessageBox, QGroupBox)
from PySide6.QtCore import QThread, Signal, Qt

# Suppress Warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

# Import MoviePy
try:
    from moviepy.editor import AudioFileClip, ImageClip
except ImportError:
    try:
        from moviepy import AudioFileClip, ImageClip
    except:
        pass

# ---------------------------------------------------------
# [Worker Thread] Conversion Logic
# ---------------------------------------------------------
class ConverterThread(QThread):
    log_signal = Signal(str)
    finish_signal = Signal(bool, str)

    def __init__(self, audio_path, image_path, output_path, use_resize, target_height):
        super().__init__()
        self.audio_path = audio_path
        self.image_path = image_path
        self.output_path = output_path
        self.use_resize = use_resize
        self.target_height = target_height

    def run(self):
        try:
            self.log_signal.emit("-" * 40)
            self.log_signal.emit(f"Starting process...")

            # 1. Image Processing
            self.log_signal.emit(f"Loading image: {os.path.basename(self.image_path)}")
            pil_image = Image.open(self.image_path)
            w, h = pil_image.size

            # Resize Logic
            if self.use_resize and self.target_height > 0:
                ratio = self.target_height / float(h)
                new_w = int(w * ratio)
                target_h = self.target_height
                
                # Make dimensions even
                if new_w % 2 != 0: new_w += 1
                if target_h % 2 != 0: target_h += 1
                
                self.log_signal.emit(f"Applying resize: {w}x{h} -> {new_w}x{target_h}")
                pil_image = pil_image.resize((new_w, target_h), Image.Resampling.LANCZOS)
            else:
                # Ensure even dimensions for video codecs
                if w % 2 != 0 or h % 2 != 0:
                    new_w = w + 1 if w % 2 != 0 else w
                    new_h = h + 1 if h % 2 != 0 else h
                    pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    self.log_signal.emit(f"Adjusting for even dimensions: {new_w}x{new_h}")

            img_array = np.array(pil_image)

            # 2. Audio Processing
            self.log_signal.emit(f"Loading audio: {os.path.basename(self.audio_path)}")
            
            audio_clip = AudioFileClip(self.audio_path)
            duration = audio_clip.duration
            self.log_signal.emit(f"Duration: {duration:.2f}s")

            # 3. Video Composition
            video_clip = ImageClip(img_array).set_duration(duration).set_audio(audio_clip)
            video_clip.fps = 24

            # 4. Encoding
            self.log_signal.emit("Encoding (this may take some time)...")
            
            # [Important] Options to prevent audio loss (especially for FLAC)
            video_clip.write_videofile(
                self.output_path,
                codec='libx264',
                audio_codec='aac',      # Standard MP4 audio codec
                audio_bitrate='320k',   # Minimize audio quality loss
                temp_audiofile='temp-audio.m4a', # Render audio first to prevent loss
                remove_temp=True,       # Cleanup temp file
                fps=24,
                verbose=False,
                logger=None 
            )

            self.finish_signal.emit(True, "Conversion Complete!")

        except Exception as e:
            self.finish_signal.emit(False, f"Error occurred: {str(e)}")

# ---------------------------------------------------------
# [Main Window] UI Setup
# ---------------------------------------------------------
class AppWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio to MP4 Converter (FLAC Support)")
        self.resize(600, 650)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 1. Audio Section
        group_audio = QGroupBox("1. Audio File (flac, mp3, wav)")
        layout_audio = QHBoxLayout()
        self.entry_audio = QLineEdit()
        self.entry_audio.setReadOnly(True)
        btn_audio = QPushButton("Browse")
        btn_audio.clicked.connect(self.browse_audio)
        layout_audio.addWidget(self.entry_audio)
        layout_audio.addWidget(btn_audio)
        group_audio.setLayout(layout_audio)
        layout.addWidget(group_audio)

        # 2. Image Section
        group_image = QGroupBox("2. Cover Image")
        layout_image = QHBoxLayout()
        self.entry_image = QLineEdit()
        self.entry_image.setReadOnly(True)
        btn_image = QPushButton("Browse")
        btn_image.clicked.connect(self.browse_image)
        layout_image.addWidget(self.entry_image)
        layout_image.addWidget(btn_image)
        group_image.setLayout(layout_image)
        layout.addWidget(group_image)

        # 3. Resolution Settings
        group_opt = QGroupBox("Resolution Settings")
        layout_opt = QHBoxLayout()
        self.check_resize = QCheckBox("Resize Image")
        self.check_resize.setChecked(True)
        self.check_resize.toggled.connect(self.toggle_spinbox)
        layout_opt.addWidget(self.check_resize)
        layout_opt.addStretch()
        layout_opt.addWidget(QLabel("Height (px):"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 4320)
        self.spin_height.setValue(1080)
        self.spin_height.setSingleStep(10)
        layout_opt.addWidget(self.spin_height)
        group_opt.setLayout(layout_opt)
        layout.addWidget(group_opt)

        # 4. Save Path
        group_save = QGroupBox("3. Output Path")
        layout_save = QHBoxLayout()
        self.entry_save = QLineEdit()
        btn_save = QPushButton("Save As...")
        btn_save.clicked.connect(self.browse_save)
        layout_save.addWidget(self.entry_save)
        layout_save.addWidget(btn_save)
        group_save.setLayout(layout_save)
        layout.addWidget(group_save)

        # 5. Start Button
        self.btn_start = QPushButton("Start MP4 Conversion")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_start.clicked.connect(self.start_conversion)
        layout.addWidget(self.btn_start)

        # 6. Log View
        layout.addWidget(QLabel("Progress Log:"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #f0f0f0; font-family: Consolas;")
        layout.addWidget(self.log_view)

        self.setLayout(layout)

    def browse_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Audio", "", "Audio (*.flac *.mp3 *.wav *.m4a *.aac)")
        if f: self.entry_audio.setText(f)

    def browse_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Image (*.jpg *.jpeg *.png *.bmp)")
        if f: self.entry_image.setText(f)

    def browse_save(self):
        f, _ = QFileDialog.getSaveFileName(self, "Select Save Location", "", "MP4 Video (*.mp4)")
        if f:
            if not f.lower().endswith(".mp4"): f += ".mp4"
            self.entry_save.setText(f)

    def toggle_spinbox(self):
        self.spin_height.setEnabled(self.check_resize.isChecked())

    def log_append(self, msg):
        self.log_view.append(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_conversion(self):
        audio = self.entry_audio.text()
        image = self.entry_image.text()
        output = self.entry_save.text()

        if not audio or not image or not output:
            QMessageBox.warning(self, "Warning", "Please select all files.")
            return

        self.btn_start.setEnabled(False)
        self.btn_start.setText("Converting...")
        
        use_resize = self.check_resize.isChecked()
        height = self.spin_height.value()

        self.worker = ConverterThread(audio, image, output, use_resize, height)
        self.worker.log_signal.connect(self.log_append)
        self.worker.finish_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success, msg):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("Start MP4 Conversion")
        self.log_append(msg)
        if success:
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Error", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AppWindow()
    window.show()
    sys.exit(app.exec())