#pqr term=false; cat=Image
# qeesung/image2ascii is licensed under the
# MIT License
# A short and simple permissive license with conditions only requiring preservation of copyright and license notices. Licensed works, modifications, and larger works may be distributed under different terms and without source code.
# https://github.com/ajratnam/image-to-ascii/blob/main/LICENSE

import sys
import html
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTextEdit, QFileDialog, 
                             QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox)
from PyQt6.QtGui import QFont
from PIL import Image


@dataclass
class ASCIIResult:
    plain: str
    html: str
    ansi: str


class ASCIIConverter:
    """Go의 로직을 Python(Pillow)으로 포팅한 핵심 변환 엔진"""
    def __init__(self):
        # 어두운 곳(<)에서 밝은 곳(>) 순서의 ASCII 문자 세트
        self.chars = "@%#*+=-:. "

    def _target_size(self, orig_w, orig_h, width=None, height=None, ratio=1.0,
                     fit_screen=False, stretched=False, screen_size=None):
        screen_w, screen_h = screen_size or shutil.get_terminal_size((100, 40))

        if stretched:
            target_w = width or screen_w
            target_h = height or screen_h
        elif fit_screen:
            max_w = width or screen_w
            max_h = height or screen_h
            width_limited_h = max(1, int(orig_h * (max_w / orig_w) * 0.5))
            if width_limited_h <= max_h:
                target_w, target_h = max_w, width_limited_h
            else:
                target_h = max_h
                target_w = max(1, int(orig_w * (target_h / orig_h) / 0.5))
        elif width and height:
            target_w, target_h = width, height
        elif width:
            target_w = width
            target_h = int(orig_h * (width / orig_w) * 0.5)
        elif height:
            target_h = height
            target_w = int(orig_w * (height / orig_h) / 0.5)
        else:
            target_w = int(orig_w * ratio)
            target_h = int(orig_h * ratio * 0.5)

        return max(1, int(target_w)), max(1, int(target_h))

    def convert(self, image_path, width=None, height=None, ratio=1.0,
                fit_screen=False, stretched=False, colored=False, reversed_chars=False,
                screen_size=None):
        try:
            source = Image.open(image_path).convert('RGBA')
            img_gray = source.convert('L')
            img_color = source.convert('RGB')
            orig_w, orig_h = source.size
            chars = self.chars[::-1] if reversed_chars else self.chars
            target_w, target_h = self._target_size(
                orig_w, orig_h, width=width, height=height, ratio=ratio,
                fit_screen=fit_screen, stretched=stretched, screen_size=screen_size
            )

            gray_resized = img_gray.resize((target_w, target_h))
            color_resized = img_color.resize((target_w, target_h))

            plain_lines = []
            html_lines = []
            ansi_lines = []
            gray_pixels = list(gray_resized.getdata())
            color_pixels = list(color_resized.getdata())

            for y in range(target_h):
                plain_line = []
                html_line = []
                ansi_line = []
                for x in range(target_w):
                    idx = y * target_w + x
                    brightness = gray_pixels[idx]
                    char_idx = int((brightness / 255) * (len(chars) - 1))
                    char = chars[char_idx]
                    plain_line.append(char)

                    if colored:
                        r, g, b = color_pixels[idx]
                        escaped = "&nbsp;" if char == " " else html.escape(char)
                        html_line.append(
                            f'<span style="color: rgb({r}, {g}, {b})">{escaped}</span>'
                        )
                        ansi_line.append(f"\033[38;2;{r};{g};{b}m{char}\033[0m")
                    else:
                        html_line.append("&nbsp;" if char == " " else html.escape(char))
                        ansi_line.append(char)

                plain_lines.append("".join(plain_line))
                html_lines.append("".join(html_line))
                ansi_lines.append("".join(ansi_line))

            plain_text = "\n".join(plain_lines)
            html_text = (
                '<pre style="margin:0; white-space:pre; font-family:Courier New, monospace; '
                'font-size:9pt; line-height:1.0; background:#1e1e1e;">'
                + "<br>".join(html_lines)
                + "</pre>"
            )
            ansi_text = "\n".join(ansi_lines) + ("\033[0m" if colored else "")
            return ASCIIResult(plain=plain_text, html=html_text, ansi=ansi_text)
        except Exception as e:
            message = f"Error: {str(e)}"
            return ASCIIResult(plain=message, html=f"<pre>{html.escape(message)}</pre>", ansi=message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.converter = ASCIIConverter()
        self.current_file = None
        self.current_result = ASCIIResult(plain="", html="", ansi="")
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Image2ASCII | GUI by DINKI'ssTyle")
        self.setGeometry(100, 100, 950, 750)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 상단: 파일 선택 + 너비 설정
        top_layout = QHBoxLayout()
        self.btn_open = QPushButton("\U0001F4C1 Open Image")
        self.btn_open.setMinimumWidth(120)
        self.btn_open.clicked.connect(self.open_file)

        self.lbl_width = QLabel("Width:")
        self.spin_width = QSpinBox()
        self.spin_width.setRange(10, 400)
        self.spin_width.setValue(100)
        self.spin_width.setMinimumWidth(80)
        self.spin_width.valueChanged.connect(self.update_ascii)

        top_layout.addWidget(self.btn_open)
        top_layout.addStretch()
        top_layout.addWidget(self.lbl_width)
        top_layout.addWidget(self.spin_width)
        main_layout.addLayout(top_layout)

        # 옵션 그룹 박스
        options_group = QGroupBox("Conversion Options")
        option_layout = QHBoxLayout()

        self.chk_colored = QCheckBox("Colored ASCII")
        self.chk_colored.setChecked(True)
        self.chk_colored.stateChanged.connect(self.update_ascii)

        self.chk_reversed = QCheckBox("Reversed ASCII")
        self.chk_reversed.stateChanged.connect(self.update_ascii)

        self.chk_fit_screen = QCheckBox("Fit Screen")
        self.chk_fit_screen.setChecked(True)
        self.chk_fit_screen.stateChanged.connect(self.on_fit_screen_changed)

        self.chk_stretched = QCheckBox("Stretch to Screen")
        self.chk_stretched.stateChanged.connect(self.on_stretched_changed)

        # 높이 입력
        self.lbl_height = QLabel("Height:")
        self.spin_height = QSpinBox()
        self.spin_height.setRange(-1, 999)
        self.spin_height.setValue(-1)
        self.spin_height.setMinimumWidth(80)
        self.spin_height.valueChanged.connect(self.update_ascii)

        # 비율 슬라이더
        self.lbl_ratio = QLabel("Ratio:")
        self.spin_ratio = QDoubleSpinBox()
        self.spin_ratio.setRange(0.1, 5.0)
        self.spin_ratio.setSingleStep(0.1)
        self.spin_ratio.setValue(1.0)
        self.spin_ratio.setDecimals(1)
        self.spin_ratio.setMinimumWidth(80)
        self.spin_ratio.setSuffix("x")
        self.spin_ratio.valueChanged.connect(self.update_ascii)

        option_layout.addWidget(self.chk_colored)
        option_layout.addWidget(self.chk_reversed)
        option_layout.addWidget(self.chk_fit_screen)
        option_layout.addWidget(self.chk_stretched)
        option_layout.addStretch()
        option_layout.addWidget(self.lbl_height)
        option_layout.addWidget(self.spin_height)
        option_layout.addWidget(self.lbl_ratio)
        option_layout.addWidget(self.spin_ratio)

        options_group.setLayout(option_layout)
        main_layout.addWidget(options_group)

        # 결과 출력창
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setFont(QFont("Courier New", 9))
        self.text_display.setStyleSheet("""
            background-color: #1e1e1e; 
            color: #ffffff;
            border-radius: 5px;
        """)
        main_layout.addWidget(self.text_display)

        # 하단 버튼 영역
        bottom_layout = QHBoxLayout()
        self.btn_copy = QPushButton("\U0001F4CB Copy to clipboard")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        
        self.btn_terminal = QPushButton("\U0001F4AC Print to terminal")
        self.btn_terminal.clicked.connect(self.echo_to_terminal)

        bottom_layout.addWidget(self.btn_copy)
        bottom_layout.addWidget(self.btn_terminal)
        main_layout.addLayout(bottom_layout)

    def open_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Select an image', '', 'Image files (*.jpg *.jpeg *.png *.bmp)')
        if fname:
            self.current_file = fname
            self.update_ascii()

    def on_fit_screen_changed(self):
        if self.chk_fit_screen.isChecked() and self.chk_stretched.isChecked():
            self.chk_stretched.blockSignals(True)
            self.chk_stretched.setChecked(False)
            self.chk_stretched.blockSignals(False)
        self.update_ascii()

    def on_stretched_changed(self):
        if self.chk_stretched.isChecked() and self.chk_fit_screen.isChecked():
            self.chk_fit_screen.blockSignals(True)
            self.chk_fit_screen.setChecked(False)
            self.chk_fit_screen.blockSignals(False)
        self.update_ascii()

    def update_ascii(self):
        if not self.current_file:
            return

        preview_size = self._preview_cell_size()
        width = None if (self.chk_fit_screen.isChecked() or self.chk_stretched.isChecked()) else self.spin_width.value()
        height_val = self.spin_height.value()
        ratio = self.spin_ratio.value()
        fit_screen = self.chk_fit_screen.isChecked()
        stretched = self.chk_stretched.isChecked()

        # -1은 자동 계산
        height = None if height_val == -1 else height_val

        try:
            result = self.converter.convert(
                self.current_file, width=width, height=height,
                ratio=ratio, fit_screen=fit_screen, stretched=stretched,
                colored=self.chk_colored.isChecked(),
                reversed_chars=self.chk_reversed.isChecked(),
                screen_size=preview_size,
            )
            self.current_result = result

            if self.chk_colored.isChecked():
                self.text_display.setHtml(result.html)
            else:
                self.text_display.setPlainText(result.plain)
        except Exception as e:
            self.text_display.setPlainText(f"Error: {str(e)}")

    def _preview_cell_size(self):
        font_metrics = self.text_display.fontMetrics()
        char_width = max(1, font_metrics.horizontalAdvance("M"))
        line_height = max(1, font_metrics.lineSpacing())
        viewport = self.text_display.viewport().size()
        columns = max(10, int(viewport.width() / char_width) - 2)
        rows = max(5, int(viewport.height() / line_height) - 1)
        return columns, rows

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_file and (self.chk_fit_screen.isChecked() or self.chk_stretched.isChecked()):
            self.update_ascii()

    def copy_to_clipboard(self):
        text = self.current_result.ansi if self.chk_colored.isChecked() else self.current_result.plain
        QApplication.clipboard().setText(text)

    def echo_to_terminal(self):
        text = self.current_result.ansi if self.chk_colored.isChecked() else self.current_result.plain
        if not text:
            print("No ASCII output to echo.")
            return

        print(text, flush=True)
        self._open_terminal_output(text)

    def _open_terminal_output(self, text):
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as output_file:
                output_file.write(text)
                output_path = output_file.name

            system = platform.system()
            if system == "Darwin":
                script_fd, script_path = tempfile.mkstemp(suffix=".command", text=True)
                with os.fdopen(script_fd, "w", encoding="utf-8") as script_file:
                    script_file.write(
                        "#!/bin/sh\n"
                        f"cat {shlex_quote(output_path)}\n"
                        "printf '\\n\\nPress Enter to close...'\n"
                        "read _\n"
                        f"rm -f {shlex_quote(output_path)} \"$0\"\n"
                    )
                os.chmod(script_path, 0o755)
                subprocess.Popen(["open", "-a", "Terminal", script_path])
            elif system == "Windows":
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", "type", output_path], shell=True)
            else:
                terminal = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
                if terminal:
                    subprocess.Popen([terminal, "--", "sh", "-c", f"cat {shlex_quote(output_path)}; printf '\\n\\nPress Enter to close...'; read _; rm -f {shlex_quote(output_path)}"])
        except Exception as e:
            print(f"Unable to open terminal window: {e}", flush=True)


def shlex_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
