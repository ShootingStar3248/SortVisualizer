"""配色、样式表与 Python 代码高亮。"""

from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import (QColor, QFont, QSyntaxHighlighter, QTextCharFormat)

# 值 → 颜色：0 为红，1 为紫，中间走完一整条彩虹
HUE_SPAN = 270.0


def rainbow_color(ratio):
    """ratio ∈ [0,1]，返回红→紫渐变上的颜色。"""
    if ratio < 0.0:
        ratio = 0.0
    elif ratio > 1.0:
        ratio = 1.0
    return QColor.fromHsvF(HUE_SPAN * ratio / 360.0, 0.85, 0.98)


APP_QSS = """
QMainWindow, QWidget {
    background: #0b0d13;
    color: #d7dae3;
    font-size: 13px;
}
QFrame#toolbar {
    background: #141722;
    border: 1px solid #232839;
    border-radius: 10px;
}
QFrame#card {
    background: #111420;
    border: 1px solid #232839;
    border-radius: 10px;
}
QFrame#card[winner="true"] { border: 1px solid #f2c14e; }
QFrame#card[error="true"] { border: 1px solid #e05a5a; }
QFrame#card[dragging="true"] { border: 1px solid #2f6df6; }
QWidget#grip, QWidget#resizeHandle { background: transparent; }
QLabel#hint { color: #7b8294; }
QLabel#stats { color: #8f96a8; }
QLabel#ops { color: #9aa2b6; font-size: 12px; padding-right: 2px; }
QLabel#field { color: #9aa2b6; }
QLineEdit#nameEdit {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px 6px;
    color: #f0f2f7;
}
QLineEdit#nameEdit:hover { border: 1px solid #2a3245; }
QLineEdit#nameEdit:focus { background: #1b2030; border: 1px solid #2f6df6; }
QPlainTextEdit#code {
    background: #0d1018;
    border: 1px solid #232839;
    border-radius: 6px;
    padding: 5px;
    color: #cfd4e0;
    selection-background-color: #2c4b8f;
}
QSpinBox {
    background: #0f1220;
    border: 1px solid #2a3245;
    border-radius: 6px;
    padding: 3px 6px;
    color: #dbe2f0;
    min-width: 62px;
}
QSpinBox:disabled { color: #565d70; }
QPushButton {
    background: #22304d;
    border: 1px solid #2f4067;
    border-radius: 6px;
    padding: 5px 14px;
    color: #dbe2f0;
}
QPushButton:hover { background: #2a3c60; }
QPushButton:disabled { background: #171b26; color: #565d70; border-color: #222736; }
QPushButton#primary {
    background: #2f6df6;
    border-color: #2f6df6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primary:hover { background: #3b78ff; }
QToolButton {
    background: #1b2130;
    border: 1px solid #2a3245;
    border-radius: 6px;
    padding: 2px 8px;
    color: #aab2c4;
}
QToolButton:hover { background: #232b3d; }
QToolButton:checked { background: #2f6df6; border-color: #2f6df6; color: #ffffff; }
QToolButton:disabled { color: #4d5468; }
QToolButton#expand { padding: 0; font-size: 11px; color: #8f96a8; }
QToolButton#expand:hover { color: #dbe2f0; }
QToolButton#expand:checked { background: #232b3d; border-color: #2a3245; color: #dbe2f0; }
QSlider::groove:horizontal { height: 4px; background: #232839; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #2f6df6; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #dbe2f0;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #262d3f; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #333c53; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QStatusBar { color: #8f96a8; }
QStatusBar::item { border: none; }
"""

KEYWORDS = (
    'def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'and', 'or',
    'break', 'continue', 'pass', 'lambda', 'import', 'from', 'as', 'class', 'try',
    'except', 'finally', 'with', 'yield', 'global', 'nonlocal', 'assert', 'del',
    'raise', 'is', 'None', 'True', 'False', 'range', 'len', 'min', 'max', 'abs',
    'int', 'float', 'list', 'print', 'sorted', 'enumerate', 'zip', 'reversed',
)


class PythonHighlighter(QSyntaxHighlighter):
    """够用的 Python 语法高亮：关键字、数字、字符串、注释。"""

    def __init__(self, document):
        super().__init__(document)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor('#7ab7ff'))
        keyword_format.setFontWeight(QFont.Bold)

        number_format = QTextCharFormat()
        number_format.setForeground(QColor('#e5a76a'))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor('#8fd68a'))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor('#5c6478'))
        comment_format.setFontItalic(True)

        self._rules = [(QRegularExpression(r'\b%s\b' % word), keyword_format) for word in KEYWORDS]
        self._rules.append((QRegularExpression(r'\b\d+(\.\d+)?\b'), number_format))
        self._rules.append((QRegularExpression(r"'[^']*'|\"[^\"]*\""), string_format))
        self._rules.append((QRegularExpression(r'#[^\n]*'), comment_format))

    def highlightBlock(self, text):
        for expression, char_format in self._rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), char_format)
