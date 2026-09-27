"""主窗口：控制条 + 若干算法行 + 运行调度。

启动时只有一个默认的「排序算法」面板（带 sort 骨架），直接改代码即可；
所有算法名占同一列宽（取最长者），保证彩虹条左右对齐。
按住面板左侧的小点上下拖，可以调整各块面板的先后顺序。
"""

import json
import random

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPushButton,
                             QScrollArea, QSlider, QSpinBox, QStatusBar,
                             QVBoxLayout, QWidget)

from .executor import SIM_DECAY, TICK_DECAY, RunController
from .panels import DEFAULT_CODE, DEFAULT_NAME, AlgorithmPanel

TICK_INTERVAL_MS = 33
MAX_OPS = 100_000_000  # 单个算法的字节码条数上限，防止写错的代码一直跑
CONFIG_VERSION = 1


def ordinal(number):
    """1 -> 1st，2 -> 2nd，11 -> 11th。"""
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return '%d%s' % (number, suffix)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('排序算法可视化对比 · PyQt5')
        self.resize(1280, 720)

        self._panels = []
        self._runners = []
        self._controller = None
        self._running = False
        self._values = []
        self._rank = 0
        self._ranking = []

        self._ticker = QTimer(self)
        self._ticker.setInterval(TICK_INTERVAL_MS)
        self._ticker.timeout.connect(self._on_tick)

        self._build_ui()
        first = self._add_panel()      # 不预置算法，给一个空白的自己写
        first.set_expanded(True)
        self._reset_data()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_ui(self):
        container = QWidget()
        self.setCentralWidget(container)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(12, 12, 12, 6)
        outer.setSpacing(10)
        outer.addWidget(self._build_toolbar())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName('panelHost')
        self.panel_layout = QVBoxLayout(host)
        self.panel_layout.setContentsMargins(0, 0, 8, 0)
        self.panel_layout.setSpacing(8)
        self.panel_layout.addStretch(1)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll, 1)

        self.setStatusBar(QStatusBar())

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('toolbar')
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel('数据量'))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 3000)
        self.size_spin.setValue(80)
        self.size_spin.setToolTip('所有算法共用的数组长度（彩虹条的格子数）')
        self.size_spin.valueChanged.connect(self._reset_data)
        layout.addWidget(self.size_spin)

        layout.addWidget(QLabel('随机种子'))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.seed_spin.setToolTip('相同种子生成完全相同的乱序数组，方便公平比较')
        self.seed_spin.valueChanged.connect(self._reset_data)
        layout.addWidget(self.seed_spin)
        self.reseed_button = QPushButton('换一组')
        self.reseed_button.setToolTip('随机换一个种子，重新生成乱序数据')
        self.reseed_button.clicked.connect(self._reseed)
        layout.addWidget(self.reseed_button)

        layout.addSpacing(6)
        layout.addWidget(QLabel('每帧操作数'))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 20000)
        self.step_spin.setValue(128)
        self.step_spin.setSingleStep(32)
        self.step_spin.setMinimumWidth(76)
        self.step_spin.setToolTip(
            '一帧推进多少条 Python 字节码（数组访问、中间变量读写、自增、比较全都算）。\n'
            '1 = 一条字节码一帧，细到能看清每一步，但只适合几十个元素的小数组；\n'
            '128（默认）动画流畅；想更快就继续调大。统计数字不受影响。')
        layout.addWidget(self.step_spin)

        layout.addSpacing(6)
        layout.addWidget(QLabel('步进延时'))
        self.delay_slider = QSlider(Qt.Horizontal)
        self.delay_slider.setRange(0, 200)
        self.delay_slider.setValue(0)
        self.delay_slider.setFixedWidth(100)
        self.delay_slider.setToolTip('每帧之间的停顿；0 为全速，调大可以慢慢看每一步')
        self.delay_slider.valueChanged.connect(self._update_delay_label)
        layout.addWidget(self.delay_slider)
        self.delay_label = QLabel()
        self.delay_label.setObjectName('field')
        layout.addWidget(self.delay_label)
        self._update_delay_label()

        layout.addSpacing(6)
        layout.addStretch(1)
        self.import_button = QPushButton('导入')
        self.import_button.setToolTip('从 .json 读回算法和全局设置')
        self.import_button.clicked.connect(self._import_config)
        layout.addWidget(self.import_button)
        self.export_button = QPushButton('保存')
        self.export_button.setToolTip('把当前所有算法和全局设置存成 .json')
        self.export_button.clicked.connect(self._export_config)
        layout.addWidget(self.export_button)
        self.add_button = QPushButton('+ 添加')
        self.add_button.setToolTip('新增一个算法行（默认代码是 def sort(a): pass）')
        self.add_button.clicked.connect(self._add_blank_panel)
        layout.addWidget(self.add_button)
        self.reset_button = QPushButton('重置')
        self.reset_button.clicked.connect(self._reset_data)
        layout.addWidget(self.reset_button)
        self.start_button = QPushButton('开始')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self._toggle_run)
        layout.addWidget(self.start_button)
        return bar

    def _update_delay_label(self):
        value = self.delay_slider.value()
        self.delay_label.setText('全速' if value == 0 else '%d ms' % value)

    # ------------------------------------------------------------------
    # 算法行管理
    # ------------------------------------------------------------------
    def _add_panel(self, name=None, code=None):
        panel = AlgorithmPanel(name or DEFAULT_NAME,
                              DEFAULT_CODE if code is None else code)
        panel.removeRequested.connect(self._remove_panel)
        panel.nameChanged.connect(self._relayout_names)
        panel.grip.dragStarted.connect(self._begin_panel_drag)
        panel.grip.dragMoved.connect(self._move_panel_drag)
        panel.grip.dragFinished.connect(self._end_panel_drag)
        self.panel_layout.insertWidget(self.panel_layout.count() - 1, panel)
        self._panels.append(panel)
        panel.bind_preview(self._values)
        self._relayout_names()
        return panel

    def _add_blank_panel(self):
        panel = self._add_panel()
        panel.set_expanded(True)
        return panel

    # ------------------------------------------------------------------
    # 左边的小点：按住拖，改面板上下顺序
    # ------------------------------------------------------------------
    def _host_widget(self):
        """装面板的那个容器，用来把鼠标全局坐标换算成面板坐标。"""
        return self.panel_layout.parentWidget()

    def _begin_panel_drag(self, panel):
        panel.setProperty('dragging', True)
        panel.style().unpolish(panel)
        panel.style().polish(panel)
        panel.raise_()

    def _move_panel_drag(self, panel, global_pos):
        """鼠标拖到哪，就把面板插到哪个位置（实时预览新顺序）。"""
        if panel not in self._panels:
            return
        host = self._host_widget()
        if host is None:
            return
        cursor_y = host.mapFromGlobal(global_pos).y()
        target = 0
        for other in self._panels:
            if other is panel:
                continue
            if cursor_y > other.y() + other.height() / 2.0:
                target += 1
        if target == self._panels.index(panel):
            return
        self._panels.remove(panel)
        self._panels.insert(target, panel)
        self._apply_panel_order()

    def _end_panel_drag(self, panel):
        panel.setProperty('dragging', False)
        panel.style().unpolish(panel)
        panel.style().polish(panel)
        self._show_status('顺序已调整：' + ' → '.join(item.name() for item in self._panels))

    def _apply_panel_order(self):
        """按 self._panels 的顺序重排控件（末尾那个 spring 始终留在最后）。"""
        for panel in self._panels:
            self.panel_layout.removeWidget(panel)
        for index, panel in enumerate(self._panels):
            self.panel_layout.insertWidget(index, panel)

    def _remove_panel(self, panel, force=False):
        if panel not in self._panels:
            return
        if self._running and not force:
            return
        self._panels.remove(panel)
        panel.detach_runner()
        self.panel_layout.removeWidget(panel)
        panel.setParent(None)
        panel.deleteLater()
        self._relayout_names()

    def _relayout_names(self):
        """算法名列宽取所有名字里最长的，让所有彩虹条左右对齐、长度一致。"""
        if not self._panels:
            return
        width = max(panel.name_width_hint() for panel in self._panels)
        for panel in self._panels:
            panel.set_name_width(width)

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def _reseed(self):
        self.seed_spin.setValue(random.randint(0, 999999))

    def _reset_data(self):
        if self._running:
            return
        self._stop_run(None)
        size = self.size_spin.value()
        rng = random.Random(self.seed_spin.value())
        self._values = list(range(1, size + 1))
        rng.shuffle(self._values)
        self._rank = 0
        self._ranking = []
        for panel in self._panels:
            panel.bind_preview(self._values)
        self._show_status('已生成 %d 项数据（种子 %d）' % (size, self.seed_spin.value()))

    # ------------------------------------------------------------------
    # 运行调度
    # ------------------------------------------------------------------
    def _toggle_run(self):
        if self._running:
            self._stop_run('已停止')
        else:
            self._start_run()

    def _collect_runnable(self):
        """有代码、且语法没问题的面板；语法错的直接在条上写 Syntax Error。"""
        panels = []
        for panel in self._panels:
            if not panel.code().strip():
                panel.show_verdict('')      # 清掉上一轮残留的蒙版
                continue
            if panel.syntax_error is not None:
                panel.show_verdict('Syntax Error', 'error')
                panel.update_stats()
                continue
            panels.append(panel)
        return panels

    def _start_run(self):
        if len(self._values) < 2:
            QMessageBox.information(self, '提示', '数据量太小了。')
            return
        panels = self._collect_runnable()
        if not panels:
            QMessageBox.information(self, '提示',
                                    '先写一段排序代码（就地操作列表 a），再点开始。')
            return

        for panel in self._panels:
            panel.set_flag('winner', False)
            panel.set_current_line(0)
        self._rank = 0
        self._ranking = []

        controller = RunController(sync=True,
                                   max_ops=MAX_OPS,
                                   ops_per_frame=self.step_spin.value(),
                                   parent=self)
        controller.renderRequested.connect(self._on_render_requested)
        self._controller = controller

        runners = [panel.make_runner(controller, list(self._values)) for panel in panels]
        for _ in runners:
            controller.register()
        for runner in runners:
            runner.start()
        self._runners = runners

        self._running = True
        self._ticker.start()
        self._set_controls_enabled(False)
        self.start_button.setText('停止')
        self._show_status('运行中…（同步逐笔对比，每帧 %d 条字节码）'
                          % controller.ops_per_frame)

    def _on_render_requested(self, event):
        """所有算法都走完这一帧了：褪一层热、重绘，然后放行下一帧。"""
        self._decay_heat(SIM_DECAY)
        for panel in self._panels:
            runner = panel.runner
            if runner is not None and runner.consume_dirty():
                panel.canvas.update()
        if self._controller is not None:
            self._controller.ops_per_frame = max(1, self.step_spin.value())
        delay = self.delay_slider.value()
        if delay > 0:
            QTimer.singleShot(delay, event.set)
        else:
            event.set()

    def _on_tick(self):
        if self._running:
            for panel in self._panels:
                runner = panel.runner
                if runner is None:
                    continue
                panel.update_stats()
                panel.set_current_line(runner.current_line)
                if runner.consume_dirty():
                    panel.canvas.update()
            self._assign_verdicts()
            if all(panel.runner.done for panel in self._panels if panel.runner is not None):
                self._finish_run()
            if self._running:
                return  # 同步推进时热度跟着每一帧走，不在这里褪
        self._decay_heat(TICK_DECAY)
        if not self._any_heat():
            self._ticker.stop()

    def _decay_heat(self, step):
        for panel in self._panels:
            if panel.canvas.cool_down(step):
                panel.canvas.update()

    def _any_heat(self):
        return any(panel.canvas.is_hot() for panel in self._panels)

    def _assign_verdicts(self):
        """按结束先后发名次：结果不对的写 Wrong，且不占名次。"""
        waiting = [panel for panel in self._panels
                   if panel.runner is not None and panel.runner.done
                   and panel.verdict is None]
        if not waiting:
            return
        waiting.sort(key=lambda item: item.runner.end_time)
        for panel in waiting:
            runner = panel.runner
            if runner.aborted:
                continue
            if runner.error is not None:
                panel.show_verdict('Syntax Error' if runner.syntax_error else 'Error', 'error')
            elif runner.correct:
                self._rank += 1
                panel.show_verdict(ordinal(self._rank), 'ok')
                panel.set_flag('winner', self._rank == 1)
                self._ranking.append((panel.verdict, panel.name()))
            else:
                panel.show_verdict('Wrong', 'wrong')
            panel.update_stats()

    def _release_panels(self):
        for panel in self._panels:
            panel.set_running(False)
            panel.update_stats()

    def _stop_run(self, message):
        if self._controller is not None:
            self._controller.stop()
            for runner in self._runners:
                runner.join(0.3)
        self._controller = None
        self._runners = []
        self._running = False
        self.start_button.setText('开始')
        self._set_controls_enabled(True)
        self._release_panels()
        if message:
            self._show_status(message)

    def _finish_run(self):
        self._running = False
        self._set_controls_enabled(True)
        self.start_button.setText('开始')
        self._assign_verdicts()
        self._release_panels()
        self._controller = None   # 之后热度交给计时器接着褪

        messages = []
        if self._ranking:
            messages.append('名次：' + ' · '.join('%s %s' % pair for pair in self._ranking))
        wrong = [panel.name() for panel in self._panels if panel.verdict_kind == 'wrong']
        if wrong:
            messages.append('结果不对：%s' % '、'.join(wrong))
        syntax = [panel.name() for panel in self._panels if panel.verdict == 'Syntax Error']
        if syntax:
            messages.append('语法错误：%s' % '、'.join(syntax))
        broken = [panel.name() for panel in self._panels if panel.verdict == 'Error']
        if broken:
            messages.append('运行出错：%s' % '、'.join(broken))
        if not messages:
            messages.append('没有任何算法跑出结果')
        self._show_status('完成 · ' + ' · '.join(messages))

    def _set_controls_enabled(self, enabled):
        for widget in (self.size_spin, self.seed_spin, self.reseed_button,
                       self.add_button, self.reset_button,
                       self.import_button, self.export_button):
            widget.setEnabled(enabled)

    def _show_status(self, text):
        self.statusBar().showMessage(text)

    # ------------------------------------------------------------------
    # 配置的保存 / 导入
    # ------------------------------------------------------------------
    def to_config(self):
        """把当前所有算法和全局设置打包成能直接 json.dump 的字典。"""
        return {
            'version': CONFIG_VERSION,
            'settings': {
                'size': self.size_spin.value(),
                'seed': self.seed_spin.value(),
                'ops_per_frame': self.step_spin.value(),
                'delay_ms': self.delay_slider.value(),
            },
            'algorithms': [{'name': panel.name(), 'code': panel.code()}
                           for panel in self._panels],
        }

    def apply_config(self, data):
        """读回配置；格式不对就抛 ValueError / TypeError。"""
        if not isinstance(data, dict):
            raise ValueError('顶层不是 JSON 对象')
        algorithms = data.get('algorithms')
        if algorithms is None:
            raise ValueError('缺少 algorithms 字段')
        if not isinstance(algorithms, list):
            raise ValueError('algorithms 必须是数组')
        settings = data.get('settings')
        if not isinstance(settings, dict):
            settings = {}

        # 先把内容全部校验一遍，确认可用再动手清空现有面板
        entries = []
        for item in algorithms:
            if not isinstance(item, dict):
                continue
            entries.append((str(item.get('name') or '算法'), str(item.get('code') or '')))
        if not entries:
            raise ValueError('algorithms 里没有可用的算法')

        if self._running:
            self._stop_run(None)
        for panel in list(self._panels):
            self._remove_panel(panel, force=True)
        self._apply_settings(settings)
        for name, code in entries:
            self._add_panel(name, code)
        self._reset_data()

    def _apply_settings(self, settings):
        for key, widget in (('size', self.size_spin), ('seed', self.seed_spin),
                            ('ops_per_frame', self.step_spin)):
            value = settings.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))
        delay = settings.get('delay_ms')
        if isinstance(delay, int) and not isinstance(delay, bool):
            self.delay_slider.setValue(max(self.delay_slider.minimum(),
                                           min(self.delay_slider.maximum(), delay)))

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存配置', 'sort-config.json',
                                              '配置文件 (*.json)')
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(self.to_config(), handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, '保存失败', '这个文件写不进去：%s' % exc)
            return
        self._show_status('已保存 %d 个算法到 %s' % (len(self._panels), path))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入配置', '', '配置文件 (*.json)')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '读取失败', '这个文件读不出来：%s' % exc)
            return
        try:
            self.apply_config(data)
        except (ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, '配置格式不对', str(exc))
            return
        self._show_status('已导入 %s（%d 个算法）' % (path, len(self._panels)))

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._stop_run(None)
        super().closeEvent(event)
