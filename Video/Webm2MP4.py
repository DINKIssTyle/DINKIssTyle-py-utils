#pqr cat "Video"

import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QTextEdit, 
                               QFileDialog, QMessageBox)
from PySide6.QtCore import QProcess, Slot

class FFmpegConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebM to MP4 Converter")
        self.resize(600, 400)
        
        # UI 초기화
        self.init_ui()
        
        # QProcess 설정 (비동기 실행을 위해 필수)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

    def init_ui(self):
        layout = QVBoxLayout()

        # 1. 파일 선택 영역
        file_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("변환할 .webm 파일을 선택하세요")
        self.path_input.setReadOnly(True)
        
        btn_browse = QPushButton("파일 찾기")
        btn_browse.clicked.connect(self.browse_file)
        
        file_layout.addWidget(self.path_input)
        file_layout.addWidget(btn_browse)
        layout.addLayout(file_layout)

        # 2. 변환 버튼
        self.btn_convert = QPushButton("MP4로 변환 시작")
        self.btn_convert.clicked.connect(self.start_conversion)
        self.btn_convert.setEnabled(False) # 파일 선택 전 비활성화
        layout.addWidget(self.btn_convert)

        # 3. 로그 출력 영역 (FFmpeg 출력 확인용)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    @Slot()
    def browse_file(self):
        # 파일 탐색기 열기
        file_name, _ = QFileDialog.getOpenFileName(
            self, "동영상 파일 선택", "", "WebM Files (*.webm);;All Files (*)"
        )
        
        if file_name:
            self.path_input.setText(file_name)
            self.btn_convert.setEnabled(True)
            self.log_output.append(f"파일 선택됨: {file_name}")

    @Slot()
    def start_conversion(self):
        input_path = self.path_input.text()
        if not os.path.exists(input_path):
            QMessageBox.warning(self, "오류", "파일을 찾을 수 없습니다.")
            return

        # 출력 파일명 생성 (원본이름.mp4)
        output_path = str(Path(input_path).with_suffix('.mp4'))

        # FFmpeg 명령어 구성
        # -y: 출력 파일이 이미 존재할 경우 덮어쓰기
        program = "ffmpeg"
        arguments = [
            "-y", 
            "-i", input_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path
        ]

        self.log_output.append(f"\n>>> 변환 시작: {output_path}")
        self.btn_convert.setEnabled(False) # 중복 실행 방지
        
        # 프로세스 시작
        self.process.start(program, arguments)

    @Slot()
    def handle_stdout(self):
        """표준 출력 처리"""
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf-8")
        self.log_output.append(stdout)

    @Slot()
    def handle_stderr(self):
        """
        FFmpeg는 진행 상황(프레임, 속도 등)을 stderr로 출력합니다.
        이를 캡처해서 보여줍니다.
        """
        data = self.process.readAllStandardError()
        # 일부 인코딩 문제 방지를 위해 에러 처리 무시 또는 replace
        stderr = bytes(data).decode("utf-8", errors='replace')
        
        # 로그창 스크롤을 항상 아래로 유지
        self.log_output.moveCursor(self.log_output.textCursor().End)
        self.log_output.insertPlainText(stderr)

    @Slot()
    def process_finished(self):
        """변환 종료 시 호출"""
        self.btn_convert.setEnabled(True)
        
        if self.process.exitStatus() == QProcess.NormalExit and self.process.exitCode() == 0:
            QMessageBox.information(self, "완료", "변환이 성공적으로 완료되었습니다!")
            self.log_output.append("\n>>> 변환 성공!")
        else:
            QMessageBox.critical(self, "실패", "변환 중 오류가 발생했습니다.")
            self.log_output.append("\n>>> 변환 실패.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 윈도우 스타일 (취향에 따라 변경 가능)
    app.setStyle("Fusion") 
    
    window = FFmpegConverter()
    window.show()
    sys.exit(app.exec())