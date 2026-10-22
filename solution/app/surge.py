"""一维水锤瞬变仿真。

用法：
    python3 /app/surge.py <case.json> <report.json>

输入给出管线、流体、阀门、调压塔和两个测点的采样时刻；输出给出压力波速、
初始达西摩阻系数、塔端峰值与末态水头，以及两个测点的水头序列。
"""

import json
import math
import sys

G = 9.80665


def pipe_support_constant(pipe):
    """按管道的轴向约束返回面积柔度系数。"""
    nu = float(pipe.get("poisson_ratio", 0.3))
    if pipe.get("axial_restraint", "free") == "anchored":
        return 1.0 - nu * nu
    return 1.0


def wave_speed(fluid, pipe):
    """薄壁管道的压力波速，按管道的轴向约束计算。"""
    K = float(fluid["bulk_modulus"])
    rho = float(fluid["density"])
    D = float(pipe["diameter"])
    e = float(pipe["wall_thickness"])
    E = float(pipe["youngs_modulus"])
    c1 = pipe_support_constant(pipe)
    return math.sqrt((K / rho) / (1.0 + K * D / (E * e) * c1))


def _colebrook(Re, roughness, diameter):
    """湍流达西摩阻系数的隐式迭代。"""
    f = 0.02
    for _ in range(60):
        rhs = -2.0 * math.log10(roughness / (3.7 * diameter) + 2.51 / (Re * math.sqrt(f)))
        f_new = 1.0 / (rhs * rhs)
        if abs(f_new - f) < 1e-13:
            return f_new
        f = f_new
    return f


def friction_factor(Re, roughness, diameter):
    """达西摩阻系数：层流用 64/Re，湍流用科尔布鲁克-怀特式。"""
    if Re < 1e-9:
        return 0.02
    if Re < 2000.0:
        return 64.0 / Re
    return _colebrook(Re, roughness, diameter)


def steady_state(case):
    """求阀门全开时的初始流量和塔端水头。"""
    fluid = case["fluid"]
    pipe = case["pipe"]
    valve = case["valve"]
    Hres = float(case["reservoir_head"])
    Hout = float(case["downstream_head"])
    D = float(pipe["diameter"])
    L = float(pipe["length"])
    A = math.pi * D * D / 4.0
    Av = float(valve["area"])
    Cd = float(valve["discharge_coefficient"])
    rho = float(fluid["density"])
    nu = float(fluid["kinematic_viscosity"])
    eps = float(pipe["roughness"])

    def residual(Ht):
        Q = Cd * Av * math.sqrt(2.0 * G * max(Ht - Hout, 0.0))
        V = Q / A
        Re = V * D / nu
        f = friction_factor(Re, eps, D)
        return Hres - Ht - f * (L / D) * V * V / (2.0 * G)

    lo = Hout
    hi = Hres
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if residual(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    Ht = 0.5 * (lo + hi)
    Q = Cd * Av * math.sqrt(2.0 * G * max(Ht - Hout, 0.0))
    V = Q / A
    Re = V * D / nu
    f = friction_factor(Re, eps, D)
    return Ht, Q, f


def validate_case(case):
    """检查输入字段和基本取值范围。"""
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    for key in ("fluid", "pipe", "valve", "surge_tank", "measurement"):
        if key not in case:
            raise ValueError(f"missing {key}")
    if float(case["pipe"]["length"]) <= 0.0:
        raise ValueError("pipe length must be positive")
    if float(case["pipe"]["diameter"]) <= 0.0:
        raise ValueError("pipe diameter must be positive")
    if float(case["surge_tank"]["gas_volume"]) <= 0.0:
        raise ValueError("gas volume must be positive")
    return case


def simulate(case):
    fluid = case["fluid"]
    pipe = case["pipe"]
    valve = case["valve"]
    tank = case["surge_tank"]
    rho = float(fluid["density"])
    nu = float(fluid["kinematic_viscosity"])
    L = float(pipe["length"])
    D = float(pipe["diameter"])
    eps = float(pipe["roughness"])
    Hres = float(case["reservoir_head"])
    Hout = float(case["downstream_head"])
    A = math.pi * D * D / 4.0
    Av = float(valve["area"])
    Cd = float(valve["discharge_coefficient"])
    Vg0 = float(tank["gas_volume"])
    At = float(tank["area"])
    Tclose = float(valve["closure_time"])

    Ht0, Q0, f0 = steady_state(case)
    a = wave_speed(fluid, pipe)
    n_grid = 160
    dx = L / n_grid
    dt = dx / a
    duration = float(case["measurement"]["duration"])
    nt = int(math.ceil(duration / dt))
    V0 = Q0 / A
    H = [Hres - f0 * (x * dx / D) * V0 * V0 / (2.0 * G) for x in range(n_grid + 1)]
    Q = [Q0] * (n_grid + 1)
    B = a / (G * A)
    R = f0 * dx / (2.0 * G * D * A * A)
    times = [float(t) for t in case["measurement"]["times"]]
    stations = case["measurement"]["stations"]
    rec = {str(s["id"]): [] for s in stations}
    Hn = H[:]
    Qn = Q[:]
    Vg = Vg0
    Ht = Ht0
    next_rec = 0

    def tau(t):
        return 0.0 if t >= Tclose else 1.0 - t / Tclose

    def station_head(s):
        pos = float(s["distance"]) / dx
        i = min(int(pos), n_grid - 1)
        frac = pos - i
        return H[i] * (1.0 - frac) + H[i + 1] * frac

    def record(t):
        nonlocal next_rec
        while next_rec < len(times) and times[next_rec] <= t + 1e-12:
            for s in stations:
                rec[str(s["id"])].append(station_head(s))
            next_rec += 1

    record(0.0)
    for n in range(1, nt + 1):
        t = n * dt
        for i in range(1, n_grid):
            Ha = H[i - 1]
            Qa = Q[i - 1]
            Hb = H[i + 1]
            Qb = Q[i + 1]
            denom = 2.0 * B + R * (abs(Qa) + abs(Qb))
            Qp = (Ha - Hb + B * (Qa + Qb)) / denom
            Hp = Ha + B * (Qa - Qp) - R * Qp * abs(Qa)
            Hn[i] = Hp
            Qn[i] = Qp
        Hb = H[1]
        Qb = Q[1]
        Hn[0] = Hres
        Qn[0] = (Hres - Hb + B * Qb) / (B + R * abs(Qb))
        Ha = H[n_grid - 1]
        Qa = Q[n_grid - 1]
        tau_now = tau(t)

        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            Hg = Ht0 * (Vg0 / Vg_new) ** 1.4
            z = (Vg0 - Vg_new) / At
            return Hg + z - Hp, Vg_new

        lo = Hout
        hi = max(Ht + 20.0, Hres + 20.0)
        for _ in range(80):
            rhi, _ = tank_residual(hi)
            if rhi < 0.0:
                break
            hi += 50.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            rmid, _ = tank_residual(mid)
            if rmid > 0.0:
                lo = mid
            else:
                hi = mid
        Hp = 0.5 * (lo + hi)
        _, Vg = tank_residual(Hp)
        Qp = (Ha - Hp + B * Qa) / (B + R * abs(Qa))
        Hn[n_grid] = Hp
        Qn[n_grid] = Qp
        Ht = Hp
        H, Hn = Hn, H
        Q, Qn = Qn, Q
        record(t)
    while next_rec < len(times):
        record(t)

    tank_id = str(stations[-1]["id"])
    tank_heads = rec[tank_id]
    tail = max(1, len(tank_heads) // 10)
    final_head = sum(tank_heads[-tail:]) / float(tail)
    return {
        "case_id": case.get("case_id", ""),
        "wave_speed_m_s": round(a, 6),
        "friction_factor": round(f0, 8),
        "peak_head_m": round(max(tank_heads), 6),
        "final_head_m": round(final_head, 6),
        "station_heads": {k: [round(v, 6) for v in vals] for k, vals in rec.items()},
    }


def main(argv):
    if len(argv) != 3:
        print("usage: python3 /app/surge.py <case.json> <report.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as handle:
            case = validate_case(json.load(handle))
        report = simulate(case)
        with open(argv[2], "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except (KeyError, TypeError, ValueError, OSError, ZeroDivisionError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
