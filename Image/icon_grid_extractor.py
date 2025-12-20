# -----------------------------
# (C) 2025 DINKI'ssTyle
# -----------------------------
import sys
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

from qtpy import QtCore, QtGui, QtWidgets
import json



# -----------------------------
# Utils
# -----------------------------
def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def qimage_to_rgba_np(img: QtGui.QImage) -> np.ndarray:
    """QImage -> RGBA uint8 (H,W,4)"""
    img = img.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(h * img.bytesPerLine())
    arr = np.frombuffer(ptr, np.uint8).reshape((h, img.bytesPerLine()))
    arr = arr[:, : w * 4].reshape((h, w, 4))
    return arr.copy()


def rgba_np_to_qimage(arr: np.ndarray) -> QtGui.QImage:
    """RGBA uint8 (H,W,4) -> QImage"""
    h, w, _ = arr.shape
    qimg = QtGui.QImage(arr.data, w, h, w * 4, QtGui.QImage.Format.Format_RGBA8888)
    return qimg.copy()


def trim_transparent(rgba: np.ndarray) -> np.ndarray:
    """Trim fully transparent borders (alpha==0)."""
    a = rgba[..., 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0 or len(ys) == 0:
        return rgba[:1, :1].copy()  # fully transparent
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    return rgba[y0:y1 + 1, x0:x1 + 1].copy()


def limit_size_keep_aspect(rgba: np.ndarray, max_px: int) -> np.ndarray:
    """Resize so max(width,height) <= max_px, keep aspect."""
    if max_px <= 0:
        return rgba
    h, w = rgba.shape[:2]
    m = max(h, w)
    if m <= max_px:
        return rgba
    scale = max_px / float(m)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    pil = Image.fromarray(rgba, mode="RGBA")
    pil = pil.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
    return np.array(pil, dtype=np.uint8)


# -----------------------------
# Background key mask
# -----------------------------
def build_alpha_mask_by_color_key(
    rgba: np.ndarray,
    key_rgb: Tuple[int, int, int],
    tolerance: int,
    feather_radius: int,
) -> np.ndarray:
    """
    Alpha mask (0..255):
      - pixels close to key become transparent
      - feather uses Gaussian blur (soft edge)
    """
    rgb = rgba[..., :3].astype(np.int16)
    key = np.array(key_rgb, dtype=np.int16)[None, None, :]
    diff = np.abs(rgb - key)
    dist = diff.max(axis=2)  # 0..255
    mask = np.ones((rgba.shape[0], rgba.shape[1]), dtype=np.uint8) * 255
    mask[dist <= tolerance] = 0

    if feather_radius > 0:
        pil = Image.fromarray(mask, mode="L")
        pil = pil.filter(ImageFilter.GaussianBlur(radius=feather_radius))
        mask = np.array(pil, dtype=np.uint8)

    return mask


def apply_alpha_mask(rgba: np.ndarray, alpha_mask: np.ndarray) -> np.ndarray:
    out = rgba.copy()
    out[..., 3] = (out[..., 3].astype(np.uint16) * alpha_mask.astype(np.uint16) // 255).astype(np.uint8)
    return out


# -----------------------------
# Draggable grid line item
# -----------------------------
class DraggableGridLine(QtWidgets.QGraphicsLineItem):
    """
    axis='x': vertical line (moves only in X)
    axis='y': horizontal line (moves only in Y)
    """
    def __init__(
        self,
        axis: str,
        value: int,
        max_w: int,
        max_h: int,
        on_moved_cb,
        on_remove_cb,
        on_release_cb,
        pen: QtGui.QPen,
    ):
        super().__init__()
        self.axis = axis
        self.value = value
        self.max_w = max_w
        self.max_h = max_h
        self.on_moved_cb = on_moved_cb
        self.on_remove_cb = on_remove_cb
        self.on_release_cb = on_release_cb

        self.setPen(pen)
        self.setZValue(10)
        self.setToolTip("Drag to move • Right-click to remove")
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton | QtCore.Qt.MouseButton.RightButton)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        if axis == "x":
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
            self.setLine(0, 0, 0, max_h)
            self.setPos(value, 0)
        else:
            self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
            self.setLine(0, 0, max_w, 0)
            self.setPos(0, value)

    def shape(self):
        path = super().shape()
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(15)  # 잡기 편하게 히트박스 확장
        return stroker.createStroke(path)

    def mousePressEvent(self, e: QtWidgets.QGraphicsSceneMouseEvent):
        if e.button() == QtCore.Qt.MouseButton.RightButton:
            self.on_remove_cb(self.axis, self.value)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QtWidgets.QGraphicsSceneMouseEvent):
        super().mouseReleaseEvent(e)
        if self.on_release_cb:
            self.on_release_cb(self.axis, self.value)

    def itemChange(self, change, value):
        # constrain movement to one axis and within bounds
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            p: QtCore.QPointF = value
            if self.axis == "x":
                new_x = clamp(int(round(p.x())), 0, self.max_w)
                return QtCore.QPointF(new_x, 0)
            else:
                new_y = clamp(int(round(p.y())), 0, self.max_h)
                return QtCore.QPointF(0, new_y)

        # after move, notify to update stored line value
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.axis == "x":
                new_v = int(round(self.pos().x()))
            else:
                new_v = int(round(self.pos().y()))
            if new_v != self.value:
                old = self.value
                self.value = new_v
                self.on_moved_cb(self.axis, old, new_v)

        return super().itemChange(change, value)


        return super().itemChange(change, value)


# -----------------------------
# Grid Cell (for naming)
# -----------------------------
class GridCellItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, r, c, rect, name, on_rename_cb):
        super().__init__(rect)
        self.r = r
        self.c = c
        self.name = name
        self.on_rename_cb = on_rename_cb

        # Appearance
        self.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 0)))  # Invisible border
        self.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0))) # Transparent fill
        self.setZValue(5) # Below lines (10)

        if name:
            self.setup_label(rect)

    def setup_label(self, rect):
        # Add text label if name exists
        text = QtWidgets.QGraphicsTextItem(self.name, self)
        # Center the text
        font = QtGui.QFont()
        font.setPixelSize(max(10, int(rect.height() / 5)))
        text.setFont(font)
        text.setDefaultTextColor(QtGui.QColor(255, 0, 0, 200)) # Reddish
        
        br = text.boundingRect()
        tx = rect.x() + (rect.width() - br.width()) / 2
        ty = rect.y() + (rect.height() - br.height()) / 2
        text.setPos(tx, ty)

    def mouseDoubleClickEvent(self, e):
        # Ask for new name
        text, ok = QtWidgets.QInputDialog.getText(None, "Icon Name", 
                                                  f"Enter name for cell ({self.r},{self.c}):", 
                                                  text=self.name)
        if ok:
            self.on_rename_cb(self.r, self.c, text)

    def paint(self, painter, option, widget=None):
        # Optional: draw subtle highlight on hover? For now just transparent logic container
        super().paint(painter, option, widget)


# -----------------------------
# Rulers
# -----------------------------
class HRuler(QtWidgets.QWidget):
    addLine = QtCore.Signal(int)
    removeNearest = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._scale = 1.0
        self._offset_x = 0.0
        self._lines: List[int] = []

    def setState(self, scale: float, offset_x: float, lines: List[int]):
        self._scale = scale
        self._offset_x = offset_x
        self._lines = lines
        self.update()

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        x_img = int(self._offset_x + e.position().x() / max(1e-6, self._scale))
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self.addLine.emit(x_img)
        elif e.button() == QtCore.Qt.MouseButton.RightButton:
            self.removeNearest.emit(x_img)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(245, 245, 248))
        p.setPen(QtGui.QPen(QtGui.QColor(140, 140, 150)))

        w = self.width()
        step = 50
        start = int(self._offset_x // step) * step
        end = int(self._offset_x + w / max(1e-6, self._scale)) + step

        for x in range(start, end, step):
            vx = int((x - self._offset_x) * self._scale)
            p.drawLine(vx, 0, vx, 12)
            p.drawText(vx + 2, 24, str(x))

        p.setPen(QtGui.QPen(QtGui.QColor(37, 99, 235), 2))
        for x in self._lines:
            vx = int((x - self._offset_x) * self._scale)
            p.drawLine(vx, 0, vx, self.height())


class VRuler(QtWidgets.QWidget):
    addLine = QtCore.Signal(int)
    removeNearest = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(28)
        self._scale = 1.0
        self._offset_y = 0.0
        self._lines: List[int] = []

    def setState(self, scale: float, offset_y: float, lines: List[int]):
        self._scale = scale
        self._offset_y = offset_y
        self._lines = lines
        self.update()

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        y_img = int(self._offset_y + e.position().y() / max(1e-6, self._scale))
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self.addLine.emit(y_img)
        elif e.button() == QtCore.Qt.MouseButton.RightButton:
            self.removeNearest.emit(y_img)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(245, 245, 248))
        p.setPen(QtGui.QPen(QtGui.QColor(140, 140, 150)))

        h = self.height()
        step = 50
        start = int(self._offset_y // step) * step
        end = int(self._offset_y + h / max(1e-6, self._scale)) + step

        for y in range(start, end, step):
            vy = int((y - self._offset_y) * self._scale)
            p.drawLine(0, vy, 12, vy)
            p.save()
            p.translate(24, vy - 2)
            p.rotate(-90)
            p.drawText(0, 0, str(y))
            p.restore()

        p.setPen(QtGui.QPen(QtGui.QColor(37, 99, 235), 2))
        for y in self._lines:
            vy = int((y - self._offset_y) * self._scale)
            p.drawLine(0, vy, self.width(), vy)


# -----------------------------
# View (zoom/pan)
# -----------------------------
# -----------------------------
# View (zoom/pan)
# -----------------------------
class GraphicsView(QtWidgets.QGraphicsView):
    viewChanged = QtCore.Signal()
    # fileDropped removed to let parent handle it

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing |
            QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # self.setAcceptDrops(True)  <-- Disabled ensures event propogation to MainWindow

    def wheelEvent(self, e: QtGui.QWheelEvent):
        if e.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            delta = e.angleDelta().y()
            factor = 1.0015 ** delta
            self.scale(factor, factor)
            self.viewChanged.emit()
        else:
            super().wheelEvent(e)

    def scrollContentsBy(self, dx: int, dy: int):
        super().scrollContentsBy(dx, dy)
        self.viewChanged.emit()

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e)
        self.viewChanged.emit()

    # Drag and Drop handlers removed from View so they bubble up to MainWindow




# -----------------------------
# Export options
# -----------------------------
@dataclass
class ExportOptions:
    fmt: str        # "png" or "ico"
    trim: bool
    limit_px: int


# -----------------------------
# MainWindow
# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Icon Grid Extractor - DINKI'ssTyle")
        self.resize(1100, 800)
        self.setAcceptDrops(True)

        # Scene/View
        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = GraphicsView(self.scene)
        self.view.viewChanged.connect(self.sync_rulers)


        # Rulers
        self.hRuler = HRuler()
        self.vRuler = VRuler()
        self.hRuler.addLine.connect(self.add_x_line)
        self.vRuler.addLine.connect(self.add_y_line)
        self.hRuler.removeNearest.connect(lambda x: self.remove_nearest_line("x", x))
        self.vRuler.removeNearest.connect(lambda y: self.remove_nearest_line("y", y))

        # Layout (ruler + view)
        central = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(central)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        corner = QtWidgets.QWidget()
        corner.setFixedSize(28, 28)
        corner.setStyleSheet("background:#f5f5f8; border-right:1px solid #e5e7eb; border-bottom:1px solid #e5e7eb;")

        grid.addWidget(corner, 0, 0)
        grid.addWidget(self.hRuler, 0, 1)
        grid.addWidget(self.vRuler, 1, 0)
        grid.addWidget(self.view, 1, 1)
        self.setCentralWidget(central)

        # State
        self.orig_qimg: Optional[QtGui.QImage] = None
        self.preview_qimg: Optional[QtGui.QImage] = None

        self.bg_key: Optional[Tuple[int, int, int]] = None
        self.alpha_mask: Optional[np.ndarray] = None
        self.pick_bg_mode = False

        self.image_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self.grid_items: List[QtWidgets.QGraphicsItem] = []
        self.cell_items: List[QtWidgets.QGraphicsItem] = [] # For grid cells
        self.x_lines: List[int] = []
        self.y_lines: List[int] = []
        self.cell_data: dict = {} # (r, c) -> name
        self.current_image_path: Optional[str] = None # Track current file for .grid saving/loading

        # Pen for grid
        self.grid_pen = QtGui.QPen(QtGui.QColor(37, 99, 235, 210), 1)
        self.grid_pen.setCosmetic(True)

        # Toolbar / Status
        self._build_toolbar()
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        # Canvas BG default
        self._set_canvas_bg("#ffffff")

        # For BG picking
        self.view.viewport().installEventFilter(self)

    # -----------------
    # Toolbar
    # -----------------
    def _build_toolbar(self):
        tb = QtWidgets.QToolBar("Tools")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_open = QtGui.QAction("Open", self)
        act_open.triggered.connect(self.open_image)
        tb.addAction(act_open)

        act_clear_grid = QtGui.QAction("Clear Grid", self)
        act_clear_grid.triggered.connect(self.clear_grid)
        tb.addAction(act_clear_grid)

        tb.addSeparator()

        self.btn_pick_bg = QtWidgets.QToolButton()
        self.btn_pick_bg.setText("Pick BG")
        self.btn_pick_bg.setCheckable(True)
        self.btn_pick_bg.toggled.connect(self.toggle_pick_bg)
        tb.addWidget(self.btn_pick_bg)

        tb.addWidget(QtWidgets.QLabel(" Tol:"))
        self.sl_tol = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sl_tol.setRange(0, 80)
        self.sl_tol.setValue(16)
        self.sl_tol.setFixedWidth(120)
        self.sl_tol.valueChanged.connect(self.rebuild_mask)
        tb.addWidget(self.sl_tol)

        self.chk_aa = QtWidgets.QCheckBox("AA")
        self.chk_aa.setChecked(True)
        self.chk_aa.stateChanged.connect(self.rebuild_mask)
        tb.addWidget(self.chk_aa)

        tb.addWidget(QtWidgets.QLabel(" Feather:"))
        self.sp_feather = QtWidgets.QSpinBox()
        self.sp_feather.setRange(0, 12)
        self.sp_feather.setValue(3)
        self.sp_feather.valueChanged.connect(self.rebuild_mask)
        tb.addWidget(self.sp_feather)

        act_clear_mask = QtGui.QAction("Clear Mask", self)
        act_clear_mask.triggered.connect(self.clear_mask)
        tb.addAction(act_clear_mask)

        tb.addSeparator()

        act_canvas_bg = QtGui.QAction("Canvas BG", self)
        act_canvas_bg.triggered.connect(self.pick_canvas_bg)
        tb.addAction(act_canvas_bg)

        tb.addSeparator()

        tb.addWidget(QtWidgets.QLabel(" Export:"))
        self.cmb_fmt = QtWidgets.QComboBox()
        self.cmb_fmt.addItems(["png", "ico"])
        tb.addWidget(self.cmb_fmt)

        self.chk_trim = QtWidgets.QCheckBox("Trim")
        self.chk_trim.setChecked(True)
        tb.addWidget(self.chk_trim)

        tb.addWidget(QtWidgets.QLabel(" Limit(px):"))
        self.sp_limit = QtWidgets.QSpinBox()
        self.sp_limit.setRange(0, 2048)
        self.sp_limit.setValue(256)
        self.sp_limit.setToolTip("0 = no limit")
        tb.addWidget(self.sp_limit)

        act_export = QtGui.QAction("Export", self)
        act_export.triggered.connect(self.export_slices)
        tb.addAction(act_export)

    # -----------------
    # Event Filter (BG pick)
    # -----------------
    def dragEnterEvent(self, e: QtGui.QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QtGui.QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.load_image(path)

    def eventFilter(self, obj, event):
        if obj == self.view.viewport() and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if self.pick_bg_mode and self.orig_qimg is not None and self.image_item is not None:
                pos = event.position().toPoint()
                scene_pos = self.view.mapToScene(pos)
                img_pos = self.image_item.mapFromScene(scene_pos)
                x, y = int(img_pos.x()), int(img_pos.y())

                if 0 <= x < self.orig_qimg.width() and 0 <= y < self.orig_qimg.height():
                    c = QtGui.QColor(self.orig_qimg.pixel(x, y))
                    self.bg_key = (c.red(), c.green(), c.blue())
                    self.status.showMessage(f"BG key picked: {self.bg_key}", 3000)
                    self.rebuild_mask()
                    return True

        return super().eventFilter(obj, event)

    # -----------------
    # Image load / preview update
    # -----------------
    # -----------------
    # Image load / preview update
    # -----------------
    def open_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self.load_image(path)

    def load_image(self, path: str):
        qimg = QtGui.QImage(path)
        if qimg.isNull():
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to load image.")
            return

        self.current_image_path = path

        self.orig_qimg = qimg.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        self.preview_qimg = self.orig_qimg
        self.bg_key = None
        self.alpha_mask = None

        self.scene.clear()
        self.grid_items.clear()
        self.cell_items.clear()
        self.x_lines.clear()
        self.y_lines.clear()
        self.cell_data.clear()

        self.image_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(self.preview_qimg))
        self.image_item.setZValue(0)
        self.scene.addItem(self.image_item)
        self.scene.setSceneRect(0, 0, self.preview_qimg.width(), self.preview_qimg.height())

        self.view.resetTransform()
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

        # Try to load .grid file
        grid_file = os.path.splitext(path)[0] + ".grid"
        if os.path.exists(grid_file):
            self.load_grid_data(grid_file)

        self._redraw_grid_lines()
        self.sync_rulers()
        self.status.showMessage(f"Loaded: {os.path.basename(path)} ({qimg.width()}x{qimg.height()})", 4000)

    def load_grid_data(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.x_lines = sorted(data.get("x_lines", []))
            self.y_lines = sorted(data.get("y_lines", []))
            
            # Load cells (key is string "r,c", convert to tuple)
            raw_cells = data.get("cells", {})
            for k, v in raw_cells.items():
                try:
                    r, c = map(int, k.split(","))
                    self.cell_data[(r, c)] = v
                except:
                    pass
            
            # Restore options
            opts = data.get("options", {})
            if "trim" in opts: self.chk_trim.setChecked(opts["trim"])
            if "limit_px" in opts: self.sp_limit.setValue(opts["limit_px"])
            if "fmt" in opts: 
                idx = self.cmb_fmt.findText(opts["fmt"])
                if idx >= 0: self.cmb_fmt.setCurrentIndex(idx)
            
            # Restore mask
            mask_info = data.get("mask", {})
            if "key" in mask_info:
                self.bg_key = tuple(mask_info["key"])
                if "tol" in mask_info: self.sl_tol.setValue(mask_info["tol"])
                if "feather" in mask_info: self.sp_feather.setValue(mask_info["feather"])
                if "aa" in mask_info: self.chk_aa.setChecked(mask_info["aa"])
                self.rebuild_mask()

            print(f"Grid loaded from {path}")

        except Exception as e:
            print(f"Failed to load grid: {e}")

    def save_grid_data(self, path: str):
        # Prepare data
        # Convert tuple keys to string "r,c"
        cells_str_key = {f"{r},{c}": v for (r, c), v in self.cell_data.items()}
        
        data = {
            "x_lines": self.x_lines,
            "y_lines": self.y_lines,
            "cells": cells_str_key,
            "options": {
                "trim": self.chk_trim.isChecked(),
                "limit_px": self.sp_limit.value(),
                "fmt": self.cmb_fmt.currentText()
            }
        }
        
        if self.bg_key:
            data["mask"] = {
                "key": self.bg_key,
                "tol": self.sl_tol.value(),
                "feather": self.sp_feather.value(),
                "aa": self.chk_aa.isChecked()
            }
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Grid saved to {path}")
        except Exception as e:
            print(f"Failed to save grid: {e}")

    def _update_preview_pixmap(self):
        if self.image_item is None or self.preview_qimg is None:
            return
        self.image_item.setPixmap(QtGui.QPixmap.fromImage(self.preview_qimg))
        self.scene.setSceneRect(0, 0, self.preview_qimg.width(), self.preview_qimg.height())
        self._redraw_grid_lines()
        self.sync_rulers()

    # -----------------
    # Grid line management
    # -----------------
    def add_x_line(self, x: int):
        if self.preview_qimg is None:
            return
        x = clamp(x, 0, self.preview_qimg.width())
        if x in self.x_lines:
            return
        self.x_lines.append(x)
        self.x_lines.sort()
        self._redraw_grid_lines()

    def add_y_line(self, y: int):
        if self.preview_qimg is None:
            return
        y = clamp(y, 0, self.preview_qimg.height())
        if y in self.y_lines:
            return
        self.y_lines.append(y)
        self.y_lines.sort()
        self._redraw_grid_lines()

    def remove_nearest_line(self, axis: str, pos: int):
        lines = self.x_lines if axis == "x" else self.y_lines
        if not lines:
            return
        nearest = min(lines, key=lambda v: abs(v - pos))
        if abs(nearest - pos) <= 15:
            lines.remove(nearest)
            self._redraw_grid_lines()

    def clear_grid(self):
        self.x_lines.clear()
        self.y_lines.clear()
        self._redraw_grid_lines()

    # ✅ called by draggable line
    # ✅ called by draggable line
    def on_line_moved(self, axis: str, old: int, new: int):
        if self.preview_qimg is None:
            return

        if axis == "x":
            if old in self.x_lines:
                self.x_lines.remove(old)
            if new not in self.x_lines:
                self.x_lines.append(new)
            # NO SORT yet -> wait for release
        else:
            if old in self.y_lines:
                self.y_lines.remove(old)
            if new not in self.y_lines:
                self.y_lines.append(new)

        self.sync_rulers()
        # DO NOT REDRAW ALL ITEMS HERE causing crash

    # ✅ called on release
    def on_line_release(self, axis: str, last_val: int):
        self.x_lines.sort()
        self.y_lines.sort()
        self._redraw_grid_lines()

    # ✅ called by draggable line
    def on_line_remove(self, axis: str, v: int):
        if axis == "x":
            if v in self.x_lines:
                self.x_lines.remove(v)
        else:
            if v in self.y_lines:
                self.y_lines.remove(v)
        self._redraw_grid_lines()

    def on_cell_rename(self, r, c, new_name):
        self.cell_data[(r, c)] = new_name
        self._redraw_grid_lines() # Refresh labels

    def _redraw_grid_lines(self):
        # remove old grid items
        for it in self.grid_items:
            self.scene.removeItem(it)
        self.grid_items.clear()

        if self.preview_qimg is None:
            return

        w, h = self.preview_qimg.width(), self.preview_qimg.height()

        # Draw Cells
        # Create sorted unique coordinates including 0 and max
        xs = [0] + sorted([x for x in self.x_lines if 0 < x < w]) + [w]
        ys = [0] + sorted([y for y in self.y_lines if 0 < y < h]) + [h]

        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                x0, x1 = xs[c], xs[c + 1]
                y0, y1 = ys[r], ys[r + 1]
                
                # Check if we have a name
                name = self.cell_data.get((r, c), "")
                
                rect = QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)
                cell_item = GridCellItem(r, c, rect, name, self.on_cell_rename)
                self.scene.addItem(cell_item)
                self.grid_items.append(cell_item)

        # vertical lines
        for x in self.x_lines:
            item = DraggableGridLine(
                axis="x",
                value=x,
                max_w=w,
                max_h=h,
                on_moved_cb=self.on_line_moved,
                on_remove_cb=self.on_line_remove,
                on_release_cb=self.on_line_release,
                pen=self.grid_pen,
            )
            self.scene.addItem(item)
            self.grid_items.append(item)

        # horizontal lines
        for y in self.y_lines:
            item = DraggableGridLine(
                axis="y",
                value=y,
                max_w=w,
                max_h=h,
                on_moved_cb=self.on_line_moved,
                on_remove_cb=self.on_line_remove,
                on_release_cb=self.on_line_release,
                pen=self.grid_pen,
            )
            self.scene.addItem(item)
            self.grid_items.append(item)

        self.sync_rulers()

    # -----------------
    # Ruler sync
    # -----------------
    def sync_rulers(self):
        if self.preview_qimg is None:
            self.hRuler.setState(1.0, 0.0, [])
            self.vRuler.setState(1.0, 0.0, [])
            return

        scale = self.view.transform().m11()
        top_left_scene = self.view.mapToScene(QtCore.QPoint(0, 0))
        offset_x = top_left_scene.x()
        offset_y = top_left_scene.y()

        self.hRuler.setState(scale, offset_x, self.x_lines)
        self.vRuler.setState(scale, offset_y, self.y_lines)

    # -----------------
    # Masking
    # -----------------
    def toggle_pick_bg(self, checked: bool):
        self.pick_bg_mode = checked
        self.view.setCursor(QtCore.Qt.CursorShape.CrossCursor if checked else QtCore.Qt.CursorShape.ArrowCursor)
        if checked:
            self.status.showMessage("Pick BG mode: click on image to choose background color.", 4000)

    def rebuild_mask(self):
        if self.orig_qimg is None:
            return

        if self.bg_key is None:
            self.preview_qimg = self.orig_qimg
            self._update_preview_pixmap()
            return

        tol = int(self.sl_tol.value())
        feather = int(self.sp_feather.value()) if self.chk_aa.isChecked() else 0

        rgba = qimage_to_rgba_np(self.orig_qimg)
        mask = build_alpha_mask_by_color_key(rgba, self.bg_key, tolerance=tol, feather_radius=feather)
        self.alpha_mask = mask
        out = apply_alpha_mask(rgba, mask)

        self.preview_qimg = rgba_np_to_qimage(out)
        self._update_preview_pixmap()

    def clear_mask(self):
        self.bg_key = None
        self.alpha_mask = None
        if self.orig_qimg is not None:
            self.preview_qimg = self.orig_qimg
            self._update_preview_pixmap()

    # -----------------
    # Canvas BG
    # -----------------
    def _set_canvas_bg(self, color_hex: str):
        self.view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(color_hex)))

    def pick_canvas_bg(self):
        c = QtWidgets.QColorDialog.getColor(parent=self, title="Pick Canvas Background")
        if c.isValid():
            self._set_canvas_bg(c.name())

    # -----------------
    # Export
    # -----------------
    def export_slices(self):
        if self.preview_qimg is None:
            QtWidgets.QMessageBox.information(self, "Info", "Load an image first.")
            return

        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if not out_dir:
            return

        opts = ExportOptions(
            fmt=self.cmb_fmt.currentText().lower(),
            trim=self.chk_trim.isChecked(),
            limit_px=int(self.sp_limit.value()),
        )

        rgba_full = qimage_to_rgba_np(self.preview_qimg)
        H, W = rgba_full.shape[:2]

        xs = [0] + sorted(set([x for x in self.x_lines if 0 < x < W])) + [W]
        ys = [0] + sorted(set([y for y in self.y_lines if 0 < y < H])) + [H]

        saved = 0
        idx = 0

        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                x0, x1 = xs[c], xs[c + 1]
                y0, y1 = ys[r], ys[r + 1]
                if x1 <= x0 or y1 <= y0:
                    continue

                cell = rgba_full[y0:y1, x0:x1].copy()

                # ✅ (요구사항) 완전 빈(완전 투명) 셀은 버림
                if np.all(cell[..., 3] == 0):
                    continue

                if opts.trim:
                    cell = trim_transparent(cell)
                    if np.all(cell[..., 3] == 0):
                        continue

                if opts.limit_px > 0:
                    cell = limit_size_keep_aspect(cell, opts.limit_px)
                    if np.all(cell[..., 3] == 0):
                        continue

                if (r, c) in self.cell_data and self.cell_data[(r, c)].strip():
                    base = self.cell_data[(r, c)].strip()
                else:
                    idx += 1
                    base = f"icon_{idx:03d}_r{r:02d}_c{c:02d}"

                if opts.fmt == "png":
                    path = os.path.join(out_dir, base + ".png")
                    Image.fromarray(cell, mode="RGBA").save(path, format="PNG")
                    saved += 1

                elif opts.fmt == "ico":
                    path = os.path.join(out_dir, base + ".ico")
                    pil = Image.fromarray(cell, mode="RGBA")

                    sizes = []
                    for s in [16, 24, 32, 48, 64, 128, 256]:
                        if s <= max(pil.size):
                            sizes.append((s, s))
                    if not sizes:
                        m = max(pil.size)
                        sizes = [(m, m)]

                    pil.save(path, format="ICO", sizes=sizes)
                    saved += 1

        # Save .grid file
        if self.current_image_path:
            grid_path = os.path.splitext(self.current_image_path)[0] + ".grid"
            self.save_grid_data(grid_path)

        self.status.showMessage(f"Exported {saved} file(s) to: {out_dir}", 6000)


# -----------------------------
# Main
# -----------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()