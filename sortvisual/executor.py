"""运行用户代码的工作线程，以及让所有算法“同拍推进”的闸门。

“操作”的粒度是 **Python 字节码条数**：用 ``sys.settrace`` 打开 opcode 事件，
只统计用户自己那段代码里的指令。这样 ``cur = a[i]``、``j -= 1``、``i += 1``、
比较运算等中间变量的读写都会被算进去——毕竟它们同样要花时间，
只数数组访问的话，冒泡这种常数大的算法会显得比实际便宜。
"""

import sys
import threading
import time
import traceback

from PyQt5.QtCore import QObject, pyqtSignal

from .tracked_array import AbortedError, StepLimitError, TrackedArray

ENTRY_NAMES = ('sort', 'main')

READ_HEAT = 0.0          # 读取只动光标，不加热度（想让扫描也留亮痕可以改成 0.35）
WRITE_HEAT = 1.0         # 被写入一下直接变白
SIM_DECAY = 1 / 45.0     # 每推进一帧（模拟速度）掉多少热度
TICK_DECAY = 1 / 14.0    # 空闲时每 33ms 掉多少热度（跑完之后继续褪）


class RunController(QObject):
    """一次对比运行的调度中心。

    同步模式下每个算法每执行 ``ops_per_frame`` 条字节码，就在闸门前等一次：
    等所有算法都走完这一帧、界面重绘完成之后再一起放行。
    于是所有彩虹条严格同拍，谁的操作少谁就先排好。
    """

    # 参数是需要被 set() 的 threading.Event，界面重绘完成后放行
    renderRequested = pyqtSignal(object)

    def __init__(self, sync=True, max_ops=100_000_000, ops_per_frame=128, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._alive = 0
        self._arrived = 0
        self.sync = bool(sync)
        self.max_ops = int(max_ops)
        self.ops_per_frame = max(1, int(ops_per_frame))

    # ------------------------------------------------------------------
    # 工作线程侧
    # ------------------------------------------------------------------
    def register(self):
        """在启动线程之前登记，闸门要提前知道这一帧有多少人。"""
        with self._lock:
            self._alive += 1

    @property
    def stopped(self):
        return self._stop.is_set()

    def check(self, ops=None):
        """廉价的中断检查。"""
        if self._stop.is_set():
            raise AbortedError('已停止')
        if ops is not None and ops > self.max_ops:
            raise StepLimitError('操作数超过上限 %d 次，已中断' % self.max_ops)

    def worker_done(self):
        """某个算法结束（正常、出错或被停止）后调用。

        活着的人变少了，原本凑不齐的闸门要立刻放行，否则剩下的算法会一直卡住。
        """
        event = None
        with self._lock:
            if self._alive > 0:
                self._alive -= 1
            if self._alive > 0 and self._arrived >= self._alive:
                self._arrived = 0
                event = self._wake
        if event is not None:
            self.renderRequested.emit(event)

    def step(self, ops):
        """一个算法走完了这一帧，来这里与其他算法对齐。"""
        if self._stop.is_set():
            raise AbortedError('已停止')
        if ops > self.max_ops:
            raise StepLimitError('操作数超过上限 %d 次，已中断' % self.max_ops)
        if not self.sync or self._alive <= 0:
            return
        with self._lock:
            if self._stop.is_set():
                raise AbortedError('已停止')
            if self._arrived == 0:
                self._wake = threading.Event()  # 新一帧
            self._arrived += 1
            event = self._wake
            release = self._arrived >= self._alive
            if release:
                self._arrived = 0
        if release:
            self.renderRequested.emit(event)
        if not event.wait(20.0) and not self._stop.is_set():
            raise AbortedError('等待界面重绘超时，已中断')

    def stop(self):
        self._stop.set()
        with self._lock:
            self._wake.set()  # 唤醒所有卡在闸门前的线程


class AlgorithmRunner(threading.Thread):
    """在独立线程里执行一段用户排序代码，并逐条字节码计步。"""

    def __init__(self, code, values, controller, canvas=None, label=''):
        super().__init__(daemon=True, name='sort-runner-%s' % (label or 'code'))
        self.code = code
        self.label = label
        self.canvas = canvas
        self.controller = controller
        self.array = TrackedArray(values, hook=self)
        self.filename = '<%s>' % (label or 'code')
        self.expected = sorted(values)

        self.ops = 0                # 用户代码执行过的字节码条数
        self.current_line = 0       # 当前执行到第几行（供代码框指针用）
        self.error = None
        self.aborted = False
        self.syntax_error = False
        self.warning = None
        self.start_time = 0.0
        self.end_time = 0.0
        self.dirty = False          # 有新的标记等待重绘
        self._accept_marks = True
        self._pending = 0           # 本帧已执行条数
        self._cursor = None         # 本帧最后读取的位置

    @property
    def correct(self):
        """结果是原数组的正确排序（既是升序，也没有丢/多元素）。"""
        return list(self.array.data) == self.expected

    # ------------------------------------------------------------------
    # 字节码计数：只统计用户代码所在的帧
    # ------------------------------------------------------------------
    def _trace_opcode(self, frame, event, arg):
        if event == 'opcode':
            self.ops += 1
            self._pending += 1
            if self._pending >= self.controller.ops_per_frame:
                self._flush_frame(frame)
        return self._trace_opcode

    def _trace_call(self, frame, event, arg):
        if event == 'call' and frame.f_code.co_filename == self.filename:
            frame.f_trace_opcodes = True
            frame.f_trace_lines = False   # 不需要行事件，省一半开销
            return self._trace_opcode
        return None

    # ------------------------------------------------------------------
    # TrackedArray 的回调（都在工作线程里执行）
    # ------------------------------------------------------------------
    def on_read(self, index):
        if self._accept_marks:
            self._cursor = index
        if READ_HEAT <= 0.0:
            return          # 默认不给读取加热度，光标已经够看
        canvas = self.canvas
        if canvas is not None:
            canvas.add_heat((index,), READ_HEAT)

    def on_write(self, changed):
        canvas = self.canvas
        if canvas is not None:
            canvas.add_heat(changed, WRITE_HEAT)

    def on_extra_ops(self, count):
        """替 C 层的工作补记操作数（比如 Timsort 的比较次数）。

        这些比较在 C 代码里发生，trace 数不到字节码，只能按次数折算。
        """
        if count <= 0:
            return
        self.ops += count
        self._pending += count
        if self._pending >= self.controller.ops_per_frame:
            self._flush_frame()

    def _flush_frame(self, frame=None):
        """这一帧走完：记下当前行号、把光标交给画布，然后去闸门等大家。"""
        self._pending = 0
        if frame is not None:
            # 循环末尾那种编译器生成的隐式跳转（JUMP_ABSOLUTE 之类）没有行号信息，
            # 这时 frame.f_lineno 是 None，沿用上一次的行号就好。
            lineno = frame.f_lineno
            if lineno is not None:
                self.current_line = lineno
        if self._accept_marks:
            if self.canvas is not None and self._cursor is not None:
                self.canvas.cursor = self._cursor
            self.dirty = True
        self._cursor = None
        self.controller.step(self.ops)

    # ------------------------------------------------------------------
    def elapsed(self):
        if not self.start_time:
            return 0.0
        return (self.end_time or time.perf_counter()) - self.start_time

    @property
    def done(self):
        return self.end_time > 0.0

    def consume_dirty(self):
        """界面线程调用：取走“待重绘”标记。"""
        if self.dirty:
            self.dirty = False
            return True
        return False

    def run(self):
        self.start_time = time.perf_counter()
        sys.settrace(self._trace_call)
        try:
            compiled = compile(self.code, self.filename, 'exec')
            namespace = {
                '__name__': '__main__',
                'a': self.array,
                'arr': self.array,
                'lst': self.array,
            }
            exec(compiled, namespace)
            entry = None
            for key in ENTRY_NAMES:
                candidate = namespace.get(key)
                if callable(candidate):
                    entry = candidate
                    break
            if entry is not None:
                entry(self.array)
            if namespace.get('a') is not self.array:
                self.warning = '代码把 a 重新赋值了，看到的可能不是真实结果'
        except StepLimitError as exc:
            self.error = str(exc)
        except SyntaxError as exc:
            self.syntax_error = True
            self.error = '第 %s 行：%s' % (exc.lineno, exc.msg)
        except AbortedError as exc:
            self.aborted = True
            self.error = str(exc) or '已停止'
        except BaseException:
            lines = traceback.format_exc(limit=6).strip().splitlines()
            self.error = lines[-1] if lines else '运行出错'
        finally:
            sys.settrace(None)
            self.end_time = time.perf_counter()
            if self.canvas is not None and self._cursor is not None:
                self.canvas.cursor = self._cursor
            self.dirty = True
            self._cursor = None
            self._accept_marks = False
            self.controller.worker_done()
