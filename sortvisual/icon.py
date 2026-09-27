"""窗口图标：内嵌 assets/icon.svg 的内容，运行时用 QtSvg 现画。

这个文件是 tools/make_icon.py 生成的，别手改；
改图标请改 assets/icon.svg，然后重新跑一次：

    python tools/make_icon.py
"""

ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <title>排序算法可视化对比</title>
  <desc>深色圆角底：五根渐高的彩虹柱，配色取自程序彩虹条的红→紫映射。</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.55" y2="1">
      <stop offset="0" stop-color="#1d2637"/>
      <stop offset="1" stop-color="#0a0c12"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="54" fill="url(#bg)"/>
  <rect x="10.5" y="10.5" width="235" height="235" rx="51.5" fill="none" stroke="#313d57" stroke-width="5"/>
  <g>
    <rect x="22"  y="148" width="32" height="54"  rx="10" fill="#fa2626"/>
    <rect x="67"  y="122" width="32" height="80"  rx="10" fill="#dffa26"/>
    <rect x="112" y="96"  width="32" height="106" rx="10" fill="#26fa5b"/>
    <rect x="157" y="70"  width="32" height="132" rx="10" fill="#26aafa"/>
    <rect x="202" y="44"  width="32" height="158" rx="10" fill="#9026fa"/>
  </g>
</svg>
"""

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
