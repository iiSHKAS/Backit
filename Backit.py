import os
import time
import subprocess
import sys
import json
import urllib.request, urllib.error, urllib.parse
import base64

import webbrowser
from path_utils import resource_path
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QSize, QTimer, QThread
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient, QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog,
    QListWidget, QListWidgetItem, QLineEdit,
    QStackedWidget, QMessageBox, QInputDialog,
    QTreeWidget, QTreeWidgetItem, QStyle, QTreeWidgetItemIterator,
    QScrollArea, QFrame, QGridLayout, QMainWindow
)

# ================= CONFIG CONSTANTS =================
APP_NAME = "Backit"
DOCS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
CONFIG_DIR = os.path.join(DOCS_DIR, APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

# OAuth Constants (Device Flow)
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# ================= DESIGN SYSTEM (Exact Copy from setup_app.py) =================

class Config:
    DARK_BG = "#0f1115"
    PANEL_BG = "#11131a"
    CARD_BG = "#171a21"
    ACCENT = "#026ec1" # User requested darker blue
    TEXT = "#e6e9ef"
    SUBTEXT = "#96a0b5"
    BORDER = "#2a2f3a"
    GLOW = "#73d1ff"
    SUCCESS = "#10b981"
    ERROR = "#d32f2f" # Medium red, not too light/dark
    WARNING = "#f59e0b"
    GITHUB_CLIENT_ID = "Ov23liczPsB3h6AqZNoB"

class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._scroll_animation.setDuration(300)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._target_value = 0
    
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 80
        current = self.verticalScrollBar().value()
        max_val = self.verticalScrollBar().maximum()
        
        if self._scroll_animation.state() == QPropertyAnimation.State.Running:
            current = self._target_value
        
        if delta > 0:
            self._target_value = max(0, current - step)
        else:
            self._target_value = min(max_val, current + step)
        
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(self.verticalScrollBar().value())
        self._scroll_animation.setEndValue(self._target_value)
        self._scroll_animation.start()
        event.accept()

class AnimatedProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self._progress = 0.0
        self._animation = QPropertyAnimation(self, b"progress")
        self._animation.setDuration(800)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    
    def get_progress(self):
        return self._progress
    
    def set_progress(self, value):
        self._progress = value
        self.update()
    
    progress = QtCore.pyqtProperty(float, get_progress, set_progress)
    
    def set_target_progress(self, value):
        self._animation.stop()
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(value)
        self._animation.start()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1f2a"))
        if self._progress > 0:
            progress_width = int(self.width() * self._progress)
            gradient = QLinearGradient(0, 0, progress_width, 0)
            gradient.setColorAt(0.0, QColor("#3b82f6"))
            gradient.setColorAt(1.0, QColor("#60a5fa"))
            painter.fillRect(0, 0, progress_width, self.height(), gradient)

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(16)

    def rotate(self):
        self.angle = (self.angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(5, 5, -5, -5)
        
        pen = QPen(QColor(Config.ACCENT), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        painter.drawArc(rect, -self.angle * 16, 270 * 16)

class GitHubLoginWorker(QThread):
    success = QtCore.pyqtSignal(str, dict, bytes) # token, user_data, avatar_data
    failed = QtCore.pyqtSignal(str)
    
    def __init__(self, device_code, interval):
        super().__init__()
        self.device_code = device_code
        self.interval = interval
        self.running = True

    def run(self):
        while self.running:
            try:
                data = urllib.parse.urlencode({
                    'client_id': Config.GITHUB_CLIENT_ID,
                    'device_code': self.device_code,
                    'grant_type': GRANT_TYPE
                }).encode('utf-8')
                
                req = urllib.request.Request(TOKEN_URL, data=data, headers={'Accept': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    resp = json.loads(response.read().decode('utf-8'))
                
                if 'access_token' in resp:
                    token = resp['access_token']
                    
                    # Fetch User Data
                    req_user = urllib.request.Request("https://api.github.com/user", headers={
                        'Authorization': f'token {token}',
                        'Accept': 'application/json'
                    })
                    with urllib.request.urlopen(req_user) as response:
                        user_data = json.loads(response.read().decode('utf-8'))
                    
                    # Fetch Avatar
                    avatar_data = b""
                    img_url = user_data.get('avatar_url')
                    if img_url:
                        avatar_data = urllib.request.urlopen(img_url).read()
                        
                    self.success.emit(token, user_data, avatar_data)
                    break
                    
                elif 'error' in resp:
                    err = resp['error']
                    if err == 'authorization_pending':
                        pass
                    elif err == 'slow_down':
                        self.interval += 5
                    elif err == 'expired_token':
                        self.failed.emit("expired")
                        break
                    else:
                        self.failed.emit(err)
                        break
                
                time.sleep(self.interval)
                
            except Exception as e:
                self.failed.emit(str(e))
                break

    def stop(self):
        self.running = False
        self.wait()

class GitHubRepoLoaderWorker(QThread):
    success = QtCore.pyqtSignal(list)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, token):
        super().__init__()
        self.token = token

    def run(self):
        try:
            req = urllib.request.Request("https://api.github.com/user/repos?per_page=100&sort=updated")
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("User-Agent", "Backit")
            
            with urllib.request.urlopen(req) as resp:
                data = json.load(resp)
                self.success.emit(data)
                
        except Exception as e:
            self.failed.emit(str(e))




class ArrowAwareComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        down = resource_path("icons/Arrow-down.svg").replace("\\", "/")
        up = resource_path("icons/Arrow-up.svg").replace("\\", "/")
        tpl = (
            "QComboBox {\n"
            "    background-color: #0f1115;\n"
            "    color: #ffffff;\n"
            "    border: 1px solid #2a2f36;\n"
            "    border-radius: 8px;\n"
            "    padding: 5px 10px;\n"
            "    font-size: 13px;\n"
            "}\n"
            "QComboBox:hover { border: 1px solid #4a90e2; }\n"
            "QComboBox::drop-down {\n"
            "    subcontrol-origin: padding;\n"
            "    subcontrol-position: top right;\n"
            "    width: 25px;\n"
            "    border-left-width: 1px;\n"
            "    border-left-color: #2a2f36;\n"
            "    border-left-style: solid;\n"
            "    border-top-right-radius: 8px;\n"
            "    border-bottom-right-radius: 8px;\n"
            "}\n"
            "QComboBox::down-arrow { image: url(ARROW); width: 16px; height: 16px; }\n"
            "QComboBox QAbstractItemView { background-color: #1e2228; color: #ffffff; selection-background-color: #2a2f36; border: 1px solid #2a2f36; outline: none; padding: 6px; border-radius: 8px; margin-top: 3px; }\n"
            "QComboBox QAbstractItemView QScrollBar:vertical { border: none; background: #0f1115; width: 10px; margin: 0px 0px 0px 0px; }\n"
            "QComboBox QAbstractItemView QScrollBar::handle:vertical { background: #026ec1; min-height: 20px; border-radius: 5px; margin: 2px; }\n"
            "QComboBox QAbstractItemView QScrollBar::add-line:vertical { height: 0px; subcontrol-position: bottom; subcontrol-origin: margin; }\n"
            "QComboBox QAbstractItemView QScrollBar::sub-line:vertical { height: 0px; subcontrol-position: top; subcontrol-origin: margin; }\n"
            "QComboBox QAbstractItemView QScrollBar::add-page:vertical, QComboBox QAbstractItemView QScrollBar::sub-page:vertical { background: transparent; }\n"
        )
        self._style_down = tpl.replace("ARROW", down)
        self._style_up = tpl.replace("ARROW", up)
        self.setStyleSheet(self._style_down)
    def showPopup(self):
        self.setStyleSheet(self._style_up)
        super().showPopup()
    def hidePopup(self):
        super().hidePopup()
        self.setStyleSheet(self._style_down)

class ModernDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, title="Dialog"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.resize(400, 250)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Container
        self.container = QWidget()
        self.container.setStyleSheet(f"""
            background: {Config.CARD_BG};
            border: 1px solid {Config.BORDER};
            border-radius: 12px;
        """)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 20, 20, 20)
        self.layout.addWidget(self.container)
        
        # Title
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {Config.TEXT}; font-size: 18px; font-weight: bold; border: none;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.container_layout.addWidget(self.title_lbl)
        self.container_layout.addSpacing(20)
        
        # Content Area
        self.content_area = QVBoxLayout()
        self.container_layout.addLayout(self.content_area)
        self.container_layout.addSpacing(20)
        
        # Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)
        self.container_layout.addLayout(self.btn_layout)

    def add_widget(self, widget):
        self.content_area.addWidget(widget)

    def add_button(self, text, role="accept", color=Config.ACCENT):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        style = f"""
            QPushButton {{
                background: {color if role == "accept" else "transparent"};
                color: {"white" if role == "accept" else Config.SUBTEXT};
                border: {f'1px solid {Config.BORDER}' if role != "accept" else 'none'};
                border-radius: 8px;
                font-weight: 600;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: {color if role == "accept" else Config.BORDER};
                opacity: 0.9;
            }}
        """
        btn.setStyleSheet(style)
        if role == "accept":
            btn.clicked.connect(self.accept)
        else:
            btn.clicked.connect(self.reject)
        
        self.btn_layout.addWidget(btn)
        return btn

class CircularButton(QPushButton):
    def __init__(self, parent=None, size=40):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_pixmap = None
        self.setStyleSheet("border: none;")

    def set_icon(self, pixmap):
        self._icon_pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background circle
        path = QtGui.QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)
        
        if self._icon_pixmap:
             painter.drawPixmap(self.rect(), self._icon_pixmap)
        else:
            # Default gray placeholder
            painter.fillRect(self.rect(), QColor("#333"))
            # Initial letter? or Icon
            painter.setPen(QColor("#666"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(int(self.height()*0.5))
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "?")

class SetupTitleBar(QWidget):
    close_clicked = QtCore.pyqtSignal()
    
    def __init__(self, parent=None, title="Backit"):
        super().__init__(parent)
        self.parent_window = parent
        self.drag_position = QPoint()
        self.is_dragging = False
        self.setFixedHeight(50)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent;") # Transparent because container has color
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {Config.TEXT}; font-size: 16px; font-weight: 600; background: transparent;")
        layout.addWidget(self.title_label)
        layout.addStretch()
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(55, 50)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {Config.SUBTEXT}; font-size: 14px; border-top-right-radius: 12px; }}
            QPushButton:hover {{ background: #e81123; color: white; border-top-right-radius: 12px; }}
        """)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            # For QMainWindow, we need to map differently or just use global position diff
            self.drag_position = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.parent_window.move(event.globalPosition().toPoint() - self.drag_position)
    
    def mouseReleaseEvent(self, event):
        self.is_dragging = False

# ================= PAGES =================

class BasePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setup_ui()
    
    def setup_ui(self):
        pass

class PathSelectionPage(BasePage):
    path_selected = QtCore.pyqtSignal(str)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        icon = QLabel("📂")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("Select Project Folder")
        title.setStyleSheet(f"color: {Config.TEXT}; font-size: 28px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Choose the folder you want to manage backups for")
        subtitle.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        self.path_display = QLabel("No folder selected")
        self.path_display.setStyleSheet(f"""
            padding: 10px 20px;
            background: {Config.CARD_BG};
            border: 1px dashed {Config.BORDER};
            border-radius: 8px;
            color: {Config.ACCENT};
            font-family: Consolas;
        """)
        self.path_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.path_display)

        browse_btn = QPushButton("Browse Folder")
        browse_btn.setFixedSize(200, 44)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Config.ACCENT}; color: white; border: none; border-radius: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #4ab8ef; }}
        """)
        browse_btn.clicked.connect(self.browse)
        layout.addWidget(browse_btn)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self.path_display.setText(path)
            self.path_selected.emit(path)

class MenuPage(BasePage):
    action_selected = QtCore.pyqtSignal(str) # 'create' or 'restore'

    def setup_ui(self):
        layout = QHBoxLayout(self) # Horizontal for cards
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(30)

        # Create Backup Card
        self.create_card = self.create_action_card("➕", "Create Backup", "Save current state", "create")
        layout.addWidget(self.create_card)

        # Restore Backup Card
        self.restore_card = self.create_action_card("♻️", "Manage Backups", "Restore or Edit", "restore")
        layout.addWidget(self.restore_card)
        
        # GitHub Card
        self.github_card = self.create_action_card("☁️", "Push", "Upload to GitHub", "github")
        layout.addWidget(self.github_card)


    def create_action_card(self, icon, title, desc, action_key):
        btn = QPushButton()
        btn.setFixedSize(280, 180)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.action_selected.emit(action_key))
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Config.CARD_BG};
                border: 1px solid {Config.BORDER};
                border-radius: 16px;
                text-align: center;
            }}
            QPushButton:hover {{
                border-color: {Config.ACCENT};
                background: #1c2029;
            }}
        """)
        
        # Layout inside button
        layout = QVBoxLayout(btn)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size: 40px; border: none; background: transparent;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # Let click pass through
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {Config.TEXT}; font-size: 18px; font-weight: bold; border: none; background: transparent;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 13px; border: none; background: transparent;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        layout.addWidget(lbl_icon)
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_desc)
        
        return btn

class IgnorePage(BasePage):
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 0)
        
        lbl = QLabel("Select Files to Ignore")
        lbl.setStyleSheet(f"color: {Config.TEXT}; font-size: 22px; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        
        sub = QLabel("Uncheck files to include in backup")
        sub.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 13px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)
        
        # Stack for Tree vs Spinner
        self.stack = QStackedWidget()
        
        # Page 0: Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Project Files")
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {Config.CARD_BG};
                border: 1px solid {Config.BORDER};
                border-radius: 8px;
                color: {Config.TEXT};
            }}
            QHeaderView::section {{
                background: {Config.PANEL_BG};
                color: {Config.SUBTEXT};
                border: none;
                padding: 4px;
            }}
            QTreeWidget::item:hover {{ background: {Config.BORDER}; }}
            QTreeWidget::item:selected {{ background: {Config.ACCENT}; color: white; }}
            QTreeWidget::item:selected:active {{ background: {Config.ACCENT}; color: white; }}
            QTreeWidget::item:selected:!active {{ background: {Config.BORDER}; color: {Config.TEXT}; }}
        """)
        self.stack.addWidget(self.tree)
        
        # Page 1: Spinner
        self.spinner_container = QWidget()
        spin_layout = QVBoxLayout(self.spinner_container)
        spin_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spinner = LoadingSpinner()
        spin_layout.addWidget(self.spinner)
        self.stack.addWidget(self.spinner_container)
        
        layout.addWidget(self.stack)

    def show_loading(self):
        self.stack.setCurrentIndex(1)
        # self.spinner.show() # implicitly shown by stack
        
    def show_tree(self):
        self.stack.setCurrentIndex(0)

class CommitPage(BasePage):
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        lbl = QLabel("Name Your Backup")
        lbl.setStyleSheet(f"color: {Config.TEXT}; font-size: 24px; font-weight: bold;")
        layout.addWidget(lbl)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("e.g. Fixed navigation bug")
        self.input.setFixedSize(400, 50)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {Config.CARD_BG};
                color: {Config.TEXT};
                border: 1px solid {Config.BORDER};
                border-radius: 12px;
                padding: 10px;
                font-size: 16px;
            }}
            QLineEdit:focus {{ border-color: {Config.ACCENT}; }}
        """)
        layout.addWidget(self.input)

class GitHubSession:
    @staticmethod
    def get_file():
        return os.path.join(CONFIG_DIR, "github_session.json")

    @staticmethod
    def load():
        f = GitHubSession.get_file()
        if not os.path.exists(f): return {}
        try:
            with open(f, 'r') as fp: return json.load(fp)
        except: return {}

    @staticmethod
    def save(data):
        if not os.path.exists(CONFIG_DIR): os.makedirs(CONFIG_DIR)
        with open(GitHubSession.get_file(), 'w') as fp:
            json.dump(data, fp)

    @staticmethod
    def clear():
        f = GitHubSession.get_file()
        if os.path.exists(f): os.remove(f)

# Worker for Async Push
class GitPushWorker(QThread):
    finished = QtCore.pyqtSignal(bool, str) # success, message

    def __init__(self, project_path, auth_url, commit_hash):
        super().__init__()
        self.project_path = project_path
        self.auth_url = auth_url
        self.commit_hash = commit_hash

    def run(self):
        try:
            # Helper to run command synchronously within thread
            def run_cmd(cmd):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                return subprocess.run(
                    cmd, cwd=self.project_path, startupinfo=startupinfo,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

            # 1. Set Remote
            run_cmd("git remote remove origin")
            res_remote = run_cmd(f"git remote add origin {self.auth_url}")
            if res_remote.returncode != 0:
                 self.finished.emit(False, f"Failed to add remote: {res_remote.stderr}")
                 return

            # 2. Push
            # 2. Safer Push (Merge Context)
            # Create a temp branch to merge remote changes into, avoiding file loss
            temp_branch = f"temp_push_{int(time.time())}"
            run_cmd(f"git branch -D {temp_branch}") # Cleanup just in case
            run_cmd(f"git checkout -b {temp_branch} {self.commit_hash}")

            # Pull remote master (if exists) into this temp branch
            # We use -X ours to prioritize our backup files in conflict, but keep remote unique files (like README)
            run_cmd("git fetch origin master")
            # attempt merge
            run_cmd("git merge origin/master --allow-unrelated-histories -X ours --no-edit")
            
            # Push the result to master
            res_push = run_cmd(f"git push origin {temp_branch}:refs/heads/master")
            
            # Switch back and clean up
            current_branch_res = run_cmd("git rev-parse --abbrev-ref HEAD")
            # If we are detached (likely), we just stay detached or move to a known state? 
            # We created temp_branch from a detached hash usually.
            # Let's check out the original commit hash to be safe/clean or just stay on temp? 
            # Actually, we should leave the repo in a clean state.
            run_cmd(f"git checkout {self.commit_hash}") 
            run_cmd(f"git branch -D {temp_branch}")

            if res_push.returncode == 0:
                self.finished.emit(True, "Savepoint pushed successfully!")
            else:
                self.finished.emit(False, res_push.stderr)
                
        except Exception as e:
            self.finished.emit(False, str(e))

# Common Base for GitHub Pages to share style
class GitHubBasePage(BasePage):
    back_clicked = QtCore.pyqtSignal()
    
    def setup_common_layout(self):
        # Main Layout (Fill screen)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        
        # --- Top Left Back Button (Text Only) ---
        top_layout = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setFixedSize(80, 40)
        self.btn_back.setStyleSheet(f"""
            QPushButton {{
                background: {Config.PANEL_BG};
                color: {Config.SUBTEXT};
                border: 1px solid {Config.BORDER};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ 
                background: {Config.BORDER}; 
                color: {Config.TEXT}; 
            }}
        """)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        top_layout.addWidget(self.btn_back)
        top_layout.addStretch()
        self.main_layout.addLayout(top_layout)
        
        self.main_layout.addStretch()
        
        # --- Center Content Container ---
        self.card = QWidget()
        self.card.setFixedWidth(520)
        self.card.setStyleSheet("background: transparent; border: none;")
        
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(25)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addStretch()

class GitHubLoginPage(GitHubBasePage):
    login_success = QtCore.pyqtSignal()
    logout_clicked = QtCore.pyqtSignal()

    def setup_ui(self):
        self.setup_common_layout()
        
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")
        self.card_layout.addWidget(self.stack)

        # --- VIEW 1: Login (Device Flow) ---
        self.view_login = QWidget()
        l = QVBoxLayout(self.view_login)
        l.setContentsMargins(0,0,0,0); l.setSpacing(20); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon = QLabel("☁️")
        icon.setStyleSheet("font-size: 72px; border: none;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(icon)
        
        title = QLabel("Connect to GitHub")
        title.setStyleSheet(f"color: {Config.TEXT}; font-size: 26px; font-weight: 700; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)
        
        sub = QLabel("Sync your savepoints with the cloud.\nSimple, secure, and fast.")
        sub.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 15px; border: none;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(sub)
        
        # Code Area
        self.code_container = QWidget()
        self.code_container.hide()
        self.code_container.setStyleSheet("background: transparent; border: none;")
        cl = QVBoxLayout(self.code_container); cl.setContentsMargins(0, 10, 0, 10); cl.setSpacing(10)
        
        self.lbl_user_code = QLabel("----")
        self.lbl_user_code.setStyleSheet(f"""
            background: #151921; color: {Config.ACCENT}; font-family: Consolas, monospace;
            font-size: 36px; font-weight: bold; border-radius: 12px; padding: 15px 40px; letter-spacing: 4px;
        """)
        self.lbl_user_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_user_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cl.addWidget(self.lbl_user_code, 0, Qt.AlignmentFlag.AlignCenter)
        
        copy_hint = QLabel("Code copied to clipboard"); copy_hint.setStyleSheet(f"color: {Config.SUCCESS}; font-size: 13px; font-weight: 600; border: none;"); copy_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(copy_hint)
        l.addWidget(self.code_container)
        
        self.btn_login = QPushButton("Log in with GitHub")
        self.btn_login.setFixedSize(260, 55)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(f"""
            QPushButton {{ background: {Config.TEXT}; color: {Config.DARK_BG}; border: none; border-radius: 27px; font-weight: bold; font-size: 17px; }}
            QPushButton:hover {{ background: white; }}
            QPushButton:disabled {{ background: {Config.BORDER}; color: {Config.SUBTEXT}; }}
        """)
        l.addWidget(self.btn_login, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.stack.addWidget(self.view_login)

        # --- VIEW 2: Profile (Logged In) ---
        self.view_profile = QWidget()
        p = QVBoxLayout(self.view_profile)
        p.setContentsMargins(0,0,0,0); p.setSpacing(20); p.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(120, 120)
        self.lbl_avatar.setStyleSheet(f"background: {Config.PANEL_BG}; border-radius: 60px; border: 2px solid {Config.BORDER};")
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(self.lbl_avatar, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_name = QLabel("User")
        self.lbl_name.setStyleSheet(f"color: {Config.TEXT}; font-size: 24px; font-weight: bold; border: none;")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(self.lbl_name)
        
        self.lbl_login = QLabel("@handle")
        self.lbl_login.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 16px; border: none;")
        self.lbl_login.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(self.lbl_login)
        
        p.addSpacing(20)
        
        self.btn_logout = QPushButton("Log Out")
        self.btn_logout.setFixedSize(200, 45)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setStyleSheet(f"""
            QPushButton {{ background: {Config.CARD_BG}; color: {Config.ERROR}; border: 1px solid {Config.BORDER}; border-radius: 22px; font-weight: 600; }}
            QPushButton:hover {{ border-color: {Config.ERROR}; background: {Config.PANEL_BG}; }}
        """)
        self.btn_logout.clicked.connect(self.logout_clicked.emit)
        p.addWidget(self.btn_logout, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.stack.addWidget(self.view_profile)

    def show_code(self, code, user_code, verification_uri):
        self.code_container.show()
        self.lbl_user_code.setText(user_code)
        self.btn_login.setEnabled(False)
        self.btn_login.setText("Waiting for authorization...")
        
        cb = QApplication.clipboard()
        cb.setText(user_code)
        # Delay browser opening by 500ms so user can see what's happening
        QTimer.singleShot(500, lambda: webbrowser.open(verification_uri))

    def show_profile(self, name, login, avatar_pixmap):
        self.lbl_name.setText(name if name else login)
        self.lbl_login.setText(f"@{login}")
        if avatar_pixmap:
            self.lbl_avatar.setPixmap(avatar_pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            # Masking for circle
            mask = QtGui.QBitmap(120, 120)
            mask.fill(Qt.GlobalColor.color0)
            painter = QPainter(mask)
            painter.setBrush(Qt.GlobalColor.color1)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 120, 120)
            painter.end()
            self.lbl_avatar.setMask(mask)
        else:
            self.lbl_avatar.setText(login[0].upper())
        self.stack.setCurrentIndex(1)

    def show_login_ui(self):
        self.stack.setCurrentIndex(0)
        self.code_container.hide()
        self.btn_login.setEnabled(True)
        self.btn_login.setText("Log in with GitHub")

class GitHubPushPage(GitHubBasePage):
    refresh_repos_clicked = QtCore.pyqtSignal()
    push_clicked = QtCore.pyqtSignal()
    login_request_clicked = QtCore.pyqtSignal() # Redirect to Login Page

    def setup_ui(self):
        self.setup_common_layout()
        
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")
        self.card_layout.addWidget(self.stack)
        
        # --- VIEW 1. Login Required ---
        self.view_req = QWidget()
        r = QVBoxLayout(self.view_req)
        r.setContentsMargins(0,0,0,0); r.setSpacing(15); r.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        r_title = QLabel("Authentication Required")
        r_title.setStyleSheet(f"color: {Config.TEXT}; font-size: 22px; font-weight: bold; border: none;")
        r_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r.addWidget(r_title)
        
        r_sub = QLabel("You must be logged in to push savepoints.")
        r_sub.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 15px; border: none;")
        r_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r.addWidget(r_sub)
        
        r.addSpacing(10)
        
        self.btn_go_login = QPushButton("Login to GitHub")
        self.btn_go_login.setFixedSize(200, 50)
        self.btn_go_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go_login.setStyleSheet(f"""
            QPushButton {{ background: {Config.ACCENT}; color: white; border: none; border-radius: 25px; font-weight: bold; font-size: 16px; }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self.btn_go_login.clicked.connect(self.login_request_clicked.emit)
        r.addWidget(self.btn_go_login, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.stack.addWidget(self.view_req)
        
        # --- VIEW 2. Push Form ---
        self.view_push = QWidget()
        p = QVBoxLayout(self.view_push)
        p.setContentsMargins(0,0,0,0); p.setSpacing(20); p.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        p_title = QLabel("Push to GitHub")
        p_title.setStyleSheet(f"color: {Config.TEXT}; font-size: 26px; font-weight: 700; border: none;")
        p_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(p_title)
        
        p_sub = QLabel("Select a repository and a savepoint.")
        p_sub.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 15px; border: none;")
        p_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(p_sub)
        
        p.addSpacing(10)
        
        # Custom Style is now inside ArrowAwareComboBox
        
        r_box = QVBoxLayout(); r_box.setSpacing(5)
        r_lbl = QLabel("Repository"); r_lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 12px; font-weight: bold; text-transform: uppercase; border: none;")
        r_box.addWidget(r_lbl)
        
        r_row = QHBoxLayout()
        self.repo_combo = ArrowAwareComboBox()
        self.repo_combo.setFixedHeight(45)
        r_row.addWidget(self.repo_combo, 1)
        
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(45, 45)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(f"QPushButton {{ background: {Config.BORDER}; border-radius: 10px; color: {Config.TEXT}; border: none; }} QPushButton:hover {{ background: {Config.ACCENT}; color: white; }}")
        self.btn_refresh.clicked.connect(self.refresh_repos_clicked.emit)
        r_row.addWidget(self.btn_refresh)
        r_box.addLayout(r_row)
        p.addLayout(r_box)
        
        c_box = QVBoxLayout(); c_box.setSpacing(5)
        c_lbl = QLabel("Savepoint"); c_lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 12px; font-weight: bold; text-transform: uppercase; border: none;")
        c_box.addWidget(c_lbl)
        
        self.commit_combo = ArrowAwareComboBox()
        self.commit_combo.setFixedHeight(45)
        c_box.addWidget(self.commit_combo)
        p.addLayout(c_box)
        
        p.addSpacing(20)
        
        self.btn_push = QPushButton("Push Savepoint")
        self.btn_push.setFixedSize(260, 55)
        self.btn_push.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_push.setStyleSheet(f"""
            QPushButton {{ background: {Config.ACCENT}; color: white; border: none; border-radius: 27px; font-weight: bold; font-size: 16px; }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self.btn_push.clicked.connect(self.push_clicked.emit)
        p.addWidget(self.btn_push, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.stack.addWidget(self.view_push)
        
    def set_authenticated(self, is_auth):
        self.stack.setCurrentIndex(1 if is_auth else 0)

class RestoreListPage(BasePage):
    commit_selected = QtCore.pyqtSignal(object)
    view_requested = QtCore.pyqtSignal()
    rename_requested = QtCore.pyqtSignal()
    delete_requested = QtCore.pyqtSignal()
    purge_requested = QtCore.pyqtSignal()
    push_requested = QtCore.pyqtSignal()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        
        lbl = QLabel("Select a Backup")
        lbl.setStyleSheet(f"color: {Config.TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(lbl)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {Config.CARD_BG};
                border: 1px solid {Config.BORDER};
                border-radius: 8px;
                color: {Config.TEXT};
                font-size: 14px;
                outline: none;
                border: none;
            }}
            QListWidget::item {{ padding: 12px; border-bottom: 1px solid {Config.BORDER}; }}
            QListWidget::item:selected {{ background: {Config.ACCENT}; color: {Config.DARK_BG}; font-weight: bold; border-radius: 8px; }}
        """)
        self.list_widget.itemClicked.connect(self.commit_selected.emit)
        self.list_widget.itemDoubleClicked.connect(self.view_requested.emit)
        layout.addWidget(self.list_widget)

        # Actions Row
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        
        self.btn_view = self.create_btn("📂 View", Config.ACCENT)
        self.btn_view.clicked.connect(self.view_requested.emit)
        

        self.btn_rename = self.create_btn("✏️ Rename", Config.ACCENT)
        self.btn_rename.clicked.connect(self.rename_requested.emit)
        
        self.btn_delete = self.create_btn("🗑️ Delete", Config.ERROR)
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        
        self.btn_initial = self.create_btn("✨ Purge", Config.WARNING)
        self.btn_initial.clicked.connect(self.purge_requested.emit)
        
        actions_layout.addWidget(self.btn_view)

        actions_layout.addWidget(self.btn_rename)
        actions_layout.addWidget(self.btn_delete)
        actions_layout.addWidget(self.btn_initial)
        
        layout.addLayout(actions_layout)

    def create_btn(self, text, color):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Config.CARD_BG};
                color: {color};
                border: 1px solid {Config.BORDER};
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {color};
                background: {Config.PANEL_BG};
            }}
        """)
        return btn

class RestoreFilesPage(BasePage):
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 0)
        
        lbl = QLabel("Select Files to Restore")
        lbl.setStyleSheet(f"color: {Config.TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(lbl)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Backup Content")
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {Config.CARD_BG};
                border: 1px solid {Config.BORDER};
                border-radius: 8px;
                color: {Config.TEXT};
            }}
             QHeaderView::section {{
                background: {Config.PANEL_BG};
                color: {Config.SUBTEXT};
                border: none;
                padding: 4px;
            }}
            QTreeWidget::item:hover {{ background: {Config.BORDER}; }}
            QTreeWidget::item:selected {{ background: {Config.ACCENT}; color: white; }}
            QTreeWidget::item:selected:active {{ background: {Config.ACCENT}; color: white; }}
            QTreeWidget::item:selected:!active {{ background: {Config.BORDER}; color: {Config.TEXT}; }}
        """)
        layout.addWidget(self.tree)

# ================= MAIN WINDOW =================

class SetupAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1000, 700)
        
        # Data State
        self.project_path = ""
        self.selected_commit_hash = ""
        self.ignore_items = []
        self.previous_page_index = 0
        self.pre_ignored_items = set()
        
        self.setup_ui()
        self.center_window()
        self.load_settings()
        
    def center_window(self):
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 1000) // 2, (screen.height() - 700) // 2)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container (Rounded, Dark BG)
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet(f"""
            QWidget#container {{
                background: {Config.DARK_BG};
                border: 1px solid {Config.BORDER};
                border-radius: 12px;
            }}
            * {{ outline: none; }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Title Bar
        self.title_bar = SetupTitleBar(self)
        self.title_bar.close_clicked.connect(self.close)
        container_layout.addWidget(self.title_bar)
        
        # Progress Bar
        self.progress_bar = AnimatedProgressBar()
        container_layout.addWidget(self.progress_bar)
        
        # Pages Stack
        self.stacked = QStackedWidget()
        
        self.page_path = PathSelectionPage()
        self.page_menu = MenuPage()
        self.page_ignore = IgnorePage()
        self.page_commit = CommitPage()
        self.page_restore_list = RestoreListPage()
        self.page_restore_files = RestoreFilesPage()
        self.page_github_login = GitHubLoginPage()
        self.page_github_push = GitHubPushPage()
        
        self.stacked.addWidget(self.page_path)       # 0
        self.stacked.addWidget(self.page_menu)       # 1
        self.stacked.addWidget(self.page_ignore)     # 2
        self.stacked.addWidget(self.page_commit)     # 3
        self.stacked.addWidget(self.page_restore_list) # 4
        self.stacked.addWidget(self.page_restore_files)# 5
        self.stacked.addWidget(self.page_github_login) # 6
        self.stacked.addWidget(self.page_github_push)  # 7
        
        # Signals
        self.page_path.path_selected.connect(self.on_path_selected)
        self.page_menu.action_selected.connect(self.on_menu_action)
        self.page_restore_list.view_requested.connect(lambda: self.on_restore_commit_selected(self.page_restore_list.list_widget.currentItem()))
        self.page_restore_list.rename_requested.connect(self.on_rename_commit)
        self.page_restore_list.delete_requested.connect(self.on_delete_commit)
        self.page_restore_list.purge_requested.connect(self.on_purge_commit)
        self.page_restore_list.push_requested.connect(self.on_push_commit)
        self.page_commit.input.returnPressed.connect(self.perform_commit)
        self.page_ignore.tree.itemExpanded.connect(self.on_tree_item_expanded)
         
        # GitHub Login Signals

        
        # Login Page
        self.page_github_login.back_clicked.connect(self.go_back)
        self.page_github_login.logout_clicked.connect(self.logout_github)
        # self.page_github_login.login_clicked is missing? I'll use the button directly if I have to.
        self.page_github_login.btn_login.clicked.connect(self.start_oauth_flow) 
        
        # Push Page
        self.page_github_push.back_clicked.connect(self.go_back)
        self.page_github_push.refresh_repos_clicked.connect(self.load_github_repos)
        self.page_github_push.push_clicked.connect(self.on_github_push_clicked)
        self.page_github_push.login_request_clicked.connect(self.on_login_requested_from_push)
        
        # Global Page Change Handler
        self.stacked.currentChanged.connect(self.on_page_changed)

        container_layout.addWidget(self.stacked, 1)
        
        # Navigation Bar
        self.nav_container = QWidget()
        nav_layout = QHBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(50, 15, 50, 25)
        
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedSize(120, 44)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Config.SUBTEXT}; border: 1.5px solid {Config.BORDER}; border-radius: 12px; font-weight: 600; }}
            QPushButton:hover {{ border-color: {Config.ACCENT}; color: {Config.TEXT}; }}
        """)
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.hide()
        
        self.next_btn = QPushButton("Continue")
        self.next_btn.setFixedSize(140, 44)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(f"""
            QPushButton {{ background: {Config.ACCENT}; color: white; border: none; border-radius: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: #4ab8ef; }}
            QPushButton:disabled {{ background: {Config.BORDER}; color: {Config.SUBTEXT}; }}
        """)
        self.next_btn.clicked.connect(self.go_next)
        
        nav_layout.addWidget(self.back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)
        
        container_layout.addWidget(self.nav_container)
        
        # --- Avatar / User Profile (Top Right) ---
        # Layout: [3px Spacer, Avatar, 15px Spacer, Stretch, Title, Stretch, Close]
        
        self.title_bar.layout().insertSpacing(0, 3)
        
        self.avatar_btn = CircularButton(self, size=38) # Slightly smaller than bar height (50)
        self.avatar_btn.clicked.connect(self.on_avatar_clicked)
        self.title_bar.layout().insertWidget(1, self.avatar_btn)
        
        self.title_bar.layout().insertSpacing(2, 15)
        
        self.avatar_btn.show()

        main_layout.addWidget(container)
        
        # Init
        self.next_btn.setEnabled(False) 

    # ================= LOGIC & FLOW =================

    def on_page_changed(self, index):
        """
        The Source of Truth for Navigation Visibility.
        Index 6 is GitHub Login -> STRICTLY HIDE Bottom Nav.
        Index 7 is GitHub Push -> STRICTLY HIDE Bottom Nav.
        """
        if index == 6 or index == 7:
            self.nav_container.hide()
            self.nav_container.setVisible(False)
            self.back_btn.hide()
            self.next_btn.hide()
        else:
            self.nav_container.show()
            self.nav_container.setVisible(True)
            # ... (logic for other pages handles buttons)

    def on_avatar_clicked(self):
        # Go to Login/Profile Page
        self.previous_page_index = self.stacked.currentIndex()
        self.stacked.setCurrentIndex(6)
        
    def on_login_requested_from_push(self):
        self.redirect_to_push = True
        self.previous_page_index = self.stacked.currentIndex()
        self.stacked.setCurrentIndex(6) # Go to Login
        self.start_oauth_flow() # Auto-click login

    def load_settings(self):
        # Load local settings
        if os.path.exists(CONFIG_FILE): 
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    last_path = data.get('last_path', '')
                    if last_path and os.path.exists(last_path):
                        self.project_path = last_path
                        self.page_path.path_display.setText(last_path)
                        self.page_path.path_selected.emit(last_path)
            except Exception as e:
                print(f"Error loading settings: {e}")

        # Load GitHub Session
        self.github_session = GitHubSession.load()
        token = self.github_session.get('access_token', '')
        self.github_token = token
        
        is_auth = bool(token)
        self.page_github_push.set_authenticated(is_auth)
        
        if is_auth:
            self.page_github_login.show_profile(
                self.github_session.get('name', ''), 
                self.github_session.get('login', ''), 
                None # Avatar loaded async
            )
            self.fetch_user_avatar()
        else:
             self.page_github_login.show_login_ui()

    def save_settings(self, path):
        try:
            if not os.path.exists(CONFIG_DIR): os.makedirs(CONFIG_DIR)
            data = {"last_path": path} # Token is now in session file
            with open(CONFIG_FILE, 'w') as f: json.dump(data, f)
        except Exception as e: print(f"Error saving settings: {e}")

    # --- GitHub Actions ---
    def start_oauth_flow(self):
        try:
            # 1. Request Device Code
            data = urllib.parse.urlencode({'client_id': Config.GITHUB_CLIENT_ID, 'scope': 'repo user'}).encode('utf-8')
            req = urllib.request.Request(DEVICE_CODE_URL, data=data, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(req) as response:
                resp = json.loads(response.read().decode('utf-8'))
                
            self.device_code = resp['device_code']
            self.user_code = resp['user_code']
            self.verification_uri = resp['verification_uri']
            self.interval = resp['interval']
            
            # Show in Login Page
            self.page_github_login.show_code(self.device_code, self.user_code, self.verification_uri)
            

            
            # Start Worker
            self.login_worker = GitHubLoginWorker(self.device_code, self.interval)
            self.login_worker.success.connect(self.on_login_worker_success)
            self.login_worker.failed.connect(self.on_login_worker_failed)
            self.login_worker.start()
            
        except Exception as e:
            self.show_modern_alert("Connection Error", str(e), is_error=True)
            self.page_github_login.btn_login.setEnabled(True)
            self.page_github_login.btn_login.setText("Log in with GitHub")

    def on_login_worker_success(self, token, user_data, avatar_data):
        self.github_token = token
        
        # Save Session
        session_data = {
            'access_token': token,
            'login': user_data.get('login'),
            'name': user_data.get('name'),
            'avatar_url': user_data.get('avatar_url')
        }
        GitHubSession.save(session_data)
        
        # Update UI
        if avatar_data:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(avatar_data)
            self.page_github_login.show_profile(user_data.get('name'), user_data.get('login'), pixmap)
            self.avatar_btn.set_icon(pixmap)
        else:
            self.page_github_login.show_profile(user_data.get('name'), user_data.get('login'), None)
            
        self.page_github_push.set_authenticated(True)
        
        # Auto-load Repos after fresh login
        self.load_github_repos()

        # Check Redirect
        if getattr(self, 'redirect_to_push', False):
            self.redirect_to_push = False
            self.stacked.setCurrentIndex(7) # Go to Push

    def on_login_worker_failed(self, error):
        if error == "expired":
            self.show_modern_alert("Expired", "Login session expired. Try again.", is_error=True)
        else:
            self.show_modern_alert("Error", f"Login failed: {error}", is_error=True)
        self.page_github_login.show_login_ui()

    def fetch_user_avatar(self):
        if not self.github_token: return
        try:
            req = urllib.request.Request("https://api.github.com/user", headers={
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/json'
            })
            with urllib.request.urlopen(req) as response:
                user_data = json.loads(response.read().decode('utf-8'))
            
            # Save Session
            session_data = {
                'access_token': self.github_token,
                'login': user_data.get('login'),
                'name': user_data.get('name'),
                'avatar_url': user_data.get('avatar_url')
            }
            GitHubSession.save(session_data)
            
            # Load Avatar Image
            img_url = user_data.get('avatar_url')
            if img_url:
                data = urllib.request.urlopen(img_url).read()
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(data)
                
                self.page_github_login.show_profile(user_data.get('name'), user_data.get('login'), pixmap)
                
                self.page_github_login.show_profile(user_data.get('name'), user_data.get('login'), pixmap)
                
                # Update Title Bar Avatar
                self.avatar_btn.set_icon(pixmap)
                
        except Exception as e:
            print(f"Fetch user error: {e}")

    def logout_github(self):
        self.github_token = ""
        if hasattr(self, 'poll_timer'): self.poll_timer.stop()
        GitHubSession.clear()
        
        self.page_github_login.show_login_ui()
        self.page_github_push.set_authenticated(False)
    def logout_github(self):
        self.github_token = ""
        if hasattr(self, 'login_worker'): self.login_worker.stop()
        GitHubSession.clear()
        
        self.page_github_login.show_login_ui()
        self.page_github_push.set_authenticated(False)
        self.avatar_btn.set_icon(None) # Clear title bar avatar
        self.show_modern_alert("Logged Out", "You have been disconnected from GitHub.")

    def on_github_push_clicked(self):
        repo_url = self.page_github_push.repo_combo.currentData()
        commit_hash = self.page_github_push.commit_combo.currentData()
        
        if not repo_url or not commit_hash:
            return self.show_modern_alert("Error", "Please select a repository and a savepoint.")
            
        token = getattr(self, 'github_token', '')
        if "@" not in repo_url and token:
             auth_url = repo_url.replace("https://", f"https://{token}@")
        else:
             auth_url = repo_url
        
        # --- Progress Dialog ---
        self.progress_dlg = ModernDialog(self, "Pushing to Cloud")
        
        layout = QVBoxLayout()
        spinner = LoadingSpinner(self.progress_dlg)
        layout.addWidget(spinner, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        
        lbl = QLabel("Syncing with GitHub...\nThis may take a moment.")
        lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        
        container = QWidget()
        container.setLayout(layout)
        self.progress_dlg.add_widget(container)
        
        # Remove buttons for modal progress
        # We can't easily remove buttons from ModernDialog once added in init? 
        # ModernDialog adds buttons via add_button. If we don't call add_button, it has none.
        # But we need to make sure user can't close it easily if we want to block interactions?
        # Actually, let's just not add buttons.
        
        # Start Worker
        self.push_worker = GitPushWorker(self.project_path, auth_url, commit_hash)
        self.push_worker.finished.connect(self.on_push_finished)
        self.push_worker.start()
        
        self.progress_dlg.exec()

    def on_push_finished(self, success, message):
        # Close progress dialog
        if hasattr(self, 'progress_dlg'):
            self.progress_dlg.accept() # Close
            
        if success:
            self.show_modern_alert("Success", message)
        else:
            self.show_modern_alert("Error", message, is_error=True)

    def load_github_repos(self):
        token = getattr(self, 'github_token', '')
        if not token: return
        
        self.page_github_push.btn_refresh.setEnabled(False)
        
        if hasattr(self, 'repo_worker') and self.repo_worker.isRunning():
             self.repo_worker.terminate()
             
        self.repo_worker = GitHubRepoLoaderWorker(token)
        self.repo_worker.success.connect(self.on_repo_worker_success)
        self.repo_worker.failed.connect(self.on_repo_worker_failed)
        self.repo_worker.start()

    def on_repo_worker_success(self, data):
        self.page_github_push.repo_combo.clear()
        for repo in data:
            self.page_github_push.repo_combo.addItem(repo['full_name'], repo['clone_url'])
        self.page_github_push.btn_refresh.setEnabled(True)

    def on_repo_worker_failed(self, error):
        self.show_modern_alert("Error", f"Failed to load repos: {error}", is_error=True)
        self.page_github_push.btn_refresh.setEnabled(True)


    def run_git_cmd(self, cmd):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        return subprocess.run(
            cmd,
            cwd=self.project_path,
            startupinfo=startupinfo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )


    def on_path_selected(self, path):
        self.project_path = path
        self.save_settings(path)
        self.next_btn.setEnabled(True)
        # Check git status / auto-fix
        if os.path.exists(os.path.join(path, ".git")):
            if os.path.exists(os.path.join(path, ".git", "rebase-merge")):
                self.run_git_cmd("git rebase --abort")



    def on_menu_action(self, action):
        if action == "create":
            # Smart Gitignore Check
            gitignore_path = os.path.join(self.project_path, ".gitignore")
            skip_ignore_page = False
            
            if os.path.exists(gitignore_path):
                # Use Modern Dialog
                should_update = self.show_modern_choice(
                    "Update Ignore List?",
                    "A .gitignore file already exists.\nDo you want to update it?",
                    yes_text="Edit List",
                    no_text="Keep Existing"
                )
                
                if not should_update:
                    skip_ignore_page = True
                else:
                    self.load_existing_gitignore()
            else:
                 self.pre_ignored_items = set()

            if skip_ignore_page:
                 # Go directly to Commit Page (3)
                 self.stacked.setCurrentIndex(3)
                 self.nav_container.show()
                 self.back_btn.show()
                 self.next_btn.show()
                 self.next_btn.setText("Save Backup")
                 self.progress_bar.set_target_progress(0.8)
                 # Clear ignore items so we don't overwrite .gitignore with empty or old data
                 self.ignore_items = []
            else:
                # Go to Ignore Page (2)
                self.stacked.setCurrentIndex(2)
                self.nav_container.show()
                self.back_btn.show()
                self.next_btn.show()
                self.next_btn.setText("Continue")
                self.progress_bar.set_target_progress(0.4)
                QTimer.singleShot(100, self.start_ignore_tree_load)
        elif action == "restore":
            self.load_commits()
            self.stacked.setCurrentIndex(4)
            self.nav_container.show()
            self.back_btn.show()
            self.next_btn.hide() # Rely on list buttons
            self.progress_bar.set_target_progress(0.4)
        elif action == "github":
            self.load_commits() # Load savepoints for combo box
            # Also load repos if authenticated
            if getattr(self, 'github_token', ''):
                self.load_github_repos()
            
            self.stacked.setCurrentIndex(7) # Go to Push Page (idx 7)
            self.nav_container.hide() # STRICTLY HIDE
            # self.refresh_github_status() # Handled by load_settings or manual refresh now

    def go_next(self):
        idx = self.stacked.currentIndex()
        if idx == 0: # Path -> Menu
            self.stacked.setCurrentIndex(1)
            self.nav_container.show()
            self.back_btn.show()
            self.next_btn.hide() # Menu has its own buttons
            self.progress_bar.set_target_progress(0.2)
        elif idx == 2: # Ignore -> Commit
            if self.collect_ignored():
                self.stacked.setCurrentIndex(3)
                self.back_btn.show()
                self.nav_container.show()
                self.next_btn.show()
                self.next_btn.setText("Save Backup")
                self.progress_bar.set_target_progress(0.8)
        elif idx == 3: # Commit -> Done (Action)
            self.perform_commit()
        elif idx == 5: # Restore Files -> Done (Action)
            self.perform_restore_files()

    def go_back(self):
        idx = self.stacked.currentIndex()
        
        # GitHub Login (6) -> Previous Page (User Request)
        if idx == 6:
            target = self.previous_page_index
            self.stacked.setCurrentIndex(target)
            
            # Restore UI State for target page
            if target in [6, 7]: # Should not happen, but keep hidden
                 pass
            else:
                 self.nav_container.show()
                 
                 # State 0: Path Selection
                 if target == 0:
                     self.back_btn.hide()
                     self.next_btn.show()
                     self.next_btn.setText("Continue")
                     self.progress_bar.set_target_progress(0.0)
                 
                 # State 1: Menu
                 elif target == 1:
                     self.back_btn.show()
                     self.next_btn.hide() # Menu has internal buttons
                     self.progress_bar.set_target_progress(0.2)
                 
                 # State 2: Ignore
                 elif target == 2:
                     self.back_btn.show()
                     self.next_btn.hide() # Wait for tree load? Actually go_next sets text to Continue
                     # But entering Ignore usually disables next or waits.
                     # Let's assume standard state:
                     self.next_btn.hide() 
                     self.progress_bar.set_target_progress(0.2)
                     
                 # State 3: Commit
                 elif target == 3:
                     self.back_btn.show()
                     self.next_btn.show()
                     self.next_btn.setText("Save Backup")
                     self.progress_bar.set_target_progress(0.8)
                     
                 # State 4: Restore List
                 elif target == 4:
                     self.back_btn.show()
                     self.next_btn.hide()
                     self.progress_bar.set_target_progress(0.4)
                     
                 # State 5: Restore Files
                 elif target == 5:
                     self.back_btn.show()
                     self.next_btn.hide()
                     self.progress_bar.set_target_progress(0.4)
            return

        # GitHub Push (7) -> Menu (1)
        if idx == 7:
            self.stacked.setCurrentIndex(1)
            self.nav_container.show()
            self.back_btn.show()
            self.next_btn.hide()
            return
            
        if idx == 1: # Menu -> Path
            self.stacked.setCurrentIndex(0)
            self.back_btn.hide()
            self.nav_container.show()
            self.next_btn.show()
            self.next_btn.setText("Continue")
            self.progress_bar.set_target_progress(0.0)
        elif idx == 2: # Ignore -> Menu
            self.stacked.setCurrentIndex(1)
            self.nav_container.show()
            self.next_btn.hide()
            self.progress_bar.set_target_progress(0.2)
        elif idx == 3: # Commit -> Ignore
            self.stacked.setCurrentIndex(2)
            self.next_btn.setText("Continue")
            self.progress_bar.set_target_progress(0.4)
        elif idx == 4: # Restore List -> Menu
            self.stacked.setCurrentIndex(1)
            self.next_btn.hide()
            self.progress_bar.set_target_progress(0.2)
        elif idx == 5: # Restore Files -> Restore List
            self.stacked.setCurrentIndex(4)
            self.next_btn.hide() # List selects item
            self.progress_bar.set_target_progress(0.4)
        elif action == "restore":
            self.load_commits()
            self.stacked.setCurrentIndex(4)
            self.next_btn.hide() # Rely on list buttons
            self.progress_bar.set_target_progress(0.4)

    # --- Create Flow Helpers (Lazy Loading) ---
    def start_ignore_tree_load(self):
        self.page_ignore.tree.clear()
        self.populate_node(self.project_path, self.page_ignore.tree.invisibleRootItem())
        self.page_ignore.show_tree()
        self.next_btn.setEnabled(True)

    def populate_node(self, path, parent_item):
        icon_folder = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        icon_file = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        SKIP_FOLDERS = {'.git'}
        
        try:
            with os.scandir(path) as it:
                entries = sorted(list(it), key=lambda e: (not e.is_dir(), e.name.lower()))
                
                for entry in entries:
                    if entry.name in SKIP_FOLDERS: 
                        # Even if skipped, we might want to show it unchecked? 
                        # Usually .gitignore excludes them. Let's skip them from list to avoid clutter.
                        continue
                        
                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, entry.name)
                    
                    # Store relative path for gitignore
                    rel = os.path.relpath(entry.path, self.project_path)
                    item.setData(0, Qt.ItemDataRole.UserRole, rel)
                    
                    # Smart Check
                    # Check both separator styles
                    if rel in self.pre_ignored_items or rel.replace(os.sep, "/") in self.pre_ignored_items:
                        item.setCheckState(0, Qt.CheckState.Checked)
                    else:
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                    
                    if entry.is_dir():
                        item.setIcon(0, icon_folder)
                        # Add dummy child to make it expandable
                        dummy = QTreeWidgetItem(item)
                        dummy.setText(0, "Loading...")
                        item.setData(0, Qt.ItemDataRole.UserRole + 1, True) # Mark as having dummy
                    else:
                        item.setIcon(0, icon_file)
                    

        except Exception as e:
            print(f"Error reading {path}: {e}")

    # --- Setup Avatar in Title Bar ---
    def resizeEvent(self, event):
        # Reposition avatar next to close button
        if hasattr(self, 'avatar_btn') and hasattr(self, 'title_bar'):
            # close btn is at right edge, width 46. contents margins 0.
            # let's put avatar to the left of close button.
            self.avatar_btn.move(self.title_bar.width() - 46 - 10 - 40, 0) # 46=close_w, 10=spacing, 40=avatar_w
            
        super().resizeEvent(event)

    def on_tree_item_expanded(self, item):
        # Check if needs loading (has dummy)
        if item.data(0, Qt.ItemDataRole.UserRole + 1):
            # Clear dummy
            item.takeChildren()
            # Reset flag
            item.setData(0, Qt.ItemDataRole.UserRole + 1, None)
            
            # Reconstruct full path
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            full_path = os.path.join(self.project_path, rel_path)
            
            # Load real children
            self.populate_node(full_path, item)

    def load_existing_gitignore(self):
        self.pre_ignored_items = set()
        path = os.path.join(self.project_path, ".gitignore")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self.pre_ignored_items.add(line)
            except: pass

    def collect_ignored(self):
        self.ignore_items = []
        it = QTreeWidgetItemIterator(self.page_ignore.tree)
        while it.value():
            item = it.value()
            if item.checkState(0) == Qt.CheckState.Checked:
                rel = item.data(0, Qt.ItemDataRole.UserRole)
                if rel: self.ignore_items.append(rel.replace("\\", "/"))
            it += 1
        return True

    def perform_commit(self):
        msg = self.page_commit.input.text().strip()
        if not msg:
            self.show_modern_alert("Error", "Please enter a backup name.")
            return

        if not os.path.exists(os.path.join(self.project_path, ".git")):
            self.run_git_cmd("git init")
        
        # Config check
        if not self.run_git_cmd("git config user.name").stdout.strip():
             self.run_git_cmd('git config user.name "BackupUser"')
             self.run_git_cmd('git config user.email "backup@local"')

        # Write gitignore
        if self.ignore_items:
            # 1. Untrack files so they are actually ignored (fix for old tracked files)
            for it in self.ignore_items:
                self.run_git_cmd(f'git rm -r --cached "{it}"')
                
            # 2. Update .gitignore safely
            gitignore_path = os.path.join(self.project_path, ".gitignore")
            existing_ignores = set()
            if os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "r", encoding="utf-8") as f:
                        existing_ignores = set(line.strip() for line in f if line.strip())
                except: pass
            
            with open(gitignore_path, "a", encoding="utf-8") as f:
                wrote_newline = False
                for it in self.ignore_items:
                    if it not in existing_ignores:
                        if not wrote_newline: 
                            f.write("\n")
                            wrote_newline = True
                        f.write(f"{it}\n")

        self.run_git_cmd("git add .")
        res = self.run_git_cmd(f'git commit -m "{msg}"')
        
        if res.returncode == 0:
            self.show_modern_alert("Success", f"Backup created: {msg}")
            self.stacked.setCurrentIndex(1) # Back to menu
        else:
             self.show_modern_alert("Info", "No changes to save.")

    # --- Restore Flow Helpers ---
    def load_commits(self):
        if not os.path.exists(os.path.join(self.project_path, ".git")):
            QMessageBox.warning(self, "Error", "No backups found.")
            self.go_back()
            return
            
        res = self.run_git_cmd('git log --pretty=format:"%h|%s|%ad" --date=short')
        self.page_restore_list.list_widget.clear()
        
        self.commits = [] 
        for line in res.stdout.strip().split('\n'):
            if not line: continue
            parts = line.split('|')
            if len(parts) >= 3:
                h, s, d = parts[0], parts[1], parts[2]
                item = QListWidgetItem(f"[{d}] {s}")
                item.setData(Qt.ItemDataRole.UserRole, h.strip())
                self.page_restore_list.list_widget.addItem(item)
                self.commits.append({'hash': h.strip(), 'msg': s, 'date': d})
        
        # Sync to GitHub Push Page
        self.update_commit_list_in_github()

    def update_commit_list_in_github(self):
        # Populate commit combo in Push Page
        if hasattr(self, 'page_github_push'):
            self.page_github_push.commit_combo.clear()
            
            if not hasattr(self, 'commits') or not self.commits:
                return
                
            for c in self.commits:
                msg = c['msg']
                h = c['hash']
                self.page_github_push.commit_combo.addItem(f"{msg} [{h[:7]}]", h)


    def on_restore_commit_selected(self, item):
        if not item: return
        self.selected_commit_hash = item.data(Qt.ItemDataRole.UserRole)
        # Load files
        res = self.run_git_cmd(f"git ls-tree -r --name-only {self.selected_commit_hash}")
        self.page_restore_files.tree.clear()
        
        # Check excessive file count
        lines = res.stdout.strip().split('\n')
        if len(lines) > 2000:
             self.show_modern_alert("Large Backup", "Too many files to display. Core restore logic remains safe.", is_error=False)
             lines = lines[:2000]
        
        self.populate_restore_tree(lines)
        
        self.stacked.setCurrentIndex(5)
        self.next_btn.show()
        self.next_btn.setText("Restore Selected")

    def populate_restore_tree(self, lines):
        icon_folder = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        icon_file = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        
        folders = {}
        for path in lines:
            if not path: continue
            parts = path.split('/')
            curr = self.page_restore_files.tree.invisibleRootItem()
            curr_path = ""
            for i, p in enumerate(parts):
                is_file = (i == len(parts)-1)
                curr_path = (curr_path + "/" + p) if curr_path else p
                if is_file:
                    fi = QTreeWidgetItem(curr); fi.setText(0, p); fi.setIcon(0, icon_file)
                    fi.setCheckState(0, Qt.CheckState.Unchecked); fi.setData(0, Qt.ItemDataRole.UserRole, path)
                else:
                    if curr_path in folders: curr = folders[curr_path]
                    else:
                        fo = QTreeWidgetItem(curr); fo.setText(0, p); fo.setIcon(0, icon_folder)
                        fo.setCheckState(0, Qt.CheckState.Unchecked); folders[curr_path] = fo; curr = fo

    def perform_restore_files(self):
        files = []
        it = QTreeWidgetItemIterator(self.page_restore_files.tree)
        while it.value():
            item = it.value()
            if item.checkState(0)==Qt.CheckState.Checked and item.childCount()==0:
                files.append(f'"{item.data(0, Qt.ItemDataRole.UserRole)}"')
            it += 1
            
        if not files:
            self.show_modern_alert("Warning", "No files selected.")
            return

        res = self.run_git_cmd(f"git checkout {self.selected_commit_hash} -- {' '.join(files)}")
        if res.returncode == 0:
            self.show_modern_alert("Success", "Files restored successfully.")
            self.stacked.setCurrentIndex(1)
        else:
            self.show_modern_alert("Error", res.stderr, is_error=True)
            
    # --- New Logic for Rename/Delete/Purge ---
    def on_rename_commit(self):
        item = self.page_restore_list.list_widget.currentItem()
        if not item: return self.show_modern_alert("Select Backup", "Please select a backup to rename.")
        
        old_msg = item.text().split(']')[1].strip() if ']' in item.text() else item.text()
        commit_hash = item.data(Qt.ItemDataRole.UserRole)
        
        new_name = self.show_modern_input("Rename Backup", "Enter new name:", old_msg)
        if not new_name: return

        head_res = self.run_git_cmd("git rev-parse --short HEAD")
        current_head = head_res.stdout.strip()

        if commit_hash == current_head:
            res = self.run_git_cmd(f'git commit --amend -m "{new_name}"')
            if res.returncode == 0:
                self.show_modern_alert("Success", "Backup renamed successfully.")
                self.load_commits()
            else:
                 self.show_modern_alert("Error", res.stderr, is_error=True)
        else:
            self.show_modern_alert("Limit", "Renaming historical backups is restricted in this version.")

    def on_delete_commit(self):
        item = self.page_restore_list.list_widget.currentItem()
        if not item: return self.show_modern_alert("Select Backup", "Please select a backup to delete.")
        
        commit_hash = item.data(Qt.ItemDataRole.UserRole)
        head_res = self.run_git_cmd("git rev-parse --short HEAD")
        current_head = head_res.stdout.strip()
        
        if commit_hash == current_head:
            if self.show_modern_confirm("Confirm Delete", "Are you sure you want to undo the last backup? Changes will be kept in staging.", confirm_color=Config.ERROR):
                if self.run_git_cmd("git reset --soft HEAD~1").returncode == 0:
                    self.show_modern_alert("Success", "Last backup undone.")
                    self.load_commits()
        else:
             self.show_modern_alert("Limit", "Can only delete the most recent backup safely.")

    def on_purge_commit(self):
        item = self.page_restore_list.list_widget.currentItem()
        if not item: return self.show_modern_alert("Select Backup", "Please select the backup to keep.")
        
        if not self.show_modern_confirm("Danger Zone", "Delete ALL history before this point? This cannot be undone.", confirm_color=Config.ERROR): return
        
        msg = item.text().split(']')[1].strip() if ']' in item.text() else "Clean Backup"
        self.run_git_cmd("git checkout --orphan temp_branch")
        self.run_git_cmd("git add -A")
        self.run_git_cmd(f'git commit -m "{msg}"')
        self.run_git_cmd("git branch -D master")
        self.run_git_cmd("git branch -m master")
        self.show_modern_alert("Success", "History pruned.")
        self.load_commits()

    # --- Restore List Push Action ---
    def on_push_commit(self):
        item = self.page_restore_list.list_widget.currentItem()
        if not item: return self.show_modern_alert("Select Backup", "Please select a backup to push.")
        
        commit_hash = item.data(Qt.ItemDataRole.UserRole)
        
        if not self.show_modern_confirm("Confirm Push", "This will FORCE push this state to GitHub/origin, overwriting remote history. Continue?"):
             return
             
        # Create a branch pointing to this commit to push
        # OR just push hash:master 
        self.show_modern_alert("Pushing", "Pushing to remote... This may take a moment.")
        QApplication.processEvents()
        
        res = self.run_git_cmd(f"git push origin {commit_hash}:refs/heads/master --force")
        if res.returncode == 0:
             self.show_modern_alert("Success", "Backup pushed to GitHub!")
        else:
             self.show_modern_alert("Error", f"Push failed: {res.stderr}", is_error=True)


    # --- Modern Dialog Helpers ---
    def show_modern_alert(self, title, message, is_error=False):
        dlg = ModernDialog(self, title)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg.add_widget(lbl)
        dlg.add_button("OK", "accept", Config.ERROR if is_error else Config.ACCENT)
        self.center_dialog(dlg)
        dlg.exec()

    def show_modern_confirm(self, title, message, confirm_color=Config.WARNING):
        dlg = ModernDialog(self, title)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg.add_widget(lbl)
        dlg.add_button("Cancel", "reject")
        dlg.add_button("Confirm", "accept", confirm_color)
        self.center_dialog(dlg)
        return dlg.exec() == 1

    def show_modern_choice(self, title, message, yes_text="Yes", no_text="No"):
        dlg = ModernDialog(self, title)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg.add_widget(lbl)
        
        dlg.add_button(no_text, "reject")
        dlg.add_button(yes_text, "accept", Config.ACCENT)
        
        self.center_dialog(dlg)
        return dlg.exec() == 1

    def show_modern_input(self, title, label_text, default_text="", confirm_color=Config.ACCENT):
        dlg = ModernDialog(self, title)
        
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {Config.SUBTEXT}; font-size: 14px; border: none;")
        dlg.add_widget(lbl)
        
        inp = QLineEdit(default_text)
        inp.setStyleSheet(f"""
            background: {Config.PANEL_BG};
            color: {Config.TEXT};
            border: 1px solid {Config.BORDER};
            border-radius: 8px;
            padding: 8px;
            font-size: 14px;
        """)
        dlg.add_widget(inp)
        
        dlg.add_button("Cancel", "reject")
        save_btn = dlg.add_button("Save", "accept", confirm_color)
        
        # Focus input logic
        inp.setFocus()
        inp.selectAll()
        
        self.center_dialog(dlg)
        if dlg.exec() == 1:
            return inp.text().strip()
        return None

    def center_dialog(self, dlg):
        # Center relative to parent (self)
        geo = self.geometry()
        x = geo.x() + (geo.width() - dlg.width()) // 2
        y = geo.y() + (geo.height() - dlg.height()) // 2
        dlg.move(x, y)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Backit")
    
    # Setup Icon (Method from main.py)
    try:
        if sys.platform.startswith('win'):
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Backit.App")
    except Exception as e:
        print(f"Warning: failed to set AppUserModelID: {e}")

    try:
        app_icon_path = resource_path("Backit.ico")
        app_icon = QIcon(app_icon_path)
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
    except Exception as e:
        print(f"Warning: failed to set application icon: {e}")

    window = SetupAppWindow()
    window.show()
    sys.exit(app.exec())