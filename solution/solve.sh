#!/usr/bin/env bash
# 参考解：把 solution/app/surge.py 装到 /app/surge.py。
# HTB_SKIP=difficulty_1[,difficulty_2,difficulty_3] 时把对应修复退回原写法，
# 用于留一法和变异矩阵；每个片段必须恰好命中一次，否则直接失败。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
install -m 0644 "$HERE/app/surge.py" /app/surge.py

SKIP="${HTB_SKIP:-}" /usr/local/bin/python3 - /app/surge.py <<'PY'
import os
import sys
from pathlib import Path

D1_FIXED = '''def wave_speed(fluid, pipe):
    """薄壁管道的压力波速，按管道的轴向约束计算。"""
    K = float(fluid["bulk_modulus"])
    rho = float(fluid["density"])
    D = float(pipe["diameter"])
    e = float(pipe["wall_thickness"])
    E = float(pipe["youngs_modulus"])
    c1 = pipe_support_constant(pipe)
    return math.sqrt((K / rho) / (1.0 + K * D / (E * e) * c1))
'''

D1_ORIGINAL = '''def wave_speed(fluid, pipe):
    """薄壁管道的压力波速，按伸缩节自由轴向变形计算。"""
    K = float(fluid["bulk_modulus"])
    rho = float(fluid["density"])
    D = float(pipe["diameter"])
    e = float(pipe["wall_thickness"])
    E = float(pipe["youngs_modulus"])
    return math.sqrt((K / rho) / (1.0 + K * D / (E * e)))
'''

D2_FIXED = '''def friction_factor(Re, roughness, diameter):
    """达西摩阻系数：层流用 64/Re，湍流用科尔布鲁克-怀特式。"""
    if Re < 1e-9:
        return 0.02
    if Re < 2000.0:
        return 64.0 / Re
    return _colebrook(Re, roughness, diameter)
'''

D2_ORIGINAL = '''def friction_factor(Re, roughness, diameter):
    """达西摩阻系数：层流用 64/Re，湍流用光滑管布拉修斯式。"""
    if Re < 1e-9:
        return 0.02
    if Re < 2000.0:
        return 64.0 / Re
    return 0.3164 / (Re ** 0.25)
'''

D3_FIXED = '''        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            Hg = Ht0 * (Vg0 / Vg_new) ** 1.4
            z = (Vg0 - Vg_new) / At
            return Hg + z - Hp, Vg_new
'''

D3_ORIGINAL = '''        def tank_residual(Hp):
            Qp = (Ha - Hp + B * Qa) / (B + R * abs(Qa))
            Qv = tau_now * Cd * Av * math.sqrt(2.0 * G * max(Hp - Hout, 0.0))
            Vg_new = Vg - (Qp - Qv) * dt
            Vg_new = max(Vg_new, 1e-6 * Vg0)
            Hg = Ht0 * (Vg0 / Vg_new) ** 1.0
            return Hg - Hp, Vg_new
'''

REVERT = {
    "difficulty_1": (D1_FIXED, D1_ORIGINAL),
    "difficulty_2": (D2_FIXED, D2_ORIGINAL),
    "difficulty_3": (D3_FIXED, D3_ORIGINAL),
}
skip = [item for item in os.environ.get("SKIP", "").split(",") if item]
unknown = sorted(set(skip) - set(REVERT))
if unknown:
    sys.exit(f"HTB_SKIP 里有未知难点：{unknown}")
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for key in skip:
    fixed, original = REVERT[key]
    count = text.count(fixed)
    if count != 1:
        sys.exit(f"{key} 的修复片段在参考实现里出现 {count} 次，应为 1")
    text = text.replace(fixed, original)
    print(f"留一法：{key} 退回原写法", file=sys.stderr)
path.write_text(text, encoding="utf-8")
PY
chown runner:runner /app/surge.py 2>/dev/null || true
