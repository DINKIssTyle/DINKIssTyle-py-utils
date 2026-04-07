#pqr cat=Image; mac=; win=; linux=; term=false
import sys
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                             QLabel, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
from PIL import Image

class IconConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.input_path = ""
        self.project_path = ""

    def initUI(self):
        self.setWindowTitle('IMG2iCON for Go Wails')
        self.setFixedSize(500, 220)

        layout = QVBoxLayout()

        # Input Image Selection
        self.lbl_input = QLabel('Source Image: Not selected')
        self.lbl_input.setWordWrap(True)
        btn_input = QPushButton('Select Source Image (PNG/JPG)')
        btn_input.clicked.connect(self.select_input_image)

        # Project Folder Selection
        self.lbl_project = QLabel('Wails Project: Not selected')
        self.lbl_project.setWordWrap(True)
        btn_project = QPushButton('Select Wails Project Folder')
        btn_project.clicked.connect(self.select_project_dir)

        # Run Button
        btn_run = QPushButton('Generate & Deploy Icons')
        btn_run.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71; 
                color: white; 
                font-weight: bold; 
                height: 45px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        btn_run.clicked.connect(self.process_icons)

        # Layout Arrangement
        layout.addWidget(btn_input)
        layout.addWidget(self.lbl_input)
        layout.addSpacing(10)
        layout.addWidget(btn_project)
        layout.addWidget(self.lbl_project)
        layout.addStretch()
        layout.addWidget(btn_run)

        self.setLayout(layout)

    def select_input_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Source Image", "", "Image Files (*.png *.jpg *.jpeg)")
        if file:
            self.input_path = file
            self.lbl_input.setText(f'Selected: {os.path.basename(file)}')

    def select_project_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Wails Project Folder")
        if directory:
            self.project_path = directory
            self.lbl_project.setText(f'Path: {directory}')

    def save_image(self, img, rel_path, size, dpi=72, format="PNG"):
        # Convert path to OS specific separators
        clean_rel_path = rel_path.lstrip('/').replace('/', os.sep)
        full_path = os.path.join(self.project_path, clean_rel_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        resized_img = img.resize(size, Image.Resampling.LANCZOS)
        
        if format.upper() == "ICO":
            # standard Windows ICO sizes
            resized_img.save(full_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        elif format.upper() == "ICNS":
            resized_img.save(full_path, format="ICNS")
        else:
            resized_img.save(full_path, format=format, dpi=(dpi, dpi))
        
        return rel_path

    def process_icons(self):
        if not self.input_path or not self.project_path:
            QMessageBox.warning(self, "Error", "Please select both the source image and the project folder.")
            return

        try:
            with Image.open(self.input_path) as img:
                img = img.convert("RGBA")
                results = []

                # Task definitions: (Path, Size, DPI, Format)
                tasks = [
                    ("/build/appicon.png", (1024, 1024), 144, "PNG"),
                    ("/build/darwin/iconfile.icns", (1024, 1024), 144, "ICNS"),
                    ("/build/linux/icon.png", (1024, 1024), 144, "PNG"),
                    ("/build/windows/icon.ico", (256, 256), 144, "ICO"),
                    ("/frontend/src/assets/images/logo.png", (1024, 1024), 144, "PNG"),
                    ("/frontend/public/apple-touch-icon.png", (180, 180), 72, "PNG"),
                    ("/frontend/public/favicon-16.png", (16, 16), 72, "PNG"),
                    ("/frontend/public/favicon-32.png", (32, 32), 72, "PNG"),
                    ("/frontend/public/icon-192.png", (192, 192), 72, "PNG"),
                    ("/frontend/public/icon-512.png", (512, 512), 72, "PNG"),
                ]

                for path, size, dpi, fmt in tasks:
                    p = self.save_image(img, path, size, dpi, fmt)
                    results.append(f"✓ Created: {path}")

                report = "\n".join(results)
                QMessageBox.information(self, "Success", f"All icons have been generated successfully!\n\n{report}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during conversion:\n{str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = IconConverter()
    ex.show()
    sys.exit(app.exec())