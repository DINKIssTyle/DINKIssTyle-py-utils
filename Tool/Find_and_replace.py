# -*- coding: utf-8 -*-
import sys, os

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton,
    QFileDialog, QCheckBox, QMessageBox, QHBoxLayout, QLineEdit
)

def replace_in_file(filepath, search_text, replace_text):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        if search_text not in content:
            return False
        content = content.replace(search_text, replace_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error in {filepath}: {e}")
        return False

class BatchReplaceTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Batch String Replacement Tool")
        self.setMinimumWidth(600)

        layout = QVBoxLayout()

        # Extension Input
        layout.addWidget(QLabel("File Extension (e.g. .txt, .py, .js ...)"))
        self.ext_input = QLineEdit(".fac")
        layout.addWidget(self.ext_input)

        # Find Text
        layout.addWidget(QLabel("Find Text"))
        self.find_input = QTextEdit()
        layout.addWidget(self.find_input)

        # Replace Text
        layout.addWidget(QLabel("Replace With"))
        self.replace_input = QTextEdit()
        layout.addWidget(self.replace_input)

        # Folder Selection
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("No folder selected.")
        self.select_button = QPushButton("Select Folder")
        self.select_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.select_button)
        layout.addLayout(folder_layout)

        # Recursive Checkbox
        self.recursive_checkbox = QCheckBox("Include Subfolders")
        self.recursive_checkbox.setChecked(True)
        layout.addWidget(self.recursive_checkbox)

        # Run Button
        self.run_button = QPushButton("Replace All")
        self.run_button.clicked.connect(self.run_replacement)
        layout.addWidget(self.run_button)

        self.setLayout(layout)
        self.folder_path = ""

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_path = folder
            self.folder_label.setText(folder)

    def run_replacement(self):
        ext = self.ext_input.text().strip()
        find = self.find_input.toPlainText()
        replace = self.replace_input.toPlainText()
        recursive = self.recursive_checkbox.isChecked()

        if not self.folder_path or not ext or not find:
            QMessageBox.warning(self, "Input Error", "Required fields are missing.")
            return

        count = 0
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.endswith(ext):
                    fpath = os.path.join(root, fname)
                    if replace_in_file(fpath, find, replace):
                        count += 1
            if not recursive:
                break

        QMessageBox.information(self, "Complete", f"Replaced text in {count} files.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BatchReplaceTool()
    window.show()
    sys.exit(app.exec_())