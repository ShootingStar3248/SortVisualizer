# 排序算法可视化对比 · PyQt5

一个把多个排序算法放在**同一拍**上跑给眼睛看的对比工具：每个算法一行彩虹色带，
所有算法每推进相同数量的字节码就一起停一下、一起刷新，于是谁的操作少、谁先排好，
一眼就能看出来。

## 它统计的是什么

「操作」的粒度是 **Python 字节码条数**，不是只看数组读写：

- 用 `sys.settrace` 打开 opcode 事件，只数用户那段代码里的指令；
- `cur = a[i]`、`j -= 1`、`i += 1`、比较运算等中间变量的读写都算进去
  （它们同样要花时间，只数数组访问会让常数大的算法显得比实际便宜）；

所以「冒泡为什么比插入慢这么多」「希尔排序的 gap 序列值不值」这类问题，
在这里可以直接横向比较。

## 功能

- **彩虹色带**：一行等高无缝的色块，颜色只由元素的值决定（左红右紫），方便看数据分布。
- **同拍推进**：所有算法每走一帧（可调，默认 128 条字节码）一起对齐再放行，谁快谁慢一目了然。
- **热度与光标**：被写入的格子瞬间变白再慢慢褪回本色；最近读到的位置在格子底部留一条黄线。
- **代码框**：就地写 `def sort(a): ...` 或直接操作列表 `a` 都行，输入时实时做语法检查；
  左侧行号处有三角形指针标出当前执行到第几行。
- **名次判定**：跑完按结束先后发 1st / 2nd / 3rd…；结果不对写 `Wrong`（不占名次），
  语法错写 `Syntax Error`，运行中抛异常写 `Error`。
- **每块面板独立调高度**：代码框下沿的小横杠，按住上下拖即可，拖到最矮有下限。
- **拖拽换顺序**：按住面板最左侧那三个小点上下拖，实时调整各算法的上下顺序。
- **保存 / 导入**：把当前所有算法和全局设置存成 `.json`，下次读回来；
  仓库里的 `sort-config.json` 就是一个示例配置。

## 运行

```bash
pip install -r requirements.txt
python main.py
```

需要 Python 3.7+ 和 PyQt5（开发环境为 Python 3.10 + PyQt5 5.15）。

## 图标

- `assets/icon.svg` 是图标源文件（深色圆角方块 + 五根渐高的彩虹柱，配色就是彩虹条的取色），改它就够了。
- `assets/icon.ico` 是给 Windows 用的图标文件，由脚本生成。
- 窗口图标不是读外部文件，而是把 SVG 内嵌在 `sortvisual/icon.py` 里、运行时用 QtSvg 现画成
  16…256 多个尺寸，所以程序跑起来一个图标文件都不用带。

改完 SVG 重新生成一次（需要 PyQt5 和 Pillow）：

```bash
python tools/make_icon.py
```

## 目录结构

```
main.py                 程序入口，套上样式表、图标后开窗
requirements.txt        依赖（PyQt5）
sort-config.json        一份示例配置（保存 / 导入 用的是同一套格式）
assets/
    icon.svg            图标源文件（改这个）
    icon.ico            Windows 图标，由 make_icon.py 生成
tools/
    make_icon.py        SVG → ICO + sortvisual/icon.py
sortvisual/
    executor.py         运行线程 + 同步闸门（RunController / AlgorithmRunner）
    tracked_array.py    记账用的数组（读写回调、切片赋值、内置 sort 的比较次数折算）
    panels.py           彩虹条、带行号的代码框、左侧碰撞箱、高度把手、算法面板
    main_window.py      工具栏、面板容器、运行调度、配置读写
    icon.py             内嵌的 SVG 与窗口图标（自动生成）
    theme.py            配色、样式表、Python 语法高亮
```

## 配置格式

`保存` / `导入` 用的就是普通 JSON：

```json
{
  "version": 1,
  "settings": { "size": 500, "seed": 682739, "ops_per_frame": 512, "delay_ms": 0 },
  "algorithms": [ { "name": "冒泡排序", "code": "def sort(a):\n    ...\n" } ]
}
```

- `seed` 相同就生成完全相同的乱序数据，方便公平比较；
- `algorithms` 里的 `code` 就是面板代码框里的原文。

## 已知取舍

- 计步（`sys.settrace`）本身有开销，所以「耗时」只适合同环境横向比较，不等于裸跑时间。
- 同步推进时所有线程每帧对齐一次，元素越多、每帧越小，开销越明显；
  想要快地看完就调大「每帧操作数」。

## 许可证
