"""一维水锤瞬变仿真（advanced 版）。

用法：
    python3 /app/surge.py <case.json> <report.json>

相对标准版增加三个闭合：含气液体有效体积模量、Brunone 非恒定摩阻、
气垫传热与非线性阀表。
"""

import json
import math
import sys

G = 9.80665
PATM = 101325.0


def pipe_support_constant(pipe):
    """按管道的轴向约束返回面积柔度系数。"""
    nu = float(pipe.get("poisson_ratio", 0.3))
    if pipe.get("axial_restraint", "free") == "anchored":
        return 1.0 - nu * nu
    return 1.0


def effective_bulk(fluid, p_abs):
    """纯液体体积模量；含气率未参与。"""
    return float(fluid["bulk_modulus"])


def wave_speed(fluid, pipe, p_abs):
    """薄壁管道的压力波速，按轴向约束和含气体积模量计算。"""
    K = effective_bulk(fluid, p_abs)
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
    k_unsteady = float(pipe.get("unsteady_coefficient", 0.0))

    Ht0, Q0, f0 = steady_state(case)
    p0_abs = rho * G * Hres + PATM
    a = wave_speed(fluid, pipe, p0_abs)
    n_grid = 160
    dx = L / n_grid
    dt = dx / a
    duration = float(case["measurement"]["duration"])
    nt = int(math.ceil(duration / dt))
    V0 = Q0 / A
    H = [Hres - f0 * (x * dx / D) * V0 * V0 / (2.0 * G) for x in range(n_grid + 1)]
    Q = [Q0] * (n_grid + 1)
    B = a / (G * A)
    R0 = f0 * dx / (2.0 * G * D * A * A)
    R_nodes = [R0] * (n_grid + 1)
    V_old = [V0] * (n_grid + 1)
    times = [float(t) for t in case["measurement"]["times"]]
    stations = case["measurement"]["stations"]
    rec = {str(s["id"]): [] for s in stations}
    Hn = H[:]
    Qn = Q[:]
    Vg = Vg0
    Ht = Ht0
    next_rec = 0

    T0 = float(tank.get("gas_temperature", 293.15))
    Tw = float(tank.get("wall_temperature", T0))
    h_coef = float(tank.get("heat_transfer_coefficient", 0.0))
    R_gas = float(tank.get("gas_constant", 287.0))
    cv_gas = float(tank.get("cv", 718.0))
    p0_gas = rho * G * Ht0 + PATM
    m_gas = p0_gas * Vg0 / (R_gas * T0)
    T_gas = T0

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
        if False:
            for i in range(1, n_grid):
                V = Q[i] / A
                Vt = (V - V_old[i]) / dt
                Vx = (Q[i + 1] - Q[i - 1]) / (2.0 * dx * A)
                sgn = 1.0 if V >= 0.0 else -1.0
                fu = f0 + k_unsteady * D / (abs(V) + 1e-6) * (Vt + a * sgn * Vx)
                fu = min(max(fu, 0.5 * f0), 5.0 * f0)
                R_nodes[i] = fu * dx / (2.0 * G * D * A * A)
        for i in range(1, n_grid):
            Ha = H[i - 1]
            Qa = Q[i - 1]
            Hb = H[i + 1]
            Qb = Q[i + 1]
            Ri = R_nodes[i]
            denom = 2.0 * B + Ri * (abs(Qa) + abs(Qb))
            Qp = (Ha - Hb + B * (Qa + Qb)) / denom
            Hp = Ha + B * (Qa - Qp) - Ri * Qp * abs(Qa)
            Hn[i] = Hp
            Qn[i] = Qp
        Hb = H[1]
        Qb = Q[1]
        Hn[0] = Hres
        Qn[0] = (Hres - Hb + B * Qb) / (B + R0 * abs(Qb))
        Ha = H[n_grid - 1]
        Qa = Q[n_grid - 1]
        tau_now = tau(t)

        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R0 * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            Hg = Ht0 * (Vg0 / Vg_new) ** 1.4
            z = (Vg0 - Vg_new) / At
            return Hg + z - Hp, Vg_new, T_gas

        lo = Hout
        hi = max(Ht + 20.0, Hres + 20.0)
        for _ in range(80):
            rhi, _, _ = tank_residual(hi)
            if rhi < 0.0:
                break
            hi += 50.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            rmid, _, _ = tank_residual(mid)
            if rmid > 0.0:
                lo = mid
            else:
                hi = mid
        Hp = 0.5 * (lo + hi)
        res = tank_residual(Hp)
        Vg, T_gas = res[1], res[2]
        Qp = (Ha - Hp + B * Qa) / (B + R0 * abs(Qa))
        Hn[n_grid] = Hp
        Qn[n_grid] = Qp
        Ht = Hp
        H, Hn = Hn, H
        Q, Qn = Qn, Q
        V_old = [q / A for q in Q]
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
