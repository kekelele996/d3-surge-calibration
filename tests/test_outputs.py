"""水锤瞬变仿真的验收测试。

每个 test_ 的 docstring 用「」引用题面原句；分支与异常处理放在模块级辅助函数里。
被测入口一律通过 run_candidate() 以 runner 身份、干净环境变量、独立进程组运行。
期望值由 tests/expected.json 给出，来自独立的 320 格特征线复算，不由候选程序生成。
"""

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

ENTRY = "/app/surge.py"
PYTHON = "/usr/local/bin/python3"
CANDIDATE_USER = "runner"
CANDIDATE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/home/runner",
    "LANG": "C.UTF-8",
    "TZ": "UTC",
}
CALL_TIMEOUT_SEC = 120
DATA = Path(__file__).resolve().parent / "data"
EXPECTED = json.loads((Path(__file__).resolve().parent / "expected.json").read_text(encoding="utf-8"))
CACHE = {}


def run_candidate(*args, timeout=CALL_TIMEOUT_SEC):
    """以 runner 身份运行候选入口；超时结束整个进程组并抛出 TimeoutError。"""
    as_root = os.getuid() == 0
    proc = subprocess.Popen(
        [PYTHON, ENTRY, *[str(a) for a in args]],
        cwd="/app",
        env=CANDIDATE_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        user=CANDIDATE_USER if as_root else None,
        group=CANDIDATE_USER if as_root else None,
        extra_groups=[] if as_root else None,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise TimeoutError(f"{ENTRY} 超过 {timeout}s")
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def run_case(case_path, cache_key):
    """在可写的临时目录里运行一个算例，返回读取后的报告。"""
    if cache_key in CACHE:
        return CACHE[cache_key]
    folder = Path(tempfile.mkdtemp(prefix="surge-"))
    folder.chmod(0o777)
    report = folder / "report.json"
    proc = run_candidate(case_path, report)
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr[-800:]}"
    payload = json.loads(report.read_text(encoding="utf-8"))
    CACHE[cache_key] = payload
    return payload


def visible(name):
    return run_case(Path("/app/cases") / f"{name}.json", f"visible:{name}")


def hidden(name):
    return run_case(DATA / f"{name}.json", f"hidden:{name}")


def expected(name):
    return EXPECTED[name]


def arrival_time(times, values, threshold=0.20):
    """第一个偏离初始水头超过 threshold 的采样时刻。"""
    v0 = values[0]
    for t, v in zip(times, values):
        if abs(v - v0) > threshold:
            return float(t)
    return None


def max_abs_diff(left, right):
    return max(abs(a - b) for a, b in zip(left, right))


def run_fresh(case_path):
    """不复用缓存地运行一次，用于重复性检查。"""
    folder = Path(tempfile.mkdtemp(prefix="surge-fresh-"))
    folder.chmod(0o777)
    report = folder / "report.json"
    proc = run_candidate(case_path, report)
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr[-800:]}"
    return json.loads(report.read_text(encoding="utf-8"))


# ---------- gate：入口与输出契约，不计分 ----------

def test_output_schema():
    """「报告里的字段集合恰好是六项，不能多也不能少」「新算例不一定带这段记录」"""
    got = visible("steady")
    assert set(got) == {
        "case_id",
        "wave_speed_m_s",
        "friction_factor",
        "peak_head_m",
        "final_head_m",
        "station_heads",
    }
    assert isinstance(got["wave_speed_m_s"], (int, float))
    assert isinstance(got["friction_factor"], (int, float))
    assert isinstance(got["peak_head_m"], (int, float))
    assert isinstance(got["final_head_m"], (int, float))
    assert set(got["station_heads"]) == {"S1", "S2"}
    assert len(got["station_heads"]["S1"]) > 100
    assert len(got["station_heads"]["S2"]) == len(got["station_heads"]["S1"])


def test_wrong_argument_count_exits_2():
    """「参数个数不对时退出码为 2，不写报告文件」"""
    proc = run_candidate()
    assert proc.returncode == 2


def test_repeatable_output():
    """「同一份输入重复运行，结果必须一致」"""
    first = visible("steady")
    second = run_fresh("/app/cases/steady.json")
    assert first == second


# ---------- 难点 1：锚固段的波速 ----------

def test_wave_speed_anchored_a():
    """「这条线一段埋在锚固墩里，一段装了伸缩节」"""
    got = hidden("anchored_1")
    want = expected("anchored_1")["wave_speed_m_s"]
    assert abs(got["wave_speed_m_s"] - want) / want < 0.01


def test_wave_speed_anchored_b():
    """「这条线一段埋在锚固墩里，一段装了伸缩节」"""
    got = hidden("anchored_2")
    want = expected("anchored_2")["wave_speed_m_s"]
    assert abs(got["wave_speed_m_s"] - want) / want < 0.01


def test_wave_speed_anchored_c():
    """「这条线一段埋在锚固墩里，一段装了伸缩节」"""
    got = hidden("anchored_3")
    want = expected("anchored_3")["wave_speed_m_s"]
    assert abs(got["wave_speed_m_s"] - want) / want < 0.01


# ---------- 难点 2：粗糙管的沿程摩阻 ----------

def test_friction_rough_a():
    """「旧钢管这段粗糙度 0.15 到 0.25 mm」"""
    got = hidden("rough_1")
    want = expected("rough_1")["friction_factor"]
    assert abs(got["friction_factor"] - want) / want < 0.03


def test_friction_rough_b():
    """「旧钢管这段粗糙度 0.15 到 0.25 mm」"""
    got = hidden("rough_2")
    want = expected("rough_2")["friction_factor"]
    assert abs(got["friction_factor"] - want) / want < 0.03


def test_rough_steady_head():
    """「旧钢管这段粗糙度 0.15 到 0.25 mm」"""
    got = hidden("rough_3")
    want = expected("rough_3")["station_heads"]["S1"][0]
    assert abs(got["station_heads"]["S1"][0] - want) <= 0.20


# ---------- 难点 3：快速关阀时的调压塔 ----------

def test_tank_peak_fast():
    """「调压塔气室只有几十升，关阀不到 1 s」"""
    got = hidden("tank_1")
    want = expected("tank_1")["peak_head_m"]
    assert abs(got["peak_head_m"] - want) <= 0.30


def test_tank_final_fast():
    """「调压塔气室只有几十升，关阀不到 1 s」"""
    got = hidden("tank_2")
    want = expected("tank_2")["final_head_m"]
    assert abs(got["final_head_m"] - want) <= 1.0


def test_tank_trace_fast():
    """「调压塔气室只有几十升，关阀不到 1 s」"""
    got = hidden("tank_3")
    want = expected("tank_3")["station_heads"]["S2"]
    assert max_abs_diff(got["station_heads"]["S2"], want) <= 1.0
