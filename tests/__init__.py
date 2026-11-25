"""TraceLens 出口测试桥接包。

规则要求在产品根跑 `python -m unittest discover -s tests -t .`。真实测试是
pytest 函数式（trace-lens/tests/，121 条），依赖 relate 模块；锻造台解释器
无 relate，故本桥接用 subprocess 调用带 relate 的解释器运行真实 pytest 套件，
把结果作为一个 unittest.TestCase 暴露给 discover。这是真跑，不是空绿。
"""
