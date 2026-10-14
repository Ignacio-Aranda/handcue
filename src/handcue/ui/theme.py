"""Design tokens and the application stylesheet.

Neutral grays plus a single accent color, reserved for interactive and active
elements. Spacing follows a 4 px scale; text uses three levels told apart by
color rather than size.
"""
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

# Colors
BG = "#0e0f11"
SURFACE = "#141518"
RAISED = "#1b1c20"
HOVER = "#24252a"
PRESSED = "#2c2d33"
BORDER = "#25272c"
BORDER_STRONG = "#34363d"
TEXT = "#ececef"
TEXT_2 = "#a1a1aa"
TEXT_3 = "#6b6b75"
ACCENT = "#4c8dff"
ACCENT_HOVER = "#6ea2ff"
ACCENT_SOFT = "rgba(76, 141, 255, 0.14)"
SUCCESS = "#3ecf8e"
WARNING = "#e5a50a"
DANGER = "#f05252"

# Spacing and shape
S1, S2, S3, S4, S6, S8 = 4, 8, 12, 16, 24, 32
RADIUS = 6
RADIUS_LARGE = 10
CONTROL_HEIGHT = 32

FONT = "Inter"
FONTS_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"


def load_fonts(app):
    for f in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))
    font = QFont(FONT)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)


STYLESHEET = f"""
* {{ font-family: "{FONT}"; font-size: 13px; color: {TEXT}; outline: none; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#surface {{ background: {SURFACE}; }}
QWidget#topBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QWidget#inspector {{ background: {SURFACE}; border-left: 1px solid {BORDER}; }}
QWidget#viewBar {{ background: {BG}; }}

QLabel {{ background: transparent; }}
QLabel[level="2"] {{ color: {TEXT_2}; font-size: 12px; }}
QLabel[level="3"] {{ color: {TEXT_3}; font-size: 12px; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="heading"] {{ color: {TEXT_3}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel[role="value"] {{ color: {TEXT_2}; font-size: 12px; }}
QLabel:disabled {{ color: {TEXT_3}; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px;
    padding: 0 {S3}px; min-height: {CONTROL_HEIGHT - 2}px; font-weight: 500;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {TEXT_3}; border-color: {BORDER}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[kind="ghost"] {{ background: transparent; border-color: transparent; color: {TEXT_2}; }}
QPushButton[kind="ghost"]:hover {{ background: {HOVER}; color: {TEXT}; }}
QPushButton[kind="danger"] {{ background: transparent; border-color: transparent; color: {DANGER}; }}
QPushButton[kind="danger"]:hover {{ background: rgba(240, 82, 82, 0.12); }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: {RADIUS}px;
    min-width: {CONTROL_HEIGHT}px; min-height: {CONTROL_HEIGHT}px; padding: 0;
}}
QToolButton:hover {{ background: {HOVER}; }}
QToolButton:pressed {{ background: {PRESSED}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; }}
QToolButton[withText="true"] {{ padding: 0 {S3}px 0 {S2}px; color: {TEXT_2}; font-weight: 500; }}
QToolButton[withText="true"]:checked {{ color: {TEXT}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px;
    min-height: {CONTROL_HEIGHT - 2}px; padding: 0 {S2}px; selection-background-color: {ACCENT};
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: #45474f; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px; padding: {S1}px;
    selection-background-color: {HOVER}; selection-color: {TEXT};
}}
QComboBox[flat="true"] {{ background: transparent; border-color: transparent; font-weight: 600; }}
QComboBox[flat="true"]:hover {{ background: {HOVER}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER_STRONG}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #ffffff; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: #dfe6ff; }}
QSlider::sub-page:horizontal:disabled {{ background: {BORDER_STRONG}; }}
QSlider::handle:horizontal:disabled {{ background: #55565e; }}

QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_2}; font-weight: 500; padding: {S2}px {S3}px;
    margin-right: {S2}px; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4c54; }}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: {RADIUS + 2}px; color: {TEXT_2};
}}
QListWidget::item:hover {{ background: {HOVER}; color: {TEXT}; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {TEXT}; }}

QPlainTextEdit {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 12px; color: {TEXT_2};
}}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px; padding: {S1}px; }}
QMenu::item {{ padding: 6px {S3}px; border-radius: 4px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: {S1}px 0; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 4px 8px; }}
QProgressBar {{ background: transparent; border: none; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QFrame[role="separator"] {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}
"""
