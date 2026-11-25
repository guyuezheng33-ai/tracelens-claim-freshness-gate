"""把真实 pytest 套件桥接到 unittest discover，满足产品根出口命令。

不复制、不改写任何测试用例：只调用 trace-lens/tests 下的真实 pytest，
并把 returncode、测试条数、stderr 原样作为断言证据。
"""
import os
import re
import subprocess
import unittest
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = PRODUCT_ROOT / "trace-lens"
FALLBACK_PY = r"C:/Users/Admin/.workbuddy/binaries/python/envs/default/Scripts/python.exe"


def _python_with_relate() -> str:
    """优先用调用方指定的解释器（award-verify.sh 的 TRACELENS_PYTHON），
    否则用已验证装有 relate 的绝对路径；找不到就明确失败，绝不空绿。"""
    for cand in (os.environ.get("TRACELENS_PYTHON"), FALLBACK_PY):
        if not cand:
            continue
        if not Path(cand).is_file():
            continue
        probe = subprocess.run(
            [cand, "-c", "import relate, pytest"],
            capture_output=True, text=True, check=False,
        )
        if probe.returncode == 0:
            return cand
    raise RuntimeError(
        "no python with relate+pytest found; set TRACELENS_PYTHON. "
        "Refusing to report a green suite without running it."
    )


class TestRealPytestSuite(unittest.TestCase):
    def test_all_pytest_cases_pass(self):
        py = _python_with_relate()
        proc = subprocess.run(
            [py, "-m", "pytest", "tests", "-q"],
            cwd=str(PROJECT_DIR), capture_output=True, text=True, check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"(\d+)\s+passed", out)
        count = int(m.group(1)) if m else 0
        self.assertEqual(proc.returncode, 0, "真实 pytest 套件失败：\n" + out[-4000:])
        self.assertGreater(count, 0, "pytest 报绿但没有跑任何测试（疑似空绿）：\n" + out[-2000:])


if __name__ == "__main__":
    unittest.main()
