"""彩虹条色带、带行号指针的代码框、单个算法面板。

一条彩虹条 = 一行等高的色块，左端红、右端紫，颜色只由元素的值决定，
相邻格子严丝合缝（不按高度区分、也不留空隙），高度与算法名一致。
排完之后整条盖上灰色蒙版，写上名次（1st/2nd/…）、Wrong 或 Syntax Error。

每个算法名占据固定的列宽（取所有算法名里最长的那个），
这样所有彩虹条的左边缘和长度都是对齐的，方便横向比较。
"""

from PyQt5.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFontDatabase, QPainter, QPainterPath,
                         QTextCursor, QTextFormat)
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QTextEdit, QToolButton, QVBoxLayout,
                             QWidget)

from .executor import AlgorithmRunner
from .theme import PythonHighlighter, rainbow_color

ROW_HEIGHT = 24          # 彩虹条与算法名共用的高度
CODE_MIN_HEIGHT = 80     # 代码框能被拖到的最小高度
CODE_DEFAULT_HEIGHT = 220   # 代码框的初始高度
GRIP_WIDTH = 16          # 面板左侧拖拽碰撞箱的宽度
HANDLE_HEIGHT = 8        # 代码框下方高度把手的高度
DRAG_THRESHOLD = 4       # 拖动多少像素才算真在拖
DEFAULT_NAME = '排序算法'
DEFAULT_CODE = 'def sort(a):\n    pass\n'
NAME_MIN_WIDTH = 92
OPS_WIDTH = 76
BUTTON_WIDTH = 24

HEAT_LEVELS = 16         # 热度量化级别，用于缓存颜色
HEAT_BLEND = 0.88        # 最高热度时向白色靠拢的比例

GUTTER_BG = QColor('#0b0e15')
GUTTER_FG = QColor('#5b6070')
POINTER_COLOR = QColor('#ffc43d')
CURRENT_LINE_BG = QColor('#212a42')

MARK_WRITE = QColor(255, 255, 255, 235)     # 刚被写入的位置
MARK_READ = QColor(255, 196, 61, 235)       # 刚被读取（比较）的位置
MASK_COLOR = QColor(58, 62, 74, 208)        # 结束后的灰色蒙版
TEXT_COLOR = QColor(245, 247, 252)
WRONG_COLOR = QColor(255, 145, 145)


def text_width(metrics, text):
    if hasattr(metrics, 'horizontalAdvance'):
        return metrics.horizontalAdvance(text)
    return metrics.width(text)


def friendly_count(number):
    """把大数字缩写成 12.3k / 1.24M，方便塞进窄窄的一行。"""
    if number >= 1_000_000:
        return '%.2fM' % (number / 1_000_000.0)
    if number >= 10_000:
        return '%.1fk' % (number / 1000.0)
    return str(int(number))


# ----------------------------------------------------------------------
# 带行号的代码框
# ----------------------------------------------------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    """带行号的代码框：当前执行到的那一行会用三角形指针标出来。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('code')
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        if hasattr(self, 'setTabStopDistance'):
            self.setTabStopDistance(28)
        self.current_line = 0
        self._gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self._on_block_count_changed)
        self.updateRequest.connect(self._on_update_request)
        self._update_gutter_width()
        self._apply_current_line()

    # ------------------------------------------------------------------
    def gutter_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 22 + text_width(self.fontMetrics(), '9') * digits

    def _update_gutter_width(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _on_block_count_changed(self, _count):
        self._update_gutter_width()

    def _on_update_request(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self._gutter.setGeometry(QRect(area.left(), area.top(),
                                       self.gutter_width(), area.height()))

    # ------------------------------------------------------------------
    def set_current_line(self, line):
        if not isinstance(line, int):    # f_lineno 偶尔是 None（隐式跳转那一拍）
            line = 0
        if line == self.current_line:
            return
        self.current_line = line
        self._apply_current_line()
        self._gutter.update()
        if line > 0:
            self._scroll_into_view(line)

    def _apply_current_line(self):
        selections = []
        if self.current_line > 0:
            block = self.document().findBlockByNumber(self.current_line - 1)
            if block.isValid():
                selection = QTextEdit.ExtraSelection()
                selection.format.setBackground(CURRENT_LINE_BG)
                selection.format.setProperty(QTextFormat.FullWidthSelection, True)
                selection.cursor = QTextCursor(block)
                selections.append(selection)
        self.setExtraSelections(selections)

    def _scroll_into_view(self, line):
        block = self.document().findBlockByNumber(line - 1)
        if not block.isValid():
            return
        geometry = self.blockBoundingGeometry(block).translated(self.contentOffset())
        scrollbar = self.verticalScrollBar()
        if geometry.top() < 0:
            scrollbar.setValue(scrollbar.value() + int(geometry.top()))
        elif geometry.bottom() > self.viewport().height():
            scrollbar.setValue(scrollbar.value()
                               + int(geometry.bottom() - self.viewport().height()) + 1)

    # ------------------------------------------------------------------
    def paint_gutter(self, event):
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), GUTTER_BG)
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        offset = self.contentOffset()
        top = self.blockBoundingGeometry(block).translated(offset).top()
        bottom = top + self.blockBoundingRect(block).height()
        line_height = self.fontMetrics().height()
        width = self._gutter.width()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = number + 1
                if line == self.current_line:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(POINTER_COLOR)
                    center = top + line_height / 2.0
                    pointer = QPainterPath()
                    pointer.moveTo(4.0, center - 6.0)
                    pointer.lineTo(14.0, center)
                    pointer.lineTo(4.0, center + 6.0)
                    pointer.closeSubpath()
                    painter.drawPath(pointer)
                    painter.setPen(POINTER_COLOR)
                else:
                    painter.setPen(GUTTER_FG)
                painter.drawText(0, int(top), width - 5, line_height,
                                 Qt.AlignRight | Qt.AlignVCenter, str(line))
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            number += 1
        painter.end()


# ----------------------------------------------------------------------
# 彩虹条
# ----------------------------------------------------------------------
class BarCanvas(QWidget):
    """等高无缝的彩虹色带。

    每个格子带一个热度值：刚被碰过是白亮的，然后随着模拟推进慢慢褪回本色。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(16)
        self._data = []
        self._max = 1.0
        self._cache = {}
        self._heat_cache = {}
        self._peak = 0.0
        self.heat = []           # 与数据等长的热度表（工作线程会写）
        self.hot = ()            # 最近被写入的位置（工作线程写）
        self.cursor = None       # 最近被读取的位置（工作线程写）
        self.verdict = ''        # 结束后的结论：'1st' / 'Wrong' / 'Syntax Error'
        self.verdict_kind = ''   # 'ok' / 'wrong' / 'error'

    # ------------------------------------------------------------------
    def bind(self, data, maximum=None):
        """绑定底层列表；运行中直接引用算法的实时数组，无需拷贝。"""
        self._data = data
        if maximum:
            self._max = float(maximum)
        elif data:
            self._max = float(max(data))
        else:
            self._max = 1.0
        if self._max <= 0:
            self._max = 1.0
        self.heat = [0.0] * len(self._data)
        self._peak = 0.0
        self._heat_cache.clear()
        self.hot = ()
        self.cursor = None
        self.verdict = ''
        self.verdict_kind = ''
        self.update()

    # ------------------------------------------------------------------
    # 热度：被碰过的地方亮一下，然后按模拟速度褪回本色
    # ------------------------------------------------------------------
    def add_heat(self, indices, amount):
        heat = self.heat
        size = len(heat)
        for index in indices:
            if 0 <= index < size:
                value = heat[index] + amount
                if value > 1.0:
                    value = 1.0
                heat[index] = value
                if value > self._peak:
                    self._peak = value

    def cool_down(self, step):
        """褪一层热；返回 True 表示还有地方没褪完。"""
        if self._peak <= 0.0:
            return False
        heat = self.heat
        peak = 0.0
        for index, value in enumerate(heat):
            if value <= 0.0:
                continue
            value -= step
            if value <= 0.0:
                heat[index] = 0.0
            else:
                heat[index] = value
                if value > peak:
                    peak = value
        self._peak = peak
        return peak > 0.0

    def reset_heat(self):
        for index in range(len(self.heat)):
            self.heat[index] = 0.0
        self._peak = 0.0

    def is_hot(self):
        return self._peak > 0.0

    def set_verdict(self, text, kind=''):
        self.verdict = text or ''
        self.verdict_kind = kind
        self.update()

    def item_count(self):
        return len(self._data)

    def clear_marks(self):
        self.hot = ()
        self.cursor = None
        self.update()

    def color_for(self, key):
        color = self._cache.get(key)
        if color is None:
            color = rainbow_color(key / 255.0)
            self._cache[key] = color
        return color

    def heated_color(self, key, level, base):
        """按热度把本色往白色拉，结果缓存起来。"""
        cache_key = (key, level)
        color = self._heat_cache.get(cache_key)
        if color is None:
            blend = level / float(HEAT_LEVELS) * HEAT_BLEND
            color = QColor(int(base.red() + (255 - base.red()) * blend),
                           int(base.green() + (255 - base.green()) * blend),
                           int(base.blue() + (255 - base.blue()) * blend))
            self._heat_cache[cache_key] = color
        return color

    @staticmethod
    def _bounds(index, count, width):
        left = int(index * width / count)
        right = int((index + 1) * width / count)
        if right <= left:
            right = left + 1
        return left, right

    def _draw_marker(self, painter, index, count, width, height, color, at_top):
        """在格子顶部 / 底部压一条亮线。

        不用描边：四周描边会让相邻色块看起来像有空隙，而这里要求严丝合缝。
        """
        left, right = self._bounds(index, count, width)
        thickness = max(2, min(5, height // 8))
        top = 0 if at_top else height - thickness
        painter.fillRect(QRect(left, top, right - left, thickness), color)

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width()
        height = self.height()
        painter.fillRect(self.rect(), QColor('#0e1017'))

        data = self._data
        count = len(data)
        if count == 0:
            painter.setPen(QColor('#4a4f61'))
            painter.drawText(self.rect(), Qt.AlignCenter, '等待生成数据…')
            painter.end()
            return

        radius = min(6.0, height / 2.0)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0.0, 0.0, float(width), float(height)), radius, radius)
        painter.setClipPath(clip)
        painter.setPen(Qt.NoPen)

        maximum = self._max
        heat = self.heat
        heat_count = len(heat)
        left = 0
        for index in range(count):
            right = int((index + 1) * width / count)
            if right <= left:
                continue  # 格子比像素还窄，并进下一格
            ratio = data[index] / maximum
            if ratio < 0.0:
                ratio = 0.0
            elif ratio > 1.0:
                ratio = 1.0
            key = int(ratio * 255)
            base = self.color_for(key)
            warm = heat[index] if index < heat_count else 0.0
            if warm > 0.02:
                level = int(warm * HEAT_LEVELS)
                if level > HEAT_LEVELS:
                    level = HEAT_LEVELS
                base = self.heated_color(key, level, base)
            painter.fillRect(QRect(left, 0, right - left, height), base)
            left = right

        cursor = self.cursor
        if cursor is not None and 0 <= cursor < count:
            self._draw_marker(painter, cursor, count, width, height, MARK_READ, False)

        if self.verdict:
            painter.fillRect(self.rect(), MASK_COLOR)
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(max(12, min(int(height * 0.56), 46)))
            painter.setFont(font)
            if self.verdict_kind in ('wrong', 'error'):
                painter.setPen(WRONG_COLOR)
            else:
                painter.setPen(TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, self.verdict)
        painter.end()


# ----------------------------------------------------------------------
# 两个小手柄：左侧拖拽碰撞箱 + 代码框高度把手
# ----------------------------------------------------------------------
class PanelGrip(QWidget):
    """面板左侧的碰撞箱：按住上下拖，就能把这块面板挪到别的顺序上。"""

    dragStarted = pyqtSignal(object)
    dragMoved = pyqtSignal(object, object)     # (panel, 鼠标全局坐标)
    dragFinished = pyqtSignal(object)

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setObjectName('grip')
        self.setFixedWidth(GRIP_WIDTH)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip('按住上下拖动，调整这个算法的先后顺序')
        self._origin = None
        self._dragging = False

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._origin = event.pos()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._origin is None:
            return
        moved = event.pos() - self._origin
        if not self._dragging:
            if abs(moved.y()) < DRAG_THRESHOLD and abs(moved.x()) < DRAG_THRESHOLD:
                return
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            self.dragStarted.emit(self.panel)
        self.dragMoved.emit(self.panel, event.globalPos())

    def mouseReleaseEvent(self, event):
        if self._origin is None:
            super().mouseReleaseEvent(event)
            return
        self._origin = None
        if self._dragging:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.update()
            self.dragFinished.emit(self.panel)

    def paintEvent(self, _event):
        """画三个小点，提示这里可以按住拖。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#7c86a0') if self._dragging else QColor('#3b4359'))
        size = 3.0
        spacing = 6.0
        left = (self.width() - size) / 2.0
        middle = self.height() / 2.0 - size / 2.0
        for index in (-1, 0, 1):
            painter.drawEllipse(QRectF(left, middle + index * spacing, size, size))
        painter.end()


class ResizeHandle(QWidget):
    """代码框下方的高度把手：上下拖动，只改这一块面板的代码框高度。"""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setObjectName('resizeHandle')
        self.setFixedHeight(HANDLE_HEIGHT)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip('上下拖动，调整这个代码框的高度')
        self._start_y = None
        self._start_height = 0
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._start_y = event.globalPos().y()
        self._start_height = self.panel.editor.height()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._start_y is None:
            return
        self.panel.set_code_height(self._start_height + event.globalPos().y() - self._start_y)

    def mouseReleaseEvent(self, event):
        if self._start_y is None:
            super().mouseReleaseEvent(event)
            return
        self._start_y = None
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._start_y is not None:
            color = QColor('#3b78ff')
        elif self._hovered:
            color = QColor('#57607a')
        else:
            color = QColor('#2a3245')
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        bar = min(90.0, max(36.0, self.width() / 4.0))
        painter.drawRoundedRect(QRectF((self.width() - bar) / 2.0,
                                       (self.height() - 3) / 2.0, bar, 3.0), 1.5, 1.5)
        painter.end()


# ----------------------------------------------------------------------
# 算法面板
# ----------------------------------------------------------------------
class AlgorithmPanel(QFrame):
    """一行算法：拖拽碰撞箱 + 名字 + 彩虹条 + 操作数 + 展开箭头 + 删除按钮。

    展开箭头下面藏着代码框和详细的统计数据，
    代码框左侧行号处有三角形指针标出当前执行到第几行，
    代码框下沿的把手可以单独把这一块拖高拖矮（有最小值）。
    """

    removeRequested = pyqtSignal(object)
    nameChanged = pyqtSignal()

    def __init__(self, name='', code='', parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        self.runner = None
        self.verdict = None
        self.verdict_kind = ''
        self.syntax_error = None
        self._flags = {'winner': False, 'error': False}
        self._build_ui(name, code)

    # ------------------------------------------------------------------
    def _build_ui(self, name, code):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 10, 6)
        outer.setSpacing(4)

        self.grip = PanelGrip(self)      # 左侧拖拽碰撞箱
        outer.addWidget(self.grip)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        outer.addLayout(root, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.name_edit = QLineEdit(name)
        self.name_edit.setObjectName('nameEdit')
        name_font = self.name_edit.font()
        name_font.setPixelSize(13)
        name_font.setBold(True)
        self.name_edit.setFont(name_font)   # 显式设字体，列宽才能量得准
        self.name_edit.setFixedHeight(ROW_HEIGHT)
        self.name_edit.setMinimumWidth(NAME_MIN_WIDTH)
        self.name_edit.setPlaceholderText('算法名')
        self.name_edit.textChanged.connect(self._on_name_changed)
        row.addWidget(self.name_edit)

        self.canvas = BarCanvas(self)
        self.canvas.setFixedHeight(ROW_HEIGHT)
        row.addWidget(self.canvas, 1)

        self.ops_label = QLabel('')
        self.ops_label.setObjectName('ops')
        self.ops_label.setFixedWidth(OPS_WIDTH)
        self.ops_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ops_label.setToolTip('已执行的操作数（字节码条数；用 a.sort() 时按实际比较次数折算）')
        row.addWidget(self.ops_label)

        self.expand_button = QToolButton()
        self.expand_button.setObjectName('expand')
        self.expand_button.setText('▼')
        self.expand_button.setToolTip('展开 / 收起代码')
        self.expand_button.setCheckable(True)
        self.expand_button.setFixedSize(BUTTON_WIDTH, ROW_HEIGHT - 2)
        self.expand_button.toggled.connect(self._toggle_body)
        row.addWidget(self.expand_button)

        self.remove_button = QToolButton()
        self.remove_button.setText('×')
        self.remove_button.setToolTip('删除这个排序方式')
        self.remove_button.setFixedSize(BUTTON_WIDTH, ROW_HEIGHT - 2)
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self))
        row.addWidget(self.remove_button)
        root.addLayout(row)

        # ---- 展开后：统计 + 代码框 ----
        self.body = QWidget(self)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.stats_label = QLabel('待运行')
        self.stats_label.setObjectName('stats')
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tools.addWidget(self.stats_label, 1)
        body.addLayout(tools)

        self.editor = CodeEditor(self)
        self.editor.setPlaceholderText('在这里写排序代码（就地操作列表 a，或者定义 sort(a)）')
        self.editor.setPlainText(code)
        self.editor.setFixedHeight(CODE_DEFAULT_HEIGHT)
        self.highlighter = PythonHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._check_syntax)
        body.addWidget(self.editor, 1)

        self.resize_handle = ResizeHandle(self)      # 代码框下方的高度把手
        body.addWidget(self.resize_handle)

        self.body.hide()
        root.addWidget(self.body, 1)
        self._check_syntax()

    # ------------------------------------------------------------------
    # 高度：每个面板各调各的
    # ------------------------------------------------------------------
    def set_code_height(self, height):
        """代码框高度（鼠标拖把手时调用），不会小于 CODE_MIN_HEIGHT。"""
        height = max(CODE_MIN_HEIGHT, int(height))
        self.editor.setFixedHeight(height)
        return height

    def code_height(self):
        return self.editor.height()

    # ------------------------------------------------------------------
    # 基本信息
    # ------------------------------------------------------------------
    def name(self):
        return self.name_edit.text().strip() or '未命名算法'

    def code(self):
        return self.editor.toPlainText()

    def name_width_hint(self):
        metrics = self.name_edit.fontMetrics()
        return text_width(metrics, self.name_edit.text() or '算法') + 20

    def set_name_width(self, width):
        self.name_edit.setFixedWidth(max(NAME_MIN_WIDTH, int(width)))

    def set_expanded(self, expanded):
        self.expand_button.setChecked(bool(expanded))

    def _toggle_body(self, shown):
        self.body.setVisible(shown)
        self.expand_button.setText('▲' if shown else '▼')

    def _on_name_changed(self, _text):
        self.nameChanged.emit()

    # ------------------------------------------------------------------
    # 语法检查
    # ------------------------------------------------------------------
    def _check_syntax(self):
        code = self.editor.toPlainText()
        self.syntax_error = None
        if code.strip():
            try:
                compile(code, '<面板代码>', 'exec')
            except SyntaxError as exc:
                self.syntax_error = exc
        if self.runner is None or self.runner.done:
            self._show_syntax_state()

    def _show_syntax_state(self):
        if self.syntax_error is not None:
            self.stats_label.setText('语法错误：%s（第 %s 行）'
                                     % (self.syntax_error.msg, self.syntax_error.lineno))
            self.set_flag('error', True)
        else:
            self.stats_label.setText('待运行 · %d 项' % self.canvas.item_count())
            self.set_flag('error', False)

    # ------------------------------------------------------------------
    # 运行期
    # ------------------------------------------------------------------
    def bind_preview(self, values):
        """运行之前先展示这一轮统一的乱序数据。"""
        self.canvas.bind(values, len(values) or 1)
        self.verdict = None
        self.verdict_kind = ''
        self.set_flag('error', self.syntax_error is not None)
        self.set_flag('winner', False)
        self.ops_label.setText('')
        if self.runner is None or self.runner.done:
            self._show_syntax_state()

    def show_verdict(self, text, kind=''):
        """把结论盖在彩虹条上：名次、Wrong、Syntax Error 或 Error。"""
        self.verdict = text
        self.verdict_kind = kind
        self.canvas.set_verdict(text, kind)
        self.set_flag('error', kind == 'error')

    def detach_runner(self):
        """断开旧线程对画布的引用，防止上一轮的残留线程干扰新一轮的显示。"""
        if self.runner is not None:
            self.runner.canvas = None
        self.runner = None

    def make_runner(self, controller, values):
        self.detach_runner()
        self.verdict = None
        self.verdict_kind = ''
        self.canvas.set_verdict('')
        self.canvas.clear_marks()
        self.editor.set_current_line(0)
        self.runner = AlgorithmRunner(self.code(), values, controller,
                                      canvas=self.canvas, label=self.name())
        self.canvas.bind(self.runner.array.data, max(values) if values else 1)
        self.set_running(True)
        return self.runner

    def set_running(self, running):
        """运行中锁住代码和删除按钮，跑完/停止后一定要解锁。"""
        self.editor.setReadOnly(running)
        self.remove_button.setEnabled(not running)

    def set_current_line(self, line):
        self.editor.set_current_line(line)

    def update_stats(self):
        runner = self.runner
        if runner is None:
            return
        array = runner.array
        self.ops_label.setText(friendly_count(runner.ops))
        if runner.error is not None and not runner.aborted:
            if runner.syntax_error:
                text = '语法错误：%s' % runner.error
            else:
                text = '出错：%s' % runner.error
            self.set_flag('error', True)
        else:
            text = '操作 %d · 读 %d · 写 %d · %.2f s' % (
                runner.ops, array.reads, array.writes, runner.elapsed())
            if runner.done:
                prefix = '已停止 · ' if runner.aborted else '完成 · '
                text = prefix + text
            if runner.warning:
                text += ' · ' + runner.warning
            self.set_flag('error', False)
        self.stats_label.setText(text)

    def set_flag(self, name, value):
        value = bool(value)
        if self._flags.get(name) == value:
            return
        self._flags[name] = value
        self.setProperty(name, value)
        self.style().unpolish(self)
        self.style().polish(self)
