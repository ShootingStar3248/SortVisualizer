"""被跟踪的列表：把用户代码对数组的每一次访问都转成一个可视化步骤。

用户代码里拿到的 ``a`` 就是这个类的实例，它对外表现得像一个普通 list：
每次 ``a[i] = x`` 会回调 ``hook.on_write(下标)``，每次 ``a[i]`` 会回调 ``hook.on_read(下标)``。
只按写入计步的话，选择排序这类“先扫描、最后才写一次”的算法会显得像开挂，
所以读和写都算一步，界面才能如实反映每个算法到底做了多少事。
"""


class AbortedError(BaseException):
    """运行被中断。

    刻意继承 ``BaseException``，这样用户代码里常见的
    ``except Exception`` 不会把它吞掉而让停止按钮失效。
    """


class StepLimitError(AbortedError):
    """写入次数超过上限，通常说明算法没有收敛。"""


class _Counted:
    """用来精确统计排序比较次数的包装器。

    真正的排序发生在 C 层（Timsort），字节码计数器看不到它；
    把元素包一层就能数出它到底比较了多少次。
    """

    __slots__ = ('order', 'value', 'hits')

    def __init__(self, order, value, hits):
        self.order = order
        self.value = value
        self.hits = hits

    def __lt__(self, other):
        self.hits[0] += 1
        return self.order < other.order


def _counted_sorted(data, key, reverse, hits):
    if key is None:
        packed = [_Counted(item, item, hits) for item in data]
    else:
        packed = [_Counted(key(item), item, hits) for item in data]
    packed.sort(reverse=reverse)
    return [item.value for item in packed]


class TrackedArray:
    """带读写钩子的 list 替身。"""

    def __init__(self, data, hook=None):
        self._data = list(data)
        self._hook = hook
        self.reads = 0
        self.writes = 0

    # ------------------------------------------------------------------
    # 供界面直接读取的底层列表（只做元素替换，读取是安全的）
    # ------------------------------------------------------------------
    @property
    def data(self):
        return self._data

    @property
    def ops(self):
        return self.reads + self.writes

    def _read(self, index):
        self.reads += 1
        if self._hook is not None:
            self._hook.on_read(index)

    def _write(self, changed):
        self.writes += 1
        if self._hook is not None:
            self._hook.on_write(changed)

    # ------------------------------------------------------------------
    # 序列协议
    # ------------------------------------------------------------------
    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, index):
        if isinstance(index, slice):
            positions = list(range(*index.indices(len(self._data))))
            for position in positions:
                self._read(position)
            return [self._data[position] for position in positions]
        self._read(index)
        return self._data[index]

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            values = list(value)
            targets = list(range(*index.indices(len(self._data))))
            if index.step in (None, 1) and len(values) == len(targets):
                # 长度不变时逐元素写入，归并排序这类整体回填也能逐步看到
                for position, item in zip(targets, values):
                    self._data[position] = item
                    self._write((position,))
            else:
                self._data[index] = values
                self._write(tuple(targets))
            return
        position = index if index >= 0 else index + len(self._data)
        self._data[index] = value
        self._write((position,))

    def __delitem__(self, index):
        del self._data[index]
        self._write(())

    def __contains__(self, value):
        return value in self._data

    def __eq__(self, other):
        if isinstance(other, TrackedArray):
            return self._data == other._data
        return self._data == other

    def __repr__(self):
        return 'TrackedArray(%r)' % (self._data,)

    # ------------------------------------------------------------------
    # 常用列表方法（全部计入步骤）
    # ------------------------------------------------------------------
    def swap(self, i, j):
        """交换两个位置，记 1 步（比 a[i],a[j]=a[j],a[i] 的 2 步更贴近一次交换）。"""
        if i == j:
            return
        self._data[i], self._data[j] = self._data[j], self._data[i]
        self._write((i, j))

    def sort(self, key=None, reverse=False):
        """就地排序。

        真正的排序由 C 层的 Timsort 完成，字节码计数器看不到它，
        所以这里把它的**实际比较次数**折算成操作数上报（1 次比较 = 1 个操作），
        再把结果逐元素回填：读一次、需要时才写一次。
        """
        hits = [0]
        ordered = _counted_sorted(self._data, key, reverse, hits)
        if self._hook is not None:
            self._hook.on_extra_ops(hits[0])
        for position, item in enumerate(ordered):
            if self[position] != item:
                self[position] = item
        return None

    def reverse(self):
        n = len(self._data)
        for i in range(n // 2):
            j = n - 1 - i
            self._data[i], self._data[j] = self._data[j], self._data[i]
            self._write((i, j))

    def append(self, value):
        self._data.append(value)
        self._write((len(self._data) - 1,))

    def extend(self, values):
        for item in values:
            self.append(item)

    def insert(self, index, value):
        self._data.insert(index, value)
        self._write((index,))

    def pop(self, index=-1):
        value = self._data.pop(index)
        self._write(())
        return value

    def remove(self, value):
        self._data.remove(value)
        self._write(())

    def clear(self):
        self._data.clear()
        self._write(())

    def copy(self):
        return self._data.copy()

    def index(self, value, *args):
        return self._data.index(value, *args)

    def count(self, value):
        return self._data.count(value)
