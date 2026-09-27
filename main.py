"""排序算法可视化对比 · 程序入口。

运行：python main.py
"""

import sys

from PyQt5.QtWidgets import QApplication

from sortvisual.icon import window_icon
from sortvisual.main_window import MainWindow
from sortvisual.theme import APP_QSS


def _set_windows_app_id():
    """让 Windows 任务栏认我们自己的图标，而不是 python.exe 的。"""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SortVisualizer')
    except (AttributeError, OSError):
        pass


def main():
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName('排序算法可视化对比')
    app.setWindowIcon(window_icon())
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
