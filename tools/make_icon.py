"""图标工具：assets/icon.svg → assets/icon.ico + sortvisual/icon.py。

    python tools/make_icon.py

改图标只要改 assets/icon.svg，然后跑一次这个脚本：
- 生成多尺寸的 Windows 图标 assets/icon.ico（给 PyInstaller 的 --icon 用）；
- 把同一份 SVG 内嵌进 sortvisual/icon.py，程序运行时直接画成窗口图标，
  这样打包时不用带任何外部资源文件。

依赖：PyQt5（QtSvg 渲染）+ Pillow（写 .ico）。
"""

import os
import sys

SIZES = (256, 128, 64, 48, 32, 24, 16)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_PATH = os.path.join(ROOT, 'assets', 'icon.svg')
ICO_PATH = os.path.join(ROOT, 'assets', 'icon.ico')
PY_PATH = os.path.join(ROOT, 'sortvisual', 'icon.py')

MODULE_TEMPLATE = '''"""窗口图标：内嵌 assets/icon.svg 的内容，运行时用 QtSvg 现画。

这个文件是 tools/make_icon.py 生成的，别手改；
改图标请改 assets/icon.svg，然后重新跑一次：

    python tools/make_icon.py
"""

ICON_SVG = """\\
{svg}"""

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def window_icon():
    """返回多尺寸的 QIcon；没有 QtSvg 或 SVG 坏了就返回空 QIcon，不影响程序启动。"""
    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QIcon, QImage, QPainter, QPixmap

    icon = QIcon()
    try:
        from PyQt5.QtSvg import QSvgRenderer
    except ImportError:
        return icon

    renderer = QSvgRenderer(ICON_SVG.encode('utf-8'))
    if not renderer.isValid():
        return icon

    for size in ICON_SIZES:
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon
'''


def main():
    with open(SVG_PATH, 'r', encoding='utf-8') as handle:
        svg = handle.read()

    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtWidgets import QApplication
    from PIL import Image

    app = QApplication.instance() or QApplication(sys.argv)   # QImage 需要先有 QApplication

    renderer = QSvgRenderer(SVG_PATH)
    if not renderer.isValid():
        raise SystemExit('SVG 读不出来：%s' % SVG_PATH)

    frames = []
    for size in sorted(SIZES):
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        buffer = image.bits()
        buffer.setsize(image.byteCount())
        frames.append(Image.frombytes('RGBA', (size, size), bytes(buffer),
                                      'raw', 'BGRA'))

    frames[-1].save(ICO_PATH, format='ICO',
                    sizes=[(size, size) for size in sorted(SIZES)])
    print('已写出 %s（%d 个尺寸）' % (ICO_PATH, len(SIZES)))

    with open(PY_PATH, 'w', encoding='utf-8') as handle:
        handle.write(MODULE_TEMPLATE.replace('{svg}', svg))
    print('已写出 %s' % PY_PATH)


if __name__ == '__main__':
    main()
