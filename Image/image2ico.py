#pqr cat=Image; mac=; win=; linux=; term=false
import sys
import os
from PIL import Image
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                               QLabel, QFileDialog, QTextEdit, QProgressBar, 
                               QMessageBox, QHBoxLayout, QFrame)
from PySide6.QtCore import QThread, Signal, Qt

# === Configuration Constants ===
SIZES = [16, 32, 48, 64, 128, 192, 256, 512]
OUT_PNG = True
OUT_ICO = True
OUT_ICNS = True

class IconWorker(QThread):
    """
    Background worker thread handling image processing
    """
    log_signal = Signal(str)            # Log message signal
    progress_signal = Signal(int)       # Progress signal
    finished_signal = Signal()          # Finished signal
    error_signal = Signal(str)          # Error signal

    def __init__(self, src_path, out_dir):
        super().__init__()
        self.src_path = src_path
        self.out_dir = out_dir
        self.is_running = True

    def run(self):
        try:
            self.log_signal.emit(f"📂 Loading source: {os.path.basename(self.src_path)}")
            img = Image.open(self.src_path).convert("RGBA")
            
            icon_dir = os.path.join(self.out_dir, "icon")
            os.makedirs(icon_dir, exist_ok=True)
            self.log_signal.emit(f"📁 Creating output folder: {icon_dir}")

            total_steps = 0
            if OUT_PNG: total_steps += len(SIZES)
            if OUT_ICO: total_steps += len(SIZES)
            if OUT_ICNS: total_steps += 1
            
            current_step = 0

            # 1) Generate PNG
            if OUT_PNG:
                self.log_signal.emit("--- Generating PNGs ---")
                for size in SIZES:
                    if not self.is_running: return
                    save_path = os.path.join(icon_dir, f"app_icon_{size}.png")
                    img.resize((size, size), Image.LANCZOS).save(save_path, format="PNG")
                    
                    current_step += 1
                    self.progress_signal.emit(int(current_step / total_steps * 100))
                    self.log_signal.emit(f"  └ Generated: app_icon_{size}.png")

            # 2) Generate ICO
            if OUT_ICO:
                self.log_signal.emit("--- Generating ICOs ---")
                for size in SIZES:
                    if not self.is_running: return
                    save_path = os.path.join(icon_dir, f"app_icon_{size}.ico")
                    img.resize((size, size), Image.LANCZOS).save(save_path, format="ICO")
                    
                    current_step += 1
                    self.progress_signal.emit(int(current_step / total_steps * 100))
                    self.log_signal.emit(f"  └ Generated: app_icon_{size}.ico")

            # 3) Generate ICNS (For Mac)
            if OUT_ICNS:
                self.log_signal.emit("--- Generating ICNS (Combined) ---")
                if not self.is_running: return
                icns_path = os.path.join(icon_dir, "app_icon.icns")
                
                # Pillow's ICNS save accepts a list of tuples in the 'sizes' option
                img.save(icns_path, format="ICNS", sizes=[(s, s) for s in SIZES])
                
                current_step += 1
                self.progress_signal.emit(100)
                self.log_signal.emit(f"  └ Generated: app_icon.icns (Combined File)")

            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        self.is_running = False


class IconMakerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Icon Maker for Mac/Win")
        self.resize(500, 500)
        
        self.src_path = None
        self.out_dir = None
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Description Label
        info_lbl = QLabel("Select an image to automatically generate icons (PNG, ICO, ICNS) in various sizes.")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: gray; margin-bottom: 10px;")
        layout.addWidget(info_lbl)

        # 1. Image Selection
        file_layout = QHBoxLayout()
        self.btn_file = QPushButton("1. Select Image")
        self.btn_file.clicked.connect(self.select_image)
        self.lbl_file = QLabel("Not Selected")
        self.lbl_file.setStyleSheet("color: #d9534f;") # Red hint
        file_layout.addWidget(self.btn_file)
        file_layout.addWidget(self.lbl_file)
        file_layout.setStretch(1, 1)
        layout.addLayout(file_layout)

        # 2. Folder Selection
        dir_layout = QHBoxLayout()
        self.btn_dir = QPushButton("2. Select Output Folder")
        self.btn_dir.clicked.connect(self.select_dir)
        self.lbl_dir = QLabel("Not Selected")
        self.lbl_dir.setStyleSheet("color: #d9534f;")
        dir_layout.addWidget(self.btn_dir)
        dir_layout.addWidget(self.lbl_dir)
        dir_layout.setStretch(1, 1)
        layout.addLayout(dir_layout)

        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # 3. Run Button and Progress Bar
        self.btn_run = QPushButton("Start Generation")
        self.btn_run.setFixedHeight(40)
        self.btn_run.clicked.connect(self.start_generation)
        self.btn_run.setEnabled(False)
        layout.addWidget(self.btn_run)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        # 4. Log View
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        self.setLayout(layout)

    def select_image(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All Files (*.*)"
        )
        if file:
            self.src_path = file
            self.lbl_file.setText(os.path.basename(file))
            self.lbl_file.setStyleSheet("color: #5cb85c; font-weight: bold;") # Green
            self.check_ready()

    def select_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.out_dir = folder
            self.lbl_dir.setText(folder)
            self.lbl_dir.setStyleSheet("color: #5cb85c; font-weight: bold;")
            self.check_ready()

    def check_ready(self):
        if self.src_path and self.out_dir:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Start Generation")

    def start_generation(self):
        self.btn_file.setEnabled(False)
        self.btn_dir.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()

        self.worker = IconWorker(self.src_path, self.out_dir)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.generation_finished)
        self.worker.error_signal.connect(self.generation_error)
        self.worker.start()

    def append_log(self, text):
        self.log_view.append(text)

    def update_progress(self, val):
        self.progress.setValue(val)

    def generation_finished(self):
        self.progress.setValue(100)
        QMessageBox.information(self, "Done", "All icons have been generated successfully!")
        self.reset_ui()

    def generation_error(self, err_msg):
        QMessageBox.critical(self, "Error", f"An error occurred during process:\n{err_msg}")
        self.reset_ui()

    def reset_ui(self):
        self.btn_file.setEnabled(True)
        self.btn_dir.setEnabled(True)
        self.btn_run.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IconMakerApp()
    window.show()
    sys.exit(app.exec())