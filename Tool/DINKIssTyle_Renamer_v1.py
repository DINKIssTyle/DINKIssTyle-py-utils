#pqr cat "Tool"
#pqr terminal true
import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                               QFileDialog, QLabel, QTabWidget, QLineEdit, QSpinBox, 
                               QHeaderView, QMessageBox, QComboBox, QCheckBox, QFrame, 
                               QToolButton, QMenu, QDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QDragEnterEvent, QDropEvent, QAction

# --- [UI 개선] 커스텀 메시지 박스 ---
class StyledMessageBox(QDialog):
    def __init__(self, title, message, icon_type="info", parent=None, is_dark=True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(350)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.lbl_msg = QLabel(message)
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setMinimumHeight(35)
        self.btn_ok.clicked.connect(self.accept)
        
        # 버튼 색상
        if icon_type == "success":
            self.btn_ok.setStyleSheet("""
                QPushButton { background-color: #2e7d32; color: white; border: none; border-radius: 5px; font-weight: bold; }
                QPushButton:hover { background-color: #388e3c; }
            """)
        else:
             self.btn_ok.setStyleSheet("""
                QPushButton { background-color: #d32f2f; color: white; border: none; border-radius: 5px; font-weight: bold; }
                QPushButton:hover { background-color: #e57373; }
            """)

        layout.addWidget(self.lbl_msg)
        layout.addWidget(self.btn_ok)
        self.setLayout(layout)
        
        # 다크/라이트 모드에 따른 다이얼로그 스타일 분기
        if is_dark:
            self.setStyleSheet("""
                QDialog { background-color: #252526; border: 1px solid #3e3e42; border-radius: 8px; }
                QLabel { color: #ffffff; font-weight: bold; font-size: 14px; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #ffffff; border: 1px solid #d1d1d6; border-radius: 8px; }
                QLabel { color: #000000; font-weight: bold; font-size: 14px; }
            """)

# --- 커스텀 테이블 ---
class FileDropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True) 
        self.setShowGrid(False) 
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setFocusPolicy(Qt.NoFocus)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            file_paths = []
            for url in event.mimeData().urls():
                file_paths.append(url.toLocalFile())
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()

# --- 메인 윈도우 ---
class SmartRenamer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DINKI'ssTyle Renamer v1.0")
        self.resize(1000, 800)
        
        self.items = [] 
        self.is_dark_mode = True 

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        self.layout = QVBoxLayout(main_widget)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        self.setup_top_controls()
        self.setup_list_view()
        self.setup_options_area()
        self.setup_bottom_controls()
        
        self.apply_theme() 

    def setup_top_controls(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 5)
        
        self.btn_add = QToolButton()
        self.btn_add.setText("Add Items ▾")
        self.btn_add.setMinimumWidth(130)
        self.btn_add.setMinimumHeight(32)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup) 
        self.btn_add.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        
        add_menu = QMenu(self)
        
        action_files = QAction("Add Files...", self)
        action_files.triggered.connect(self.add_files)
        add_menu.addAction(action_files)
        
        action_folder = QAction("Add Folder...", self)
        action_folder.triggered.connect(self.add_folders)
        add_menu.addAction(action_folder)
        
        self.btn_add.setMenu(add_menu)
        
        btn_clear = QPushButton("Clear List")
        btn_clear.setMinimumHeight(32)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_list)

        self.btn_theme = QPushButton("Switch to Light Mode")
        self.btn_theme.setMinimumHeight(32)
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setCheckable(True)
        self.btn_theme.setChecked(True) 
        self.btn_theme.clicked.connect(self.toggle_theme)
        
        layout.addWidget(self.btn_add)
        layout.addWidget(btn_clear)
        layout.addStretch()
        layout.addWidget(self.btn_theme)
        
        self.layout.addLayout(layout)

    def setup_list_view(self):
        self.table = FileDropTable()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Current Name", "New Name (Preview)", "Full Path"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.table.files_dropped.connect(self.handle_dropped_files)
        
        self.layout.addWidget(self.table, 1)

    def setup_options_area(self):
        self.opt_frame = QFrame()
        self.opt_frame.setObjectName("OptionFrame")
        
        v_layout = QVBoxLayout(self.opt_frame)
        v_layout.setContentsMargins(20, 20, 20, 20)
        v_layout.setSpacing(15)
        
        row1_layout = QHBoxLayout()
        lbl_scope = QLabel("Apply To:")
        lbl_scope.setObjectName("LabelBold")
        
        self.combo_scope = QComboBox()
        self.combo_scope.setMinimumWidth(220)
        self.combo_scope.addItems([
            "File Name Only (Keep Ext)",
            "Folder Name Only",
            "File & Folder Name",
            "File Name + Extension",
            "Extension Only"
        ])
        self.combo_scope.currentIndexChanged.connect(self.update_preview)
        
        row1_layout.addWidget(lbl_scope)
        row1_layout.addWidget(self.combo_scope)
        row1_layout.addStretch()
        v_layout.addLayout(row1_layout)

        self.tabs = QTabWidget()
        self.tabs.setFixedHeight(160)
        
        self.tab_new = QWidget()
        self.setup_tab_new()
        self.tabs.addTab(self.tab_new, "New Name")
        
        self.tab_replace = QWidget()
        self.setup_tab_replace()
        self.tabs.addTab(self.tab_replace, "Find / Replace")
        
        self.tab_prepend = QWidget()
        self.setup_tab_prepend()
        self.tabs.addTab(self.tab_prepend, "Prepend")
        
        self.tab_append = QWidget()
        self.setup_tab_append()
        self.tabs.addTab(self.tab_append, "Append")

        self.tabs.currentChanged.connect(self.update_preview)
        
        v_layout.addWidget(self.tabs)
        self.layout.addWidget(self.opt_frame, 0)

    def create_counter_widgets(self, func_connect, with_checkbox=True, default_checked=True):
        layout = QHBoxLayout()
        
        chk_use = None
        if with_checkbox:
            chk_use = QCheckBox("Use Counter")
            chk_use.setChecked(default_checked)
            chk_use.stateChanged.connect(func_connect)
        
        lbl_start = QLabel("Start:")
        sp_start = QSpinBox()
        sp_start.setRange(0, 999999)
        sp_start.setValue(1)
        sp_start.setMinimumWidth(80) 
        sp_start.valueChanged.connect(func_connect)
        
        lbl_digit = QLabel("Digits:")
        sp_digit = QSpinBox()
        sp_digit.setRange(1, 10)
        sp_digit.setValue(3)
        sp_digit.setMinimumWidth(80)
        sp_digit.valueChanged.connect(func_connect)
        
        if with_checkbox:
            chk_use.toggled.connect(lbl_start.setEnabled)
            chk_use.toggled.connect(sp_start.setEnabled)
            chk_use.toggled.connect(lbl_digit.setEnabled)
            chk_use.toggled.connect(sp_digit.setEnabled)
            lbl_start.setEnabled(default_checked)
            sp_start.setEnabled(default_checked)
            lbl_digit.setEnabled(default_checked)
            sp_digit.setEnabled(default_checked)
            layout.addWidget(chk_use)
            layout.addSpacing(20)

        layout.addWidget(lbl_start)
        layout.addWidget(sp_start)
        layout.addSpacing(15)
        layout.addWidget(lbl_digit)
        layout.addWidget(sp_digit)
        layout.addStretch()
        
        return layout, sp_start, sp_digit, chk_use

    def setup_tab_new(self):
        layout = QVBoxLayout(self.tab_new)
        layout.setContentsMargins(15, 20, 15, 15)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Name:"))
        self.txt_new_name = QLineEdit()
        self.txt_new_name.setPlaceholderText("Enter new name base")
        self.txt_new_name.textChanged.connect(self.update_preview)
        input_layout.addWidget(self.txt_new_name)
        
        layout.addLayout(input_layout)
        cnt_layout, self.sp_new_start, self.sp_new_digit, _ = \
            self.create_counter_widgets(self.update_preview, with_checkbox=False)
        layout.addLayout(cnt_layout)

    def setup_tab_replace(self):
        layout = QVBoxLayout(self.tab_replace)
        layout.setContentsMargins(15, 20, 15, 15)

        grid = QHBoxLayout()
        self.txt_find = QLineEdit()
        self.txt_find.setPlaceholderText("Text to find")
        self.txt_find.textChanged.connect(self.update_preview)
        
        self.txt_replace = QLineEdit()
        self.txt_replace.setPlaceholderText("Replacement text")
        self.txt_replace.textChanged.connect(self.update_preview)
        
        grid.addWidget(QLabel("Find:"))
        grid.addWidget(self.txt_find)
        grid.addWidget(QLabel("→ Replace:"))
        grid.addWidget(self.txt_replace)
        layout.addLayout(grid)
        
        cnt_layout, self.sp_rep_start, self.sp_rep_digit, self.chk_rep_counter = \
            self.create_counter_widgets(self.update_preview, with_checkbox=True, default_checked=False)
        layout.addLayout(cnt_layout)

    def setup_tab_prepend(self):
        layout = QVBoxLayout(self.tab_prepend)
        layout.setContentsMargins(15, 30, 15, 15)
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Prefix:"))
        self.txt_prepend = QLineEdit()
        self.txt_prepend.setPlaceholderText("Text to add at the beginning")
        self.txt_prepend.textChanged.connect(self.update_preview)
        h_layout.addWidget(self.txt_prepend)
        layout.addLayout(h_layout)
        layout.addStretch()

    def setup_tab_append(self):
        layout = QVBoxLayout(self.tab_append)
        layout.setContentsMargins(15, 30, 15, 15)
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Suffix:"))
        self.txt_append = QLineEdit()
        self.txt_append.setPlaceholderText("Text to add at the end")
        self.txt_append.textChanged.connect(self.update_preview)
        h_layout.addWidget(self.txt_append)
        layout.addLayout(h_layout)
        layout.addStretch()

    def setup_bottom_controls(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 5, 0, 0)
        
        self.lbl_status = QLabel("Ready")
        layout.addWidget(self.lbl_status)
        
        btn_run = QPushButton("Run Rename")
        btn_run.setMinimumHeight(50)
        btn_run.setCursor(Qt.PointingHandCursor)
        btn_run.setObjectName("RunButton") 
        btn_run.clicked.connect(self.run_rename)
        layout.addWidget(btn_run)
        
        self.layout.addLayout(layout)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        if self.is_dark_mode:
            self.btn_theme.setText("Switch to Light Mode")
        else:
            self.btn_theme.setText("Switch to Dark Mode")
        self.apply_theme()
        self.update_preview()

    def apply_theme(self):
        if self.is_dark_mode:
            # === DARK THEME ===
            style = """
                QMainWindow { background-color: #1e1e1e; }
                QWidget { color: #e0e0e0; font-size: 13px; }
                QFrame#OptionFrame { background-color: #252526; border: 1px solid #3e3e42; border-radius: 8px; }
                
                QHeaderView { background-color: #333337; }
                QHeaderView::section { 
                    background-color: #333337; 
                    color: #cccccc; 
                    border: none;
                    border-bottom: 1px solid #3e3e42;
                    border-right: 1px solid #3e3e42;
                    padding: 4px;
                }
                QHeaderView::section:vertical { border-right: 1px solid #3e3e42; border-bottom: 1px solid #3e3e42; }
                QTableCornerButton::section { background-color: #333337; border: none; }
                
                QTableWidget { 
                    background-color: #1e1e1e; 
                    alternate-background-color: #262626;
                    gridline-color: #1e1e1e; 
                    border: none;
                    color: #e0e0e0; 
                }
                QTableWidget::item { border: none; padding-left: 5px; }
                QTableWidget::item:selected { background-color: #094771; color: white; }

                /* Inputs */
                QLineEdit, QSpinBox, QComboBox { 
                    background-color: #3c3c3c; 
                    border: 1px solid #555555; 
                    border-radius: 4px; 
                    padding: 5px; 
                    color: #ffffff; 
                }
                QComboBox QAbstractItemView {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    selection-background-color: #094771;
                    border: 1px solid #555555;
                }
                QMenu { background-color: #252526; color: #ffffff; border: 1px solid #555555; }
                QMenu::item:selected { background-color: #094771; }

                /* Tabs & Buttons */
                QTabWidget::pane { border: 1px solid #3e3e42; background: #2d2d30; }
                QTabBar::tab { background: #2d2d30; color: #aaaaaa; padding: 8px 16px; border: 1px solid #3e3e42; }
                QTabBar::tab:selected { background: #3e3e42; color: #ffffff; font-weight: bold; border-bottom: none; }

                QPushButton, QToolButton { 
                    background-color: #3a3a3a; 
                    border: 1px solid #555555; 
                    border-radius: 5px; 
                    padding: 5px 15px; 
                    color: #ffffff; 
                }
                QPushButton:hover, QToolButton:hover { background-color: #4a4a4a; }
                
                /* [중요] 화살표 제거 (Dark) */
                QToolButton::menu-indicator { image: none; }
                
                QPushButton#RunButton { background-color: #2e7d32; color: white; border: none; font-weight: bold; font-size: 15px; }
                QPushButton#RunButton:hover { background-color: #388e3c; }
            """
        else:
            # === LIGHT THEME ===
            style = """
                QMainWindow { background-color: #f2f2f7; }
                QWidget { color: #000000; font-size: 13px; }
                QFrame#OptionFrame { background-color: #ffffff; border: 1px solid #d1d1d6; border-radius: 8px; }
                
                QHeaderView { background-color: #f2f2f7; }
                QHeaderView::section { 
                    background-color: #f2f2f7; 
                    color: #000000; 
                    border: none;
                    border-bottom: 1px solid #dcdcdc;
                    border-right: 1px solid #dcdcdc;
                    padding: 4px;
                }
                
                QTableWidget { 
                    background-color: #ffffff; 
                    alternate-background-color: #f7f7f9; 
                    gridline-color: #e5e5ea; 
                    border: 1px solid #d1d1d6; 
                    color: #000000; 
                }
                QTableWidget::item { border: none; padding-left: 5px; }
                QTableWidget::item:selected { background-color: #007aff; color: white; }
                
                QLineEdit, QSpinBox, QComboBox { 
                    background-color: #ffffff; 
                    border: 1px solid #cccccc; 
                    border-radius: 4px; 
                    padding: 5px; 
                    color: #000000; 
                }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    color: #000000;
                    selection-background-color: #007aff;
                }
                QMenu { background-color: #ffffff; color: #000000; border: 1px solid #cccccc; }
                QMenu::item:selected { background-color: #007aff; color: white; }

                QTabWidget::pane { border: 1px solid #e5e5ea; background: #ffffff; }
                QTabBar::tab { background: #f2f2f7; color: #000000; padding: 8px 16px; border: 1px solid #e5e5ea; }
                QTabBar::tab:selected { background: #ffffff; font-weight: bold; border-bottom: none; }

                QPushButton, QToolButton { background-color: #e5e5ea; border: 1px solid #d1d1d6; border-radius: 5px; padding: 5px 15px; color: #000000; }
                QPushButton:hover, QToolButton:hover { background-color: #d1d1d6; }
                
                /* [중요] 화살표 제거 (Light) - 여기를 추가했습니다 */
                QToolButton::menu-indicator { image: none; }
                
                QPushButton#RunButton { background-color: #34C759; color: white; border: none; font-weight: bold; font-size: 15px; }
                QPushButton#RunButton:hover { background-color: #2da84e; }
            """
        
        self.setStyleSheet(style)

    def handle_dropped_files(self, paths):
        added_count = 0
        for path in paths:
            if path not in self.items:
                self.items.append(path)
                added_count += 1
        if added_count > 0:
            self.refresh_table_list()

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files")
        if files:
            for f in files:
                if f not in self.items:
                    self.items.append(f)
            self.refresh_table_list()

    def add_folders(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if folder:
            if folder not in self.items:
                self.items.append(folder)
            self.refresh_table_list()

    def clear_list(self):
        self.items = []
        self.table.setRowCount(0)
        self.update_preview()

    def refresh_table_list(self):
        self.table.setRowCount(len(self.items))
        for row, path in enumerate(self.items):
            p = Path(path)
            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.name))
            self.table.setItem(row, 2, QTableWidgetItem(str(p)))
        self.update_preview()

    def get_counter_str(self, index, start_num, digits):
        num = start_num + index
        return str(num).zfill(digits)

    def update_preview(self):
        scope_idx = self.combo_scope.currentIndex()
        tab_idx = self.tabs.currentIndex()
        
        process_count = 0 
        
        if self.is_dark_mode:
            col_default = "#e0e0e0"
            col_change = "#4ec9b0"
            col_dim = "#666666"
        else:
            col_default = "#000000"
            col_change = "#007aff"
            col_dim = "#777777"

        for row in range(self.table.rowCount()):
            full_path = self.table.item(row, 2).text()
            p = Path(full_path)
            original_name = p.name
            
            is_dir = p.is_dir()
            is_file = p.is_file()
            
            target_name = ""  
            prefix_part = ""  
            suffix_part = ""  
            should_skip = False 

            if scope_idx == 0: 
                if is_dir: should_skip = True
                else:
                    target_name = p.stem
                    suffix_part = p.suffix
            elif scope_idx == 1:
                if is_file: should_skip = True
                else: target_name = p.name
            elif scope_idx == 2:
                if is_file:
                    target_name = p.stem
                    suffix_part = p.suffix
                else:
                    target_name = p.name
            elif scope_idx == 3:
                if is_dir: should_skip = True
                else: target_name = p.name
            elif scope_idx == 4:
                if is_dir: should_skip = True
                else:
                    prefix_part = p.stem 
                    target_name = p.suffix 
            
            for c in range(3):
                item = self.table.item(row, c)
                if item:
                    item.setForeground(QBrush(QColor(col_default)))
            
            if should_skip:
                item = QTableWidgetItem(original_name)
                item.setForeground(QBrush(QColor(col_dim)))
                self.table.setItem(row, 1, item)
                continue

            new_core_name = target_name
            
            if tab_idx == 0: # New Name
                base_txt = self.txt_new_name.text()
                start_n, digit_n = self.sp_new_start.value(), self.sp_new_digit.value()
                cnt_str = self.get_counter_str(process_count, start_n, digit_n)
                new_core_name = f"{base_txt}{cnt_str}"
            
            elif tab_idx == 1: # Find / Replace
                find_txt = self.txt_find.text()
                rep_txt = self.txt_replace.text()
                if find_txt and find_txt in target_name:
                    replacement = rep_txt
                    if self.chk_rep_counter.isChecked():
                        start_r, digit_r = self.sp_rep_start.value(), self.sp_rep_digit.value()
                        cnt_str = self.get_counter_str(process_count, start_r, digit_r)
                        replacement += cnt_str
                    new_core_name = target_name.replace(find_txt, replacement)
                else:
                    new_core_name = target_name
            
            elif tab_idx == 2: # Prepend
                prepend_txt = self.txt_prepend.text()
                new_core_name = f"{prepend_txt}{target_name}"
            
            elif tab_idx == 3: # Append
                append_txt = self.txt_append.text()
                new_core_name = f"{target_name}{append_txt}"

            final_name = f"{prefix_part}{new_core_name}{suffix_part}"
            
            item = QTableWidgetItem(final_name)
            if final_name != original_name:
                item.setForeground(QBrush(QColor(col_change)))
                item.setFont(item.font()) 
            else:
                item.setForeground(QBrush(QColor(col_default)))
                
            self.table.setItem(row, 1, item)
            process_count += 1
            
        self.lbl_status.setText(f"Ready to rename {process_count} items (out of {self.table.rowCount()})")

    def run_rename(self):
        count = 0
        errors = []
        for row in range(self.table.rowCount()):
            old_path_str = self.table.item(row, 2).text()
            new_name = self.table.item(row, 1).text()
            p_old = Path(old_path_str)
            if p_old.name == new_name:
                continue
            p_new = p_old.parent / new_name
            try:
                os.rename(p_old, p_new)
                self.items[row] = str(p_new)
                count += 1
            except Exception as e:
                errors.append(f"{p_old.name} -> {e}")
        self.refresh_table_list()
        
        if errors:
            msg = "Some files failed:\n" + "\n".join(errors[:5])
            if len(errors) > 5: msg += "\n..."
            dlg = StyledMessageBox("Completed with Errors", msg, icon_type="error", parent=self, is_dark=self.is_dark_mode)
            dlg.exec()
        else:
            msg = f"Successfully renamed {count} items."
            dlg = StyledMessageBox("Success", msg, icon_type="success", parent=self, is_dark=self.is_dark_mode)
            dlg.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartRenamer()
    window.show()
    sys.exit(app.exec())
