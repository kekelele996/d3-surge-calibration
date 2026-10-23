"""区域供热管网评分：4 个 gate + D1/D2/D3 共 10 个计分测试。"""
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path("/tests")
APP = "/app/dhn.py"
RUNNER = pwd.getpwnam("runner")
EXPECTED = json.loads((TESTS / "expected.json").read_text())


def _demote():
    os.setgid(RUNNER.pw_gid)
    os.setuid(RUNNER.pw_uid)


def run_case(cid, timeout=180):
    base = Path("/app/cases") if cid in ("commissioning", "loop_demo") else (TESTS / "data")
    case = base / f"{cid}.json"
    tmp = Path(tempfile.mkdtemp(prefix=f"dhn-{cid}-"))
    os.chmod(tmp, 0o777)
    out = tmp / "report.json"
    try:
        proc = subprocess.run(
            [sys.executable, APP, str(case), str(out)],
            cwd=tmp, capture_output=True, text=True, timeout=timeout,
            preexec_fn=_demote,
        )
        if proc.returncode != 0:
            raise AssertionError(f"{cid} exited {proc.returncode}: {proc.stderr[-500:]}")
        if not out.exists():
            raise AssertionError(f"{cid} wrote no report")
        return json.loads(out.read_text())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expected(cid):
    return EXPECTED[cid]


def num(x):
    return float(x)


def max_diff(a, b):
    assert len(a) == len(b), f"length {len(a)} != {len(b)}"
    return max(abs(num(x) - num(y)) for x, y in zip(a, b))


# ---------- gate ----------

def test_output_schema():
    '''报告是 JSON 对象，字段就这些，不多不少'''
    got = run_case("commissioning")
    fields = {"case_id", "pipe_flows_kg_s", "node_pressures_kpa", "pump_head_kpa",
              "pump_flow_kg_s", "consumer_flow_kg_s", "consumer_heat_kw",
              "supply_temperatures_c", "return_temperatures_c", "plant_return_c",
              "station_temperatures"}
    assert fields <= set(got), f"missing fields: {fields - set(got)}"


def test_wrong_argument_count_exits_2():
    '''参数个数不对就退 2'''
    tmp = Path(tempfile.mkdtemp(prefix="dhn-arg-"))
    os.chmod(tmp, 0o777)
    try:
        proc = subprocess.run([sys.executable, APP], cwd=tmp, capture_output=True, text=True,
                              timeout=60, preexec_fn=_demote)
        assert proc.returncode == 2, f"exit {proc.returncode}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_repeatable_output():
    '''同一个算例跑两遍结果要完全一样'''
    a = run_case("commissioning")
    b = run_case("commissioning")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_report_is_json_object():
    '''报告是 JSON 对象'''
    got = run_case("commissioning")
    assert isinstance(got, dict)


# ---------- D1: multi-loop hydraulic ----------

def test_loop_flow_a():
    '''环路边的流量不能当成零'''
    got = run_case("hyd_1")
    want = expected("hyd_1")
    assert abs(got["pipe_flows_kg_s"].get("PS3", 0.0) - want["pipe_flows_kg_s"]["PS3"]) <= 0.03


def test_loop_flow_b():
    '''多环水力'''
    got = run_case("hyd_2")
    want = expected("hyd_2")
    assert abs(got["pipe_flows_kg_s"].get("PR3", 0.0) - want["pipe_flows_kg_s"]["PR3"]) <= 0.03


def test_loop_pressure_c():
    got = run_case("hyd_3")
    want = expected("hyd_3")
    assert abs(got["node_pressures_kpa"]["S2"] - want["node_pressures_kpa"]["S2"]) <= 0.5


# ---------- D2: heat loss + mixing ----------

def test_supply_temp_a():
    '''保温层要真的算进沿程热损'''
    got = run_case("therm_1")
    want = expected("therm_1")
    assert abs(got["supply_temperatures_c"]["S1"] - want["supply_temperatures_c"]["S1"]) <= 0.3


def test_plant_return_b():
    '''节点混合按流量加权'''
    got = run_case("therm_2")
    want = expected("therm_2")
    assert abs(got["plant_return_c"] - want["plant_return_c"]) <= 0.3


def test_return_temp_c():
    got = run_case("therm_3")
    want = expected("therm_3")
    assert abs(got["return_temperatures_c"]["R1"] - want["return_temperatures_c"]["R1"]) <= 0.3


# ---------- D3: transport delay + inertia ----------

def test_transient_a():
    '''瞬态要保留管段的输运延迟和热惯性'''
    got = run_case("trans_1")
    want = expected("trans_1")
    assert max_diff(got["station_temperatures"]["S1"], want["station_temperatures"]["S1"]) <= 1.5


def test_transient_b():
    got = run_case("trans_2")
    want = expected("trans_2")
    assert max_diff(got["station_temperatures"]["S2"], want["station_temperatures"]["S2"]) <= 1.5


def test_transient_c():
    '''supply_profile / load_profile 是阶跃或折线'''
    got = run_case("trans_3")
    want = expected("trans_3")
    assert max_diff(got["station_temperatures"]["S1"], want["station_temperatures"]["S1"]) <= 1.5


def test_transient_d():
    got = run_case("trans_3")
    want = expected("trans_3")
    assert max_diff(got["station_temperatures"]["R0"], want["station_temperatures"]["R0"]) <= 1.5
