"""D.3 区域供热管网：多环水力 + 热力稳态/瞬态。"""
import json
import math
import sys

G = 9.80665


def solve_linear(A, b):
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-15:
            return None
        if piv != col:
            M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            if f:
                for k in range(col, n + 1):
                    M[r][k] -= f * M[col][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / M[i][i]
    return x


def friction_factor(Re, eps, D):
    if Re <= 0.0:
        return 64.0
    if Re < 2300.0:
        return 64.0 / Re
    f = 0.02
    for _ in range(50):
        f = 1.0 / (-2.0 * math.log10(eps / (3.7 * D) + 2.51 / (Re * math.sqrt(f)))) ** 2
    return f


def pump_fit(curve):
    (q0, h0), (q1, h1), (q2, h2) = curve[0], curve[1], curve[2]
    A = [[1.0, q0, q0 * q0], [1.0, q1, q1 * q1], [1.0, q2, q2 * q2]]
    return solve_linear(A, [h0, h1, h2])


def pump_head(curve, q, speed):
    a, b, c = pump_fit(curve)
    qq = q / speed
    return speed * speed * (a + b * qq + c * qq * qq)


def pump_flow(curve, head, speed):
    a, b, c = pump_fit(curve)
    t = head / (speed * speed)
    A, B, C = c, b, a - t
    if abs(A) < 1e-12:
        q1 = (t - a) / b if abs(b) > 1e-15 else 0.0
    else:
        disc = B * B - 4.0 * A * C
        if disc < 0.0:
            disc = 0.0
        r1 = (-B + math.sqrt(disc)) / (2.0 * A)
        r2 = (-B - math.sqrt(disc)) / (2.0 * A)
        cand = [r for r in (r1, r2) if r > 1e-12]
        q1 = min(cand) if cand else 0.0
    return speed * max(q1, 0.0)


def active_pipes(case):
    return [p for p in case["pipes"] if not p.get("loop")]


def u_value(pipe):
    ins = pipe.get("insulation")
    if not ins:
        return 0.0
    k = float(ins.get("conductivity", 0.0))
    t = float(ins.get("thickness", 0.0))
    r = 0.5 * float(pipe["diameter"])
    if k <= 0.0 or t <= 0.0 or r <= 0.0:
        return 0.0
    return 2.0 * math.pi * k / math.log((r + t) / r)


def pipe_outlet_temp(Tin, m, pipe, cp, Tamb):
    return Tin


def pipe_delay(pipe, m, rho):
    return 0.0


def hydraulic(case):
    fluid = case["fluid"]
    rho = float(fluid["density"])
    nu = float(fluid["kinematic_viscosity"])
    pipes = active_pipes(case)
    cons = case["consumers"]
    plant = case["plant"]
    curve = plant["pump"]["curve"]
    speed = float(plant["pump"].get("speed", 1.0))
    S0 = plant["node_supply"]
    R0 = plant["node_return"]
    nodes = set()
    for p in pipes:
        nodes.add(p["from"]); nodes.add(p["to"])
    for c in cons:
        nodes.add(c["node_supply"]); nodes.add(c["node_return"])
    nodes.add(S0); nodes.add(R0)
    unknown = sorted(n for n in nodes if n != R0)
    H = {S0: pump_head(curve, 0.0, speed), R0: 0.0}
    for n in nodes:
        if n not in H:
            H[n] = H[S0] * 0.9 if n.startswith("S") else 0.02
    qpipe = {p["id"]: 1e-4 for p in pipes}
    Rmap = {}
    for outer in range(30):
        for p in pipes:
            q = abs(qpipe.get(p["id"], 1e-4))
            D = float(p["diameter"])
            A = math.pi * D * D / 4.0
            V = q / A
            Re = V * D / nu
            f = friction_factor(Re, float(p["roughness"]), D)
            Rmap[p["id"]] = (f * float(p["length"]) / D + float(p.get("minor_loss", 0.0))) / (2.0 * G * A * A)

        def state(Hv):
            qp = pump_flow(curve, Hv[S0] - Hv[R0], speed)
            qs = {}
            for p in pipes:
                dH = Hv[p["from"]] - Hv[p["to"]]
                R = Rmap[p["id"]]
                qs[p["id"]] = math.copysign(math.sqrt(abs(dH) / R + 1e-12), dH)
            qc = {}
            for c in cons:
                dH = Hv[c["node_supply"]] - Hv[c["node_return"]]
                qc[c["id"]] = float(c["valve"]["kv"]) * float(c["valve"]["position"]) * math.sqrt(max(dH, 0.0))
            res = {n: 0.0 for n in unknown}
            for p in pipes:
                q = qs[p["id"]]
                if p["from"] in res:
                    res[p["from"]] += q
                if p["to"] in res:
                    res[p["to"]] -= q
            for c in cons:
                q = qc[c["id"]]
                if c["node_supply"] in res:
                    res[c["node_supply"]] += q
                if c["node_return"] in res:
                    res[c["node_return"]] -= q
            res[S0] -= qp
            return res, qs, qc, qp

        for it in range(60):
            res, qs, qc, qp = state(H)
            r = [res[n] for n in unknown]
            norm = max(abs(x) for x in r)
            if norm < 1e-7:
                break
            m = len(unknown)
            J = [[0.0] * m for _ in range(m)]
            for j, u in enumerate(unknown):
                dh = 1e-4 * max(1.0, abs(H[u]))
                H2 = dict(H); H2[u] += dh
                res2, _, _, _ = state(H2)
                for i, n in enumerate(unknown):
                    J[i][j] = (res2[n] - res[n]) / dh
            dx = solve_linear(J, [-x for x in r])
            if dx is None:
                break
            alpha = 1.0
            for _ in range(25):
                Ht = dict(H)
                for i, u in enumerate(unknown):
                    Ht[u] += alpha * dx[i]
                rt, _, _, _ = state(Ht)
                if max(abs(rt[n]) for n in unknown) < norm:
                    break
                alpha *= 0.5
            for i, u in enumerate(unknown):
                H[u] += alpha * dx[i]
        qpipe = qs
        if outer > 0 and max(abs(qs[p["id"]] - qpipe.get(p["id"], 0.0)) for p in pipes) < 1e-9:
            pass
    return {"H": H, "qpipe": qpipe, "qcons": qc, "qp": qp, "pipes": pipes, "rho": rho}


def thermal_steady(case, hyd):
    fluid = case["fluid"]
    rho = hyd["rho"]
    cp = float(fluid["specific_heat"])
    Tamb = float(case["ambient"]["ground_temperature"])
    plant = case["plant"]
    S0 = plant["node_supply"]
    R0 = plant["node_return"]
    Tplant = float(plant["supply_temperature"])
    pipes = hyd["pipes"]
    qpipe = hyd["qpipe"]
    qcons = hyd["qcons"]
    pipes_by_id = {p["id"]: p for p in pipes}
    sup_pipes = [p for p in pipes if p["from"].startswith("S") and p["to"].startswith("S")]
    ret_pipes = [p for p in pipes if p["from"].startswith("R") and p["to"].startswith("R")]
    sup_nodes = sorted({n for p in sup_pipes for n in (p["from"], p["to"])} | {S0})
    ret_nodes = sorted({n for p in ret_pipes for n in (p["from"], p["to"])} | {R0})
    T = {n: Tplant - 12.0 for n in sup_nodes}
    T[S0] = Tplant
    for _ in range(600):
        new = dict(T)
        for v in sup_nodes:
            if v == S0:
                continue
            num = 0.0; den = 0.0
            for p in sup_pipes:
                q = qpipe[p["id"]]
                if p["to"] == v and q > 1e-9:
                    u = p["from"]; mm = rho * q
                    num += mm * pipe_outlet_temp(T[u], mm, p, cp, Tamb); den += mm
                elif p["from"] == v and q < -1e-9:
                    u = p["to"]; mm = rho * (-q)
                    num += mm * pipe_outlet_temp(T[u], mm, p, cp, Tamb); den += mm
            if den > 1e-12:
                new[v] = num / den
        if max(abs(new[v] - T[v]) for v in sup_nodes) < 1e-10:
            T = new; break
        T = new
    Tr = {n: 45.0 for n in ret_nodes}
    for _ in range(600):
        new = dict(Tr)
        for v in ret_nodes:
            if v == R0:
                continue
            num = 0.0; den = 0.0
            for p in ret_pipes:
                q = qpipe[p["id"]]
                if p["to"] == v and q > 1e-9:
                    u = p["from"]; mm = rho * q
                    num += mm * pipe_outlet_temp(Tr[u], mm, p, cp, Tamb); den += mm
                elif p["from"] == v and q < -1e-9:
                    u = p["to"]; mm = rho * (-q)
                    num += mm * pipe_outlet_temp(Tr[u], mm, p, cp, Tamb); den += mm
            for c in case["consumers"]:
                if c["node_return"] == v:
                    mm = rho * qcons[c["id"]]
                    if mm > 1e-9:
                        ts = T[c["node_supply"]]
                        tr = ts - float(c["heat_load"]) / (mm * cp)
                        num += mm * tr; den += mm
            if den > 1e-12:
                new[v] = num / den
        if max(abs(new[v] - Tr[v]) for v in ret_nodes) < 1e-10:
            Tr = new; break
        Tr = new
    num = 0.0; den = 0.0
    for p in ret_pipes:
        q = qpipe[p["id"]]
        if p["to"] == R0 and q > 1e-9:
            num += rho * q * pipe_outlet_temp(Tr[p["from"]], rho * q, p, cp, Tamb); den += rho * q
        elif p["from"] == R0 and q < -1e-9:
            num += rho * (-q) * pipe_outlet_temp(Tr[p["to"]], rho * (-q), p, cp, Tamb); den += rho * (-q)
    if den > 1e-12:
        Tr[R0] = num / den
    return {"supply": T, "return": Tr, "qcons": qcons, "qpipe": qpipe}


def profile_value(profile, t):
    if not profile:
        return None
    if t <= float(profile[0][0]):
        return float(profile[0][1])
    for k in range(1, len(profile)):
        t0, v0 = float(profile[k - 1][0]), float(profile[k - 1][1])
        t1, v1 = float(profile[k][0]), float(profile[k][1])
        if t <= t1:
            return v1 if t1 <= t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return float(profile[-1][1])


def thermal_transient(case, hyd):
    fluid = case["fluid"]
    rho = hyd["rho"]
    cp = float(fluid["specific_heat"])
    Tamb = float(case["ambient"]["ground_temperature"])
    plant = case["plant"]
    S0 = plant["node_supply"]
    R0 = plant["node_return"]
    Tplant0 = float(plant["supply_temperature"])
    supply_profile = plant.get("supply_profile")
    pipes = hyd["pipes"]
    qpipe = hyd["qpipe"]
    qcons = hyd["qcons"]
    sup_pipes = [p for p in pipes if p["from"].startswith("S") and p["to"].startswith("S")]
    ret_pipes = [p for p in pipes if p["from"].startswith("R") and p["to"].startswith("R")]
    sup_nodes = sorted({n for p in sup_pipes for n in (p["from"], p["to"])} | {S0})
    ret_nodes = sorted({n for p in ret_pipes for n in (p["from"], p["to"])} | {R0})
    meas = case["measurement"]
    times = [float(t) for t in meas["times"]]
    duration = float(meas.get("duration", times[-1] if times else 0.0))
    nt = 240
    dt = duration / nt if duration > 0 else 1.0
    # histories of inlet temperature per pipe, one sample per step
    steady = thermal_steady(case, hyd)
    T = dict(steady["supply"])
    Tr = dict(steady["return"])
    hist = {}
    for p in pipes:
        q = qpipe[p["id"]]
        if p["from"].startswith("S"):
            Tin0 = T[p["from"]] if q >= 0 else T[p["to"]]
        else:
            Tin0 = Tr[p["from"]] if q >= 0 else Tr[p["to"]]
        hist[p["id"]] = [Tin0] * (nt + 2)
    stations = meas["stations"]
    rec = {str(s["id"]): [] for s in stations}
    next_rec = 0

    def record(t, Tsup, Tret):
        nonlocal next_rec
        while next_rec < len(times) and times[next_rec] <= t + 1e-9:
            for s in stations:
                node = s["node"]
                val = Tsup.get(node, Tret.get(node, 0.0))
                rec[str(s["id"])].append(val)
            next_rec += 1

    def pipe_out_delayed(p, t, Tsup):
        q = qpipe[p["id"]]
        mm = rho * abs(q)
        Tin = Tsup[p["from"]] if q > 0 else Tsup[p["to"]]
        tau = pipe_delay(p, mm, rho)
        # sample index at t - tau
        pos = (t - tau) / dt
        if pos <= 0:
            base = Tplant0 if p["from"].startswith("S") else 45.0
            delayed = base
        else:
            i0 = int(math.floor(pos)); frac = pos - i0
            seq = hist[p["id"]]
            i0 = min(max(i0, 0), nt)
            delayed = seq[i0] * (1.0 - frac) + seq[min(i0 + 1, nt)] * frac
        return pipe_outlet_temp(delayed, mm, p, cp, Tamb)

    T[S0] = Tplant0
    record(0.0, T, Tr)
    for n in range(1, nt + 1):
        t = n * dt
        T[S0] = profile_value(supply_profile, t) if supply_profile else Tplant0
        for p in pipes:
            if p["from"].startswith("S"):
                hist[p["id"]][n] = T[p["from"]] if qpipe[p["id"]] >= 0 else T[p["to"]]
            else:
                hist[p["id"]][n] = Tr[p["from"]] if qpipe[p["id"]] >= 0 else Tr[p["to"]]
        newT = dict(T)
        for _ in range(2):
            for v in sup_nodes:
                if v == S0:
                    continue
                num = 0.0; den = 0.0
                for p in sup_pipes:
                    q = qpipe[p["id"]]
                    if p["to"] == v and q > 1e-9:
                        mm = rho * q; num += mm * pipe_out_delayed(p, t, T); den += mm
                    elif p["from"] == v and q < -1e-9:
                        mm = rho * (-q); num += mm * pipe_out_delayed(p, t, T); den += mm
                if den > 1e-12:
                    newT[v] = num / den
            T = newT
        newTr = dict(Tr)
        for v in ret_nodes:
            num = 0.0; den = 0.0
            for p in ret_pipes:
                q = qpipe[p["id"]]
                if p["to"] == v and q > 1e-9:
                    mm = rho * q; num += mm * pipe_out_delayed(p, t, Tr); den += mm
                elif p["from"] == v and q < -1e-9:
                    mm = rho * (-q); num += mm * pipe_out_delayed(p, t, Tr); den += mm
            for c in case["consumers"]:
                if c["node_return"] == v:
                    mm = rho * qcons[c["id"]]
                    if mm > 1e-9:
                        load = profile_value(c.get("load_profile"), t) or float(c["heat_load"])
                        ts = T[c["node_supply"]]
                        num += mm * (ts - load / (mm * cp)); den += mm
            if den > 1e-12:
                newTr[v] = num / den
        Tr = newTr
        record(t, T, Tr)
    while next_rec < len(times):
        record(times[next_rec] + 1e-6, T, Tr)
    return {"T": T, "Tr": Tr, "station": rec}


def simulate(case):
    hyd = hydraulic(case)
    rho = hyd["rho"]
    cp = float(case["fluid"]["specific_heat"])
    meas = case["measurement"]
    times = [float(t) for t in meas["times"]]
    duration = float(meas.get("duration", 0.0))
    transient_mode = duration > 0.0 and len(times) > 1
    if transient_mode:
        tr = thermal_transient(case, hyd)
        T, Tr, station = tr["T"], tr["Tr"], tr["station"]
    else:
        th = thermal_steady(case, hyd)
        T, Tr = th["supply"], th["return"]
        station = {}
        for s in meas["stations"]:
            node = s["node"]
            val = T.get(node, Tr.get(node, 0.0))
            station[str(s["id"])] = [val]
    pipes = hyd["pipes"]
    cons = case["consumers"]
    qpipe = hyd["qpipe"]; qcons = hyd["qcons"]; qp = hyd["qp"]; H = hyd["H"]
    return {
        "case_id": case.get("case_id", ""),
        "pipe_flows_kg_s": {p["id"]: round(rho * qpipe[p["id"]], 6) for p in pipes},
        "node_pressures_kpa": {n: round(H[n] * rho * G / 1000.0, 4) for n in sorted(H)},
        "pump_head_kpa": round((H[case["plant"]["node_supply"]] - H[case["plant"]["node_return"]]) * rho * G / 1000.0, 4),
        "pump_flow_kg_s": round(rho * qp, 6),
        "consumer_flow_kg_s": {c["id"]: round(rho * qcons[c["id"]], 6) for c in cons},
        "consumer_heat_kw": {c["id"]: round(float(c["heat_load"]) / 1000.0, 4) for c in cons},
        "supply_temperatures_c": {n: round(T[n], 4) for n in sorted(T)},
        "return_temperatures_c": {n: round(Tr[n], 4) for n in sorted(Tr)},
        "plant_return_c": round(Tr[case["plant"]["node_return"]], 4),
        "station_temperatures": {k: [round(v, 4) for v in vals] for k, vals in station.items()},
    }


def validate_case(case):
    if not case.get("pipes"):
        raise ValueError("pipes must not be empty")
    for p in case["pipes"]:
        if float(p["length"]) <= 0.0 or float(p["diameter"]) <= 0.0:
            raise ValueError("pipe length/diameter must be positive")
    for c in case["consumers"]:
        if float(c["valve"]["kv"]) < 0.0 or float(c["valve"]["position"]) < 0.0:
            raise ValueError("valve must be non-negative")
    return case


def main(argv):
    if len(argv) != 3:
        print("usage: python3 /app/dhn.py <case.json> <report.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as fh:
            case = validate_case(json.load(fh))
        report = simulate(case)
        with open(argv[2], "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
    except (KeyError, TypeError, ValueError, OSError, ZeroDivisionError, OverflowError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
