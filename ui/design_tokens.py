"""Shared semantic presentation tokens for the native desktop companion."""
from __future__ import annotations

from PyQt6.QtGui import QGuiApplication

COLORS = {
    "background": "#02060B",
    "surface": "#071522",
    "surface_raised": "#091A28",
    "text": "#F5FAFF",
    "secondary": "#A7B9CA",
    "muted": "#667D91",
    "border": "rgba(120, 190, 230, 0.18)",
    "accent": "#20B8FF",
    "bright": "#4DDCFF",
    "soft": "#9DDBFF",
    "danger": "#ff929f",
    "selection": "#244656",
}

SPACE = {"1": 4, "2": 8, "3": 12, "4": 16, "5": 20, "6": 24, "8": 32, "10": 40}
TYPE = {"display": 30, "page_title": 23, "section_title": 19, "body": 16, "supporting": 14, "control": 14, "metadata": 12}
CONTROL_HEIGHT = 44
TOUCH_TARGET = 44


def stylesheet(*, high_contrast: bool = False) -> str:
    colors = dict(COLORS)
    if high_contrast:
        colors.update(secondary="#cbd8de", muted="#b2c2ca", border="#536f7c", accent="#8acaff")
    return f"""
    QWidget {{ color: {colors['text']}; font-family: Inter, 'Segoe UI', Arial; font-size: {TYPE['body']}px; }}
    QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTreeWidget {{
      color: {colors['text']}; background: {colors['surface']}; border: 1px solid {colors['border']};
      border-radius: 13px; padding: 9px 12px; selection-background-color: {colors['selection']};
    }}
    QPushButton {{ color: {colors['text']}; background: {colors['surface']}; border: 1px solid {colors['border']};
      border-radius: 12px; padding: 9px 16px; min-height: {CONTROL_HEIGHT}px; }}
    QPushButton:hover {{ background: {colors['surface_raised']}; border-color: {colors['accent']}; }}
    QPushButton:pressed {{ background: {colors['selection']}; }}
    QPushButton:disabled {{ color: {colors['muted']}; }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextBrowser:focus,
    QTreeWidget:focus, QPushButton:focus, QTabBar::tab:focus {{ border: 2px solid {colors['accent']}; }}
    QCheckBox {{ spacing: 9px; }} QCheckBox::indicator {{ width: 20px; height: 20px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


def fit_window_to_screen(widget, *, preferred: tuple[int, int], minimum: tuple[int, int] = (560, 440)) -> None:
    """Pick a usable initial size while retaining resizability and user zoom."""
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        widget.resize(*preferred)
        widget.setMinimumSize(*minimum)
        return
    available = screen.availableGeometry()
    width = max(320, min(preferred[0], int(available.width() * 0.92)))
    height = max(320, min(preferred[1], int(available.height() * 0.9)))
    widget.setMinimumSize(min(minimum[0], width), min(minimum[1], height))
    widget.resize(width, height)
