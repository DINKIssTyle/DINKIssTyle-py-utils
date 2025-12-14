#pqr cat "Image"
#pqr ubuntu "/home/dinki/python/default/.venv/bin/python"

import sys
import io
import os
import requests
from PIL import Image

# rembg imports
from rembg import remove, new_session

from PySide6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                               QGraphicsScene, QFileDialog, QToolBar, 
                               QMessageBox, QVBoxLayout, QWidget, QLabel,
                               QGraphicsRectItem, QGraphicsTextItem, QProgressDialog,
                               QSpinBox, QDoubleSpinBox)
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QThread
from PySide6.QtGui import (QPixmap, QImage, QAction, QDragEnterEvent, 
                           QDropEvent, QPainter, QPen, QColor, QWheelEvent, QMouseEvent, QFont)

# --- [Model Downloader Thread] ---
class ModelDownloader(QThread):
    progress = Signal(int)
    finished_download = Signal()
    error_occurred = Signal(str)

    def run(self):
        url = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
        home_dir = os.path.expanduser("~")
        model_dir = os.path.join(home_dir, ".u2net")
        model_path = os.path.join(model_dir, "u2net.onnx")

        try:
            if not os.path.exists(model_dir):
                os.makedirs(model_dir)

            response = requests.get(url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(model_path, "wb") as f:
                for data in response.iter_content(chunk_size=1024 * 1024):
                    if data:
                        f.write(data)
                        downloaded_size += len(data)
                        if total_size > 0:
                            percent = int((downloaded_size / total_size) * 100)
                            self.progress.emit(percent)
            
            self.finished_download.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))


# --- [Custom View Class] ---
class EditorGraphicsView(QGraphicsView):
    selectionChanged = Signal(bool)
    fileDropped = Signal(str)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor(40, 40, 40)) 

        self.is_selecting = False
        self.start_pos = QPointF()
        self.current_rect_item = None
        self.selection_rect = QRectF()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.fileDropped.emit(files[0])

    def wheelEvent(self, event: QWheelEvent):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event: QMouseEvent):
        if self.dragMode() == QGraphicsView.DragMode.NoDrag and event.button() == Qt.MouseButton.LeftButton:
            # Deprecation fix
            pos = event.position() if hasattr(event, 'position') else event.pos()
            self.start_pos = self.mapToScene(pos.toPoint())
            
            self.remove_selection_item()

            self.current_rect_item = QGraphicsRectItem()
            self.current_rect_item.setPen(QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine))
            self.current_rect_item.setBrush(QColor(255, 0, 0, 50))
            self.scene().addItem(self.current_rect_item)
            self.current_rect_item.setRect(QRectF(self.start_pos, self.start_pos))
            self.is_selecting = True
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_selecting and self.current_rect_item:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            current_pos = self.mapToScene(pos.toPoint())
            
            rect = QRectF(self.start_pos, current_pos).normalized()
            self.current_rect_item.setRect(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_selecting and self.current_rect_item:
            self.is_selecting = False
            self.selection_rect = self.current_rect_item.rect()
            self.selectionChanged.emit(True)
            return
        super().mouseReleaseEvent(event)

    def remove_selection_item(self):
        if self.current_rect_item:
            if self.scene() and self.current_rect_item.scene() == self.scene():
                self.scene().removeItem(self.current_rect_item)
            self.current_rect_item = None

    def reset_selection_state(self):
        self.current_rect_item = None
        self.selection_rect = QRectF()
        self.selectionChanged.emit(False)


# --- [Main Window] ---
class ImageEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DINKI'ssTyle Crop RMBG Trim")
        self.resize(1400, 900) # 가로를 조금 더 넓게

        self.current_image: Image.Image = None
        self.rembg_session = None 
        
        # Undo/Redo Stacks
        self.undo_stack = []
        self.redo_stack = []
        
        self.init_ui()
        self.show_welcome_message()

    def init_ui(self):
        # 1. Main Toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(toolbar.iconSize() * 1.2)
        # 텍스트와 아이콘을 같이 표시하려면 아래 주석 해제
        # toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # [Group 1: File]
        btn_open = QAction("📂 Open", self)
        btn_open.triggered.connect(self.open_image_dialog)
        toolbar.addAction(btn_open)

        btn_save = QAction("💾 Save", self)
        btn_save.triggered.connect(self.save_image)
        toolbar.addAction(btn_save)

        toolbar.addSeparator()

        # [Group 2: Undo/Redo]
        self.act_undo = QAction("↩️ Undo", self)
        self.act_undo.triggered.connect(self.undo)
        self.act_undo.setShortcut("Ctrl+Z")
        self.act_undo.setEnabled(False)
        toolbar.addAction(self.act_undo)

        self.act_redo = QAction("↪️ Redo", self)
        self.act_redo.triggered.connect(self.redo)
        self.act_redo.setShortcut("Ctrl+Shift+Z")
        self.act_redo.setEnabled(False)
        toolbar.addAction(self.act_redo)

        toolbar.addSeparator()

        # [Group 3: View]
        btn_fit = QAction("Fit", self)
        btn_fit.triggered.connect(self.fit_image)
        toolbar.addAction(btn_fit)

        btn_zoom_100 = QAction("1:1", self)
        btn_zoom_100.triggered.connect(self.reset_zoom)
        toolbar.addAction(btn_zoom_100)

        toolbar.addSeparator()

        # [Group 4: Selection/Crop]
        self.act_select_mode = QAction("🔲 Select", self)
        self.act_select_mode.setCheckable(True)
        self.act_select_mode.toggled.connect(self.toggle_select_mode)
        toolbar.addAction(self.act_select_mode)

        self.act_crop_apply = QAction("✂️ Crop", self)
        self.act_crop_apply.triggered.connect(self.process_manual_crop)
        self.act_crop_apply.setEnabled(False) 
        toolbar.addAction(self.act_crop_apply)

        toolbar.addSeparator()

        # [Group 5: Remove BG & Settings & Trim] 
        # 순서: Remove BG -> Settings -> Separator -> Trim
        
        # 5-1. Remove BG Button
        btn_rmbg = QAction("✨ Remove BG", self)
        btn_rmbg.triggered.connect(self.check_and_process_rmbg)
        toolbar.addAction(btn_rmbg)

        # 5-2. Settings (Sensitivity)
        lbl_sens = QLabel("  Sens: ")
        toolbar.addWidget(lbl_sens)
        
        self.spin_sensitivity = QDoubleSpinBox()
        self.spin_sensitivity.setRange(0.1, 2.0)
        self.spin_sensitivity.setSingleStep(0.1)
        self.spin_sensitivity.setValue(1.0)
        self.spin_sensitivity.setFixedWidth(60) # 너비 고정
        self.spin_sensitivity.setToolTip("Alpha Threshold (Default: 1.0)")
        toolbar.addWidget(self.spin_sensitivity)

        # 5-3. Settings (Resolution)
        lbl_res = QLabel("  Res: ")
        toolbar.addWidget(lbl_res)

        self.spin_resolution = QSpinBox()
        self.spin_resolution.setRange(256, 4096)
        self.spin_resolution.setSingleStep(64)
        self.spin_resolution.setValue(1024)
        self.spin_resolution.setFixedWidth(70) # 너비 고정
        self.spin_resolution.setToolTip("Processing Resolution")
        toolbar.addWidget(self.spin_resolution)

        # 5-4. Separator & Trim
        toolbar.addSeparator()

        btn_trim = QAction("📐 Trim", self)
        btn_trim.triggered.connect(self.process_auto_trim)
        toolbar.addAction(btn_trim)


        # 2. Main View
        self.scene = QGraphicsScene()
        self.view = EditorGraphicsView(self.scene)
        self.view.selectionChanged.connect(self.on_selection_changed)
        self.view.fileDropped.connect(self.load_image_file)
        
        self.setAcceptDrops(True)

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        
        self.lbl_info = QLabel("Ready")
        self.statusBar().addWidget(self.lbl_info)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    # --- [Undo/Redo System] ---
    def push_undo_state(self):
        if self.current_image:
            if len(self.undo_stack) >= 20:
                self.undo_stack.pop(0)
            self.undo_stack.append(self.current_image.copy())
            self.redo_stack.clear() 
            self.update_undo_redo_buttons()

    def undo(self):
        if not self.undo_stack: return
        if self.current_image:
            self.redo_stack.append(self.current_image.copy())
        
        prev_image = self.undo_stack.pop()
        self.current_image = prev_image
        self.update_view(save_undo=False)
        self.update_undo_redo_buttons()
        self.statusBar().showMessage("Undo performed", 2000)

    def redo(self):
        if not self.redo_stack: return
        if self.current_image:
            self.undo_stack.append(self.current_image.copy())

        next_image = self.redo_stack.pop()
        self.current_image = next_image
        self.update_view(save_undo=False)
        self.update_undo_redo_buttons()
        self.statusBar().showMessage("Redo performed", 2000)

    def update_undo_redo_buttons(self):
        self.act_undo.setEnabled(len(self.undo_stack) > 0)
        self.act_redo.setEnabled(len(self.redo_stack) > 0)


    # --- [Helper Functions] ---
    def show_welcome_message(self):
            self.scene.clear()
            self.view.reset_selection_state()
            
            # [수정됨] HTML 태그를 사용하여 텍스트 내부 중앙 정렬 적용
            text_content = """
            <div style='text-align: center;'>
                Open from File or Drag & Drop Image Here
            </div>
            """
            text_item = QGraphicsTextItem()
            text_item.setHtml(text_content) # setPlainText 대신 setHtml 사용
            
            font = QFont("Arial", 13, QFont.Weight.Bold)
            text_item.setFont(font)
            text_item.setDefaultTextColor(QColor(200, 200, 200))
            
            # 텍스트 아이템 자체를 화면 중앙(0,0)에 배치
            rect = text_item.boundingRect()
            text_item.setPos(-rect.width() / 2, -rect.height() / 2)
            
            self.scene.addItem(text_item)
            self.current_image = None
            self.act_crop_apply.setEnabled(False)
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update_undo_redo_buttons()
            self.lbl_info.setText("Waiting for image...")

    # --- View Control ---
    def fit_image(self):
        if self.scene.itemsBoundingRect().width() > 0:
            self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def reset_zoom(self):
        self.view.resetTransform()

    def toggle_select_mode(self, checked):
        if self.current_image is None:
            self.act_select_mode.setChecked(False)
            return
        if checked:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage("Drag mouse to select an area.")
        else:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
            self.view.remove_selection_item()
            self.view.reset_selection_state()
            self.statusBar().showMessage("Pan Mode")

    def on_selection_changed(self, has_selection):
        self.act_crop_apply.setEnabled(has_selection)
        if has_selection:
            self.statusBar().showMessage("Area selected. Press 'Crop Selection' to apply.")

    def update_view(self, save_undo=True):
        if self.current_image is None: return

        self.view.reset_selection_state() 

        im_data = io.BytesIO()
        self.current_image.save(im_data, format='PNG')
        qimg = QImage()
        qimg.loadFromData(im_data.getvalue())
        pixmap = QPixmap.fromImage(qimg)
        
        self.scene.clear()
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        if self.act_select_mode.isChecked():
            self.toggle_select_mode(True)

        self.lbl_info.setText(f"Size: {self.current_image.width} x {self.current_image.height} | Mode: {self.current_image.mode}")

    # --- File I/O ---
    def open_image_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_name:
            self.load_image_file(file_name)

    def load_image_file(self, path):
        try:
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update_undo_redo_buttons()

            self.current_image = Image.open(path).convert("RGBA")
            self.update_view(save_undo=False)
            self.fit_image()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {e}")

    def save_image(self):
        if self.current_image is None: return
        file_name, _ = QFileDialog.getSaveFileName(self, "Save as PNG", "result.png", "PNG Files (*.png)")
        if file_name:
            try:
                self.current_image.save(file_name, format="PNG")
                self.statusBar().showMessage(f"Saved: {file_name}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # --- Process Functions ---
    def check_and_process_rmbg(self):
        if self.current_image is None: return

        if self.rembg_session is not None:
            self.process_remove_background()
            return

        home_dir = os.path.expanduser("~")
        model_path = os.path.join(home_dir, ".u2net", "u2net.onnx")

        if os.path.exists(model_path):
            self.load_session_and_run()
        else:
            reply = QMessageBox.question(
                self, "Download Model", 
                "Missing AI model (~170MB). Download now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.start_model_download()

    def start_model_download(self):
        self.progress_dialog = QProgressDialog("Downloading AI Model...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)

        self.downloader = ModelDownloader()
        self.downloader.progress.connect(self.progress_dialog.setValue)
        self.downloader.finished_download.connect(self.on_download_finished)
        self.downloader.error_occurred.connect(self.on_download_error)
        self.progress_dialog.canceled.connect(self.downloader.terminate)
        self.downloader.start()

    def on_download_finished(self):
        self.progress_dialog.close()
        QMessageBox.information(self, "Success", "Model downloaded!")
        self.load_session_and_run()

    def on_download_error(self, error_msg):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"Download failed:\n{error_msg}")

    def load_session_and_run(self):
        self.statusBar().showMessage("Loading AI Model...")
        QApplication.processEvents()
        try:
            self.rembg_session = new_session("u2net")
            self.process_remove_background()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Session load failed: {e}")

    def process_remove_background(self):
        self.statusBar().showMessage("Processing Background Removal...")
        QApplication.processEvents()
        
        self.push_undo_state()

        try:
            sensitivity = self.spin_sensitivity.value()
            target_res = self.spin_resolution.value()
            
            original_size = self.current_image.size
            processing_image = self.current_image.copy()

            scale_factor = 1.0
            max_dim = max(original_size)
            if max_dim > target_res:
                scale_factor = target_res / max_dim
                new_size = (int(original_size[0] * scale_factor), int(original_size[1] * scale_factor))
                processing_image = processing_image.resize(new_size, Image.Resampling.LANCZOS)

            out_image = remove(processing_image, session=self.rembg_session)
            
            if scale_factor != 1.0:
                out_image = out_image.resize(original_size, Image.Resampling.LANCZOS)

            if sensitivity != 1.0:
                r, g, b, a = out_image.split()
                a = a.point(lambda p: min(255, int(p * sensitivity)))
                out_image.putalpha(a)

            self.current_image = out_image
            self.update_view()
            self.statusBar().showMessage("Background removed.", 3000)
            
        except Exception as e:
            if self.undo_stack:
                self.undo() 
            QMessageBox.critical(self, "Error", str(e))

    def process_auto_trim(self):
        if self.current_image is None: return
        self.push_undo_state()
        
        bbox = self.current_image.getbbox()
        if bbox:
            self.current_image = self.current_image.crop(bbox)
            self.update_view()
            self.fit_image()
            self.statusBar().showMessage("Trimmed.", 3000)
        else:
            if self.undo_stack: self.undo_stack.pop()
            QMessageBox.information(self, "Info", "Nothing to trim.")

    def process_manual_crop(self):
        if self.current_image is None or not self.view.selection_rect.isValid():
            return

        self.push_undo_state()

        rect = self.view.selection_rect
        left = max(0, int(rect.left()))
        top = max(0, int(rect.top()))
        right = min(self.current_image.width, int(rect.right()))
        bottom = min(self.current_image.height, int(rect.bottom()))

        if right > left and bottom > top:
            self.current_image = self.current_image.crop((left, top, right, bottom))
            self.update_view()
            self.fit_image()
            self.statusBar().showMessage("Cropped.", 3000)
            self.act_select_mode.setChecked(False)
        else:
            if self.undo_stack: self.undo_stack.pop()
            QMessageBox.warning(self, "Warning", "Invalid selection.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = ImageEditor()
    editor.show()
    sys.exit(app.exec())