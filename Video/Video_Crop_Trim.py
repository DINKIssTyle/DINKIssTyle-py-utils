import sys
import os
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                               QMessageBox, QProgressBar, QScrollArea,
                               QLineEdit)
from PySide6.QtCore import Qt, QThread, Signal, QRect, QPoint, QRectF, QMutex, QWaitCondition
from PySide6.QtGui import (QPixmap, QImage, QPainter, QPen, QColor, 
                           QBrush, QPainterPath, QIntValidator)

from moviepy.editor import VideoFileClip

# ==========================================
# 1. Preview Worker (Background Thread)
# ==========================================
class PreviewWorker(QThread):
    frame_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.clip = None
        self.target_time = None
        self.is_running = True
        self.mutex = QMutex()
        self.condition = QWaitCondition()

    def load_video(self, path):
        if self.clip:
            self.clip.close()
        try:
            self.clip = VideoFileClip(path)
        except Exception as e:
            print(f"Error loading clip: {e}")

    def request_frame(self, t):
        self.mutex.lock()
        self.target_time = t
        self.condition.wakeAll()
        self.mutex.unlock()

    def run(self):
        while self.is_running:
            self.mutex.lock()
            if self.target_time is None:
                self.condition.wait(self.mutex)
            
            t = self.target_time
            self.target_time = None
            self.mutex.unlock()

            if t is not None and self.clip:
                try:
                    frame = self.clip.get_frame(t)
                    self.frame_ready.emit(frame)
                except Exception as e:
                    print(f"Frame error: {e}")
    
    def stop(self):
        self.is_running = False
        self.mutex.lock()
        self.condition.wakeAll()
        self.mutex.unlock()
        self.wait()
        if self.clip:
            self.clip.close()

# ==========================================
# 2. Range Slider (With Playhead)
# ==========================================
class RangeSlider(QWidget):
    # start, end, current, who_moved
    rangeChanged = Signal(float, float, float, str) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.duration = 100.0
        
        # Values
        self.start_val = 0.0
        self.end_val = 100.0
        self.cur_val = 0.0 # Playhead position
        
        # UI Settings
        self.bar_height = 8
        self.handle_size = 18
        self.margin = 20
        
        # Drag States
        self.dragging_start = False
        self.dragging_end = False
        self.dragging_cur = False

    def set_duration(self, duration):
        self.duration = duration
        self.start_val = 0.0
        self.end_val = duration
        self.cur_val = 0.0
        self.update()

    def val_to_pos(self, val):
        available_width = self.width() - 2 * self.margin
        if self.duration <= 0: return self.margin
        ratio = val / self.duration
        return self.margin + int(ratio * available_width)

    def pos_to_val(self, x):
        available_width = self.width() - 2 * self.margin
        if available_width <= 0: return 0
        x = max(self.margin, min(x, self.width() - self.margin))
        ratio = (x - self.margin) / available_width
        return ratio * self.duration

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        track_y = (self.height() - self.bar_height) // 2
        
        # 1. Background Track (Gray)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(60, 60, 60))
        painter.drawRoundedRect(self.margin, track_y, self.width() - 2 * self.margin, self.bar_height, 4, 4)
        
        x_start = self.val_to_pos(self.start_val)
        x_end = self.val_to_pos(self.end_val)
        x_cur = self.val_to_pos(self.cur_val)

        # 2. Selected Range (Blue)
        painter.setBrush(QColor(0, 120, 215))
        if x_end > x_start:
            painter.drawRoundedRect(x_start, track_y, x_end - x_start, self.bar_height, 4, 4)

        # 3. Trim Handles (Circle)
        cy = track_y + self.bar_height // 2
        self.draw_trim_handle(painter, x_start, cy, self.dragging_start)
        self.draw_trim_handle(painter, x_end, cy, self.dragging_end)

        # 4. Playhead (Red Line + Triangle) - Draw on top
        self.draw_play_head(painter, x_cur, track_y, self.dragging_cur)

    def draw_trim_handle(self, painter, x, cy, is_active):
        color = QColor(0, 120, 215) if is_active else QColor(220, 220, 220)
        painter.setBrush(color)
        painter.setPen(QPen(QColor(30, 30, 30), 1))
        r = self.handle_size // 2
        painter.drawEllipse(QPoint(x, cy), r, r)

    def draw_play_head(self, painter, x, track_y, is_active):
        # Vertical Line
        painter.setPen(QPen(QColor(255, 50, 50), 2))
        painter.drawLine(x, 5, x, self.height() - 5)
        
        # Top Handle (Triangle)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 50, 50))
        path = QPainterPath()
        top_y = 5
        size = 8
        path.moveTo(x - size, top_y)
        path.lineTo(x + size, top_y)
        path.lineTo(x, top_y + size * 1.5)
        path.closeSubpath()
        painter.drawPath(path)

    def mousePressEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        
        x_start = self.val_to_pos(self.start_val)
        x_end = self.val_to_pos(self.end_val)
        x_cur = self.val_to_pos(self.cur_val)
        
        cy = (self.height() - self.bar_height) // 2 + self.bar_height // 2
        trim_radius = self.handle_size 
        play_radius = 15 # Playhead detection range
        
        dist_start = abs(x - x_start)
        dist_end = abs(x - x_end)
        dist_cur = abs(x - x_cur)
        
        # Y-axis check
        if abs(y - cy) > 30: return

        caught = False
        
        # Detect Handles
        if dist_start < trim_radius and dist_start <= dist_end and dist_start <= dist_cur:
            self.dragging_start = True
            caught = True
        elif dist_end < trim_radius and dist_end < dist_start and dist_end <= dist_cur:
            self.dragging_end = True
            caught = True
        elif dist_cur < play_radius:
            self.dragging_cur = True
            caught = True
        
        # If nothing caught, move playhead to click position
        if not caught:
            self.cur_val = self.pos_to_val(x)
            self.dragging_cur = True
            self.rangeChanged.emit(self.start_val, self.end_val, self.cur_val, "cur")
            
        self.update()

    def mouseMoveEvent(self, event):
        if not (self.dragging_start or self.dragging_end or self.dragging_cur):
            return

        val = self.pos_to_val(event.pos().x())
        who_moved = ""
        
        if self.dragging_start:
            self.start_val = min(val, self.end_val - 0.1) 
            who_moved = "start"
        elif self.dragging_end:
            self.end_val = max(val, self.start_val + 0.1)
            who_moved = "end"
        elif self.dragging_cur:
            self.cur_val = val
            who_moved = "cur"
        
        self.rangeChanged.emit(self.start_val, self.end_val, self.cur_val, who_moved)
        self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_start = False
        self.dragging_end = False
        self.dragging_cur = False
        self.update()

# ==========================================
# 3. Zoomable Crop Widget
# ==========================================
class ZoomableCropWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #222;")
        
        self.original_pixmap = None
        self.scale_factor = 1.0
        self.crop_rect_img_coord = QRectF() 
        self.is_cropping = False
        self.mode = None 
        self.last_mouse_pos = QPoint()
        self.handle_size = 10

    def set_image(self, frame_image):
        height, width, channel = frame_image.shape
        bytes_per_line = 3 * width
        q_img = QImage(frame_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
        self.original_pixmap = QPixmap.fromImage(q_img)
        
        if not self.is_cropping:
            self.scale_factor = 1.0
            self.crop_rect_img_coord = QRectF(0, 0, width, height)
            self.is_cropping = True
        
        self.update_view()

    def set_zoom(self, zoom_value):
        if self.original_pixmap is None: return
        self.scale_factor = zoom_value
        self.update_view()

    def update_view(self):
        if self.original_pixmap is None: return
        new_w = int(self.original_pixmap.width() * self.scale_factor)
        new_h = int(self.original_pixmap.height() * self.scale_factor)
        self.setFixedSize(new_w, new_h)
        self.setPixmap(self.original_pixmap.scaled(
            new_w, new_h, Qt.KeepAspectRatio, Qt.FastTransformation
        ))
        self.update()

    def map_to_screen(self, rect_f):
        return QRect(
            int(rect_f.x() * self.scale_factor),
            int(rect_f.y() * self.scale_factor),
            int(rect_f.width() * self.scale_factor),
            int(rect_f.height() * self.scale_factor)
        )

    def map_to_image(self, point):
        return QPoint(
            int(point.x() / self.scale_factor),
            int(point.y() / self.scale_factor)
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_cropping and self.original_pixmap:
            painter = QPainter(self)
            screen_rect = self.map_to_screen(self.crop_rect_img_coord)
            
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRect(0, 0, self.width(), self.height())
            path.addRect(screen_rect)
            painter.drawPath(path)

            painter.setBrush(Qt.NoBrush)
            pen = QPen(Qt.white, 1, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(screen_rect)
            
            painter.setBrush(Qt.white)
            painter.setPen(QPen(Qt.black, 1))
            handles = self.get_screen_handles(screen_rect)
            for rect in handles.values():
                painter.drawRect(rect)

    def get_screen_handles(self, screen_rect):
        r = screen_rect
        s = self.handle_size
        return {
            'TL': QRect(r.left(), r.top(), s, s),
            'TR': QRect(r.right() - s, r.top(), s, s),
            'BL': QRect(r.left(), r.bottom() - s, s, s),
            'BR': QRect(r.right() - s, r.bottom() - s, s, s)
        }

    def mousePressEvent(self, event):
        if not self.is_cropping: return
        pos = event.pos()
        screen_rect = self.map_to_screen(self.crop_rect_img_coord)
        handles = self.get_screen_handles(screen_rect)
        if handles['TL'].contains(pos): self.mode = 'TL'
        elif handles['TR'].contains(pos): self.mode = 'TR'
        elif handles['BL'].contains(pos): self.mode = 'BL'
        elif handles['BR'].contains(pos): self.mode = 'BR'
        elif screen_rect.contains(pos): self.mode = 'MOVE'
        else: self.mode = None
        self.last_mouse_pos = self.map_to_image(pos)

    def mouseMoveEvent(self, event):
        if not self.is_cropping: return
        pos = event.pos()
        screen_rect = self.map_to_screen(self.crop_rect_img_coord)
        handles = self.get_screen_handles(screen_rect)
        if handles['TL'].contains(pos) or handles['BR'].contains(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handles['TR'].contains(pos) or handles['BL'].contains(pos):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif screen_rect.contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.mode and event.buttons() & Qt.LeftButton:
            img_pos = self.map_to_image(pos)
            dx = img_pos.x() - self.last_mouse_pos.x()
            dy = img_pos.y() - self.last_mouse_pos.y()
            r = self.crop_rect_img_coord
            if self.mode == 'MOVE': r.translate(dx, dy)
            elif self.mode == 'TL': r.setTopLeft(img_pos)
            elif self.mode == 'TR': r.setTopRight(img_pos)
            elif self.mode == 'BL': r.setBottomLeft(img_pos)
            elif self.mode == 'BR': r.setBottomRight(img_pos)
            self.crop_rect_img_coord = r.normalized()
            self.last_mouse_pos = img_pos
            self.update()

    def mouseReleaseEvent(self, event):
        self.mode = None

    def get_real_crop_coordinates(self):
        r = self.crop_rect_img_coord
        if self.original_pixmap:
            w = self.original_pixmap.width()
            h = self.original_pixmap.height()
            r = r.intersected(QRectF(0, 0, w, h))
        return int(r.x()), int(r.y()), int(r.width()), int(r.height())

# ==========================================
# 4. Export Worker (Safe FPS)
# ==========================================
class VideoProcessWorker(QThread):
    finished_signal = Signal(bool, str)
    def __init__(self, input_path, output_path, start_time, end_time, crop_params):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.start_time = start_time
        self.end_time = end_time
        self.crop_params = crop_params

    def run(self):
        try:
            clip = VideoFileClip(self.input_path)
            
            # --- [FPS Fix for WebM] ---
            src_fps = clip.fps
            
            # 1. FPS is None
            # 2. FPS > 60 (WebM 1000fps bug)
            # 3. FPS < 1
            # -> Force 30fps
            if src_fps is None or src_fps > 60.0 or src_fps < 1.0:
                output_fps = 30.0
            else:
                output_fps = src_fps
            
            end = min(self.end_time, clip.duration)
            if self.start_time >= end: self.start_time = 0
            
            trimmed = clip.subclip(self.start_time, end)
            x, y, w, h = self.crop_params
            
            if w > 10 and h > 10:
                final = trimmed.crop(x1=x, y1=y, width=w, height=h)
            else:
                final = trimmed
            
            final.write_videofile(
                self.output_path, 
                fps=output_fps, # Explicit FPS
                codec='libx264', 
                audio_codec='aac', 
                logger=None
            )
            
            clip.close()
            final.close()
            self.finished_signal.emit(True, f"Export Complete!\nFPS: {output_fps}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

# ==========================================
# 5. Main Window
# ==========================================
class ProVideoEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DINKI'ssTyle Video Crop & Trim v2.0")
        self.resize(1000, 850)
        
        # Enable Drag & Drop
        self.setAcceptDrops(True)
        
        self.input_path = ""
        self.duration = 0
        self.current_zoom = 1.0 
        
        self.preview_worker = PreviewWorker()
        self.preview_worker.frame_ready.connect(self.update_preview_image)
        self.preview_worker.start()

        self.init_ui()

    def closeEvent(self, event):
        self.preview_worker.stop()
        super().closeEvent(event)

    # --- Drag & Drop Handlers ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                self.load_video_from_path(file_path)
            else:
                QMessageBox.warning(self, "Unsupported File", "Please drop video files only.")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top
        top_layout = QHBoxLayout()
        self.lbl_file = QLabel("Open a file or Drag & Drop here.")
        btn_open = QPushButton("📂 Open File")
        btn_open.clicked.connect(self.open_file_dialog)
        top_layout.addWidget(self.lbl_file)
        top_layout.addWidget(btn_open)
        layout.addLayout(top_layout)

        # Viewer
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("background-color: #333;")
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.crop_widget = ZoomableCropWidget()
        self.scroll_area.setWidget(self.crop_widget)
        layout.addWidget(self.scroll_area)

        # Zoom Controls (Fit included)
        zoom_layout = QHBoxLayout()
        zoom_layout.setAlignment(Qt.AlignCenter)
        
        btn_fit = QPushButton("Fit to Screen")
        btn_fit.clicked.connect(self.zoom_fit)
        
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(30, 30)
        btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.input_zoom = QLineEdit("100")
        self.input_zoom.setFixedSize(50, 30)
        self.input_zoom.setAlignment(Qt.AlignCenter)
        self.input_zoom.setValidator(QIntValidator(10, 500))
        self.input_zoom.returnPressed.connect(self.apply_manual_zoom)
        
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(30, 30)
        btn_zoom_in.clicked.connect(self.zoom_in)
        
        zoom_layout.addWidget(btn_fit)
        zoom_layout.addSpacing(20)
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(self.input_zoom)
        zoom_layout.addWidget(QLabel("%"))
        zoom_layout.addWidget(btn_zoom_in)
        layout.addLayout(zoom_layout)

        # Bottom Controls
        control_panel = QWidget()
        control_panel.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        cp_layout = QVBoxLayout(control_panel)
        
        self.range_slider = RangeSlider()
        self.range_slider.rangeChanged.connect(self.on_timeline_changed)
        self.range_slider.setEnabled(False)
        
        cp_layout.addWidget(QLabel("✂️ Trim & Playhead Position"))
        cp_layout.addWidget(self.range_slider)
        
        self.lbl_time_info = QLabel("0.0s")
        self.lbl_time_info.setAlignment(Qt.AlignCenter)
        cp_layout.addWidget(self.lbl_time_info)
        
        self.btn_run = QPushButton("💾 Export Video")
        self.btn_run.setFixedHeight(45)
        self.btn_run.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.process_video)
        self.btn_run.setEnabled(False)
        
        cp_layout.addWidget(self.btn_run)
        self.pbar = QProgressBar()
        self.pbar.hide()
        cp_layout.addWidget(self.pbar)
        layout.addWidget(control_panel)

    # --- Timeline & Preview Logic ---
    def on_timeline_changed(self, start, end, cur, who_moved):
        # Update Info Label
        if who_moved == "cur":
            info = f"Current: {cur:.2f}s"
        else:
            info = f"Range: {start:.1f}s ~ {end:.1f}s (Duration: {end-start:.1f}s)"
        self.lbl_time_info.setText(info)
        
        # Request Preview
        target_t = cur if who_moved == "cur" else (start if who_moved == "start" else end)
        self.preview_worker.request_frame(target_t)

    def update_preview_image(self, frame):
        self.crop_widget.set_image(frame)

    # --- Zoom Logic (Fit included) ---
    def update_zoom_ui(self):
        percent = int(self.current_zoom * 100)
        self.input_zoom.setText(str(percent))
        self.crop_widget.set_zoom(self.current_zoom)

    def zoom_fit(self):
        """Fit video to current viewport size"""
        if self.crop_widget.original_pixmap is None:
            return
            
        vp_w = self.scroll_area.viewport().width()
        vp_h = self.scroll_area.viewport().height()
        
        img_w = self.crop_widget.original_pixmap.width()
        img_h = self.crop_widget.original_pixmap.height()
        
        if img_w == 0 or img_h == 0: return

        ratio_w = vp_w / img_w
        ratio_h = vp_h / img_h
        
        new_zoom = min(ratio_w, ratio_h) * 0.95
        
        self.current_zoom = new_zoom
        self.update_zoom_ui()

    def zoom_in(self):
        self.current_zoom += 0.1
        self.update_zoom_ui()

    def zoom_out(self):
        if self.current_zoom > 0.1:
            self.current_zoom -= 0.1
            self.update_zoom_ui()

    def apply_manual_zoom(self):
        try:
            val = int(self.input_zoom.text())
            if val < 10: val = 10
            if val > 500: val = 500
            self.current_zoom = val / 100.0
            self.update_zoom_ui()
        except ValueError: pass

    # --- File Loading ---
    def open_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video (*.mp4 *.mov *.avi *.mkv *.webm)")
        if fname:
            self.load_video_from_path(fname)

    def load_video_from_path(self, fname):
        self.input_path = fname
        self.lbl_file.setText(os.path.basename(fname))
        try:
            clip = VideoFileClip(fname)
            self.duration = clip.duration
            frame = clip.get_frame(0)
            clip.close()
            
            self.preview_worker.load_video(fname)

            self.crop_widget.is_cropping = False
            self.crop_widget.set_image(frame)
            
            self.range_slider.set_duration(self.duration)
            self.range_slider.setEnabled(True)
            self.btn_run.setEnabled(True)
            self.on_timeline_changed(0, self.duration, 0, "cur")
            
            self.zoom_fit()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    # --- Export Logic ---
    def process_video(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "export.mp4", "MP4 (*.mp4)")
        if not save_path: return
        
        start = self.range_slider.start_val
        end = self.range_slider.end_val
        crop_coords = self.crop_widget.get_real_crop_coordinates()
        
        self.btn_run.setEnabled(False)
        self.pbar.show()
        self.pbar.setRange(0, 0)
        
        self.worker = VideoProcessWorker(self.input_path, save_path, start, end, crop_coords)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success, msg):
        self.pbar.hide()
        self.btn_run.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Failure", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProVideoEditor()
    window.show()
    sys.exit(app.exec())