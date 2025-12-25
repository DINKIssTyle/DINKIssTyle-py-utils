import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel,
    QFileDialog, QVBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt
from PIL import Image


OUTPUTS = {
    128: "icon128.png",
    48:  "icon48.png",
    16:  "icon16.png",
}


class ImageResizer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Icon Resizer (128 / 48 / 16)")
        self.setFixedSize(420, 200)

        self.image_path = None

        layout = QVBoxLayout()

        self.label = QLabel("No image selected")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_select = QPushButton("Select Image")
        btn_select.clicked.connect(self.select_image)

        btn_save = QPushButton("Resize & Save")
        btn_save.clicked.connect(self.resize_and_save)

        layout.addWidget(self.label)
        layout.addWidget(btn_select)
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def select_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self.image_path = path
            self.label.setText(os.path.basename(path))

    def resize_and_save(self):
        if not self.image_path:
            QMessageBox.warning(self, "Warning", "Please select an image first.")
            return

        out_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder"
        )
        if not out_dir:
            return

        try:
            img = Image.open(self.image_path).convert("RGBA")

            for size, filename in OUTPUTS.items():
                resized = img.copy()
                resized.thumbnail((size, size), Image.Resampling.LANCZOS)

                out_path = os.path.join(out_dir, filename)
                resized.save(out_path, format="PNG")

            QMessageBox.information(
                self,
                "Done",
                "Saved files:\nicon128.png\nicon48.png\nicon16.png"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ImageResizer()
    w.show()
    sys.exit(app.exec())
