#!/usr/bin/env bash
# 参考解：把 solution/app/surge.py 装到 /app/surge.py。
# HTB_SKIP=difficulty_1[,difficulty_2,difficulty_3] 时把对应修复退回原写法。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
install -m 0644 "$HERE/app/surge.py" /app/surge.py

SKIP="${HTB_SKIP:-}" /usr/local/bin/python3 - /app/surge.py <<'PY'
import os
import sys
from pathlib import Path

D1_FIXED = '''def effective_bulk(fluid, p_abs):
    """含气液体的有效体积模量。

    等温气泡：alpha(p) = alpha0 * p_ref / p，混合物体积模量
    1/K_m = 1/K_l + alpha0 * p_ref / p^2。
    """
    K = float(fluid["bulk_modulus"])
    alpha = float(fluid.get("air_fraction", 0.0))
    p_ref = float(fluid.get("reference_pressure", PATM))
    if alpha <= 0.0:
        return K
    return 1.0 / (1.0 / K + alpha * p_ref / (p_abs * p_abs))
'''

D1_ORIGINAL = '''def effective_bulk(fluid, p_abs):
    """纯液体体积模量；含气率未参与。"""
    return float(fluid["bulk_modulus"])
'''

D2_FIXED = '''        if k_unsteady > 0.0:
'''

D2_ORIGINAL = '''        if False:
'''

D3_TAU_FIXED = '''    table = valve.get("position_table")

    def tau(t):
        if table:
            if t <= float(table[0][0]):
                return float(table[0][1])
            for k in range(1, len(table)):
                t0, v0 = float(table[k - 1][0]), float(table[k - 1][1])
                t1, v1 = float(table[k][0]), float(table[k][1])
                if t <= t1:
                    return v1 if t1 <= t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
            return float(table[-1][1])
        return 0.0 if t >= Tclose else 1.0 - t / Tclose
'''

D3_TAU_ORIGINAL = '''    def tau(t):
        return 0.0 if t >= Tclose else 1.0 - t / Tclose
'''

D3_TANK_FIXED = '''        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R0 * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            dVdt = -(Qp - Qv)
            p_old = m_gas * R_gas * T_gas / Vg
            T_new = T_gas + dt * (-p_old * dVdt + h_coef * At * (Tw - T_gas)) / (m_gas * cv_gas)
            T_new = max(T_new, 100.0)
            p_new = m_gas * R_gas * T_new / Vg_new
            Hg = (p_new - PATM) / (rho * G)
            z = (Vg0 - Vg_new) / At
            return Hg + z - Hp, Vg_new, T_new
'''

D3_TANK_ORIGINAL = '''        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R0 * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            Hg = Ht0 * (Vg0 / Vg_new) ** 1.4
            z = (Vg0 - Vg_new) / At
            return Hg + z - Hp, Vg_new, T_gas
'''

REVERT = {
    "difficulty_1": [(D1_FIXED, D1_ORIGINAL)],
    "difficulty_2": [(D2_FIXED, D2_ORIGINAL)],
    "difficulty_3": [(D3_TAU_FIXED, D3_TAU_ORIGINAL), (D3_TANK_FIXED, D3_TANK_ORIGINAL)],
}
skip = [item for item in os.environ.get("SKIP", "").split(",") if item]
unknown = sorted(set(skip) - set(REVERT))
if unknown:
    sys.exit(f"HTB_SKIP 里有未知难点：{unknown}")
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for key in skip:
    for fixed, original in REVERT[key]:
        count = text.count(fixed)
        if count != 1:
            sys.exit(f"{key} 的修复片段在参考实现里出现 {count} 次，应为 1")
        text = text.replace(fixed, original)
    print(f"留一法：{key} 退回原写法", file=sys.stderr)
path.write_text(text, encoding="utf-8")
PY
chown runner:runner /app/surge.py 2>/dev/null || true
