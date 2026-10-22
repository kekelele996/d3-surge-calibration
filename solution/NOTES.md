# 参考解说明

## 三个难点

| 编号 | 错误认知 | 正确知识 | 可观察行为 | 对应测试 |
|---|---|---|---|---|
| difficulty_1 | 锚固段按“只锚上游端”取 `c1=1-nu_p/2` | 锚固段取 `c1=1-nu_p^2`，伸缩节段取 `c1=1`；`a=sqrt((K/rho)/(1+K D c1/(E e)))` | 锚固 HDPE 段波速偏高 2.0%-2.4%，压力波到达时间随之提前 | `test_wave_speed_anchored_a/b/c` |
| difficulty_2 | 湍流按完全粗糙区 `0.25/log10^2(eps/(3.7D))` 近似，忽略 Re | 粗糙管用 Colebrook-White；层流仍用 `64/Re` | 初始摩阻系数偏低 3.9%-5.7%，首端稳态水头偏高 0.32-0.74 m | `test_friction_rough_a/b`、`test_rough_steady_head` |
| difficulty_3 | 气垫按绝对压力计算，`H_g=(H_t0+P_atm)(V_g0/V_g)^1.4-P_atm` | 塔头是表压：`H_g=H_t0(V_g0/V_g)^1.4`，再加水位项 `z=(V_g0-V_g)/A_t` | 峰值差 0.18-0.89 m，末段 10% 平均差 1.56-6.03 m，塔端逐点差 3.65-8.08 m | `test_tank_peak_fast/final_fast/trace_fast` |

## 参考解文件

- `solution/app/surge.py`：完整实现，约 260 行；`wave_speed`、`friction_factor`、`steady_state`、`simulate`、`main` 五个部分。
- `solution/solve.sh`：只负责把参考实现装到 `/app/surge.py`，并按 `HTB_SKIP` 用精确片段退回原写法。每个片段在参考实现里必须恰好出现一次。
- 留一法 id：`difficulty_1`、`difficulty_2`、`difficulty_3`。

## 关键步骤

1. **稳态初值**：由 `H_res-H_t=f(L/D)V^2/(2g)` 和 `Q=C_d A_v sqrt(2g(H_t-H_out))` 联立，在 `[H_out,H_res]` 上二分求 `H_t`，得到 `Q0`、`f0` 和沿管线的初始水头。
2. **网格**：`N=160`，`dx=L/N`，`dt=dx/a`，Courant 数 1。
3. **内节点**：由 C+、C- 联立求 `Q_P`，再代回 C+ 求 `H_P`。
4. **上游**：水库水头固定，由 C- 求流量。
5. **下游调压塔**：由 C+ 得 `Q_P(H)`，阀门得 `Q_v(H)`；`valve.position_table` 存在时按时间线性插值开度，否则按 `closure_time` 线性关。气室体积更新后由多变过程得 `H_g`，水位项得 `z`；解 `H=H_g+z`。`H_g+z-H` 随 `H` 单调下降，二分求根。
6. **输出**：`wave_speed_m_s` 取公式值；`friction_factor` 取初始 Re 的达西系数；`peak_head_m` 取塔端序列最大值；`final_head_m` 取塔端序列末段 10% 的平均；`station_heads` 按测点 id 和 `times` 输出。

## 核心公式与独立复算

- 波速：`a=sqrt((K/rho)/(1+K D c1/(E e)))`，自由 `c1=1`，锚固 `c1=1-nu_p^2`。解析推导见 `research/derivations.md` 第 1 节；`research/verify_wave_speed.py` 用 MOC 波往返周期 `4L/a` 和 Joukowsky `aV0/g` 复核，比值都是 1.0。
- 摩阻：Colebrook-White 隐式式，层流 `64/Re`。`research/verify_friction.py` 用 Haaland 显式式复核，最大相对差 `8.0e-3`；Moody 图已知点 `Re=1e5, eps/D=0.00125` 给出 `0.022984`。
- 调压塔：`H_g=H_t0(V_g0/V_g)^n`，`z=(V_g0-V_g)/A_t`，`dV_g/dt=-(Q_P-Q_v)`。`research/verify_tank.py` 从仿真最小气室体积独立算 `H_g+z`，和仿真峰值差 `0.0002 m` 以内。
- 稳态：`research/verify_steady.py` 用 20001 点扫描复核二分结果，9 个算例差 `0.0`，最大残差 `1.4e-14`。
- 网格：`N=160` 与 `N=320` 的塔峰值差 `0.025 m`，末段平均差 `0.062 m`；`N=80` 到 `N=640` 的峰值变化小于 `0.09 m`。

## 容差依据

- 波速 `1%`：公式值是确定性的，网格不影响；错误版本偏 2.0%-2.4%，容差比错误小一半以上。
- 摩阻 `3%`：Colebrook 与 Haaland 的差小于 `0.8%`；错误版本偏 3.9%-5.7%，容差留出足够余量。
- 首端稳态水头 `0.20 m`：参考解与 N=320 期望差 `0.03 m`；错误版本偏 `0.32-0.74 m`。
- 塔峰值 `0.30 m`、末态 `1.0 m`：参考解与期望差 `0.10 m` 以内；错误版本峰值偏 `0.38/0.89/0.18 m`，末态偏 `6.03/1.56/4.07 m`。
- 塔端逐点 `1.0 m`：参考解与期望差 `0.21 m` 以内；错误版本偏 `3.65-8.08 m`。
- 三个容差都大于正常网格抖动，小于典型错误偏差；依据和实测表见 `research/derivations.md` 第 6、7 节。

## 权重依据

- `difficulty_1` 合计 `0.40`：波速是报告的第一核心量；三个锚固算例分别为 `0.14/0.13/0.13`。
- `difficulty_2` 合计 `0.30`：摩阻控制首端稳态水头和压力衰减；三个算例各 `0.10`。
- `difficulty_3` 合计 `0.30`：调压塔峰值、末态和塔端序列；三个算例各 `0.10`。
- gate 测试（`test_output_schema`、`test_wrong_argument_count_exits_2`、`test_repeatable_output`）不计分；只检查入口、输出结构和重复性。
- 只修一个难点的实测分数是 `0.400/0.300/0.300`；跳过单个难点是 `0.600/0.700/0.700`，和权重一致。

## 数据来源

- 真实数据：无。本题的试验记录是按一维瞬变模型生成的合成数据，用于覆盖参数包线；`research/sources.md` 已说明，`environment/` 内不放生成脚本或来源说明。
- 生成规则：`research/make_cases.py` 调用 `research/reference_model.py`，用 320 格特征线模型生成 9 个隐藏算例和 2 个可见算例；参数固定，无随机种子。
- 可见算例：`environment/app/cases/commissioning.json`（不带现场记录）和 `steady.json`；隐藏算例在 `tests/data/`。
- 期望值：`tests/expected.json` 由 `research/make_cases.py` 生成，不由候选程序或 `solution/` 代码生成。

## 答案隔离

- [x] 镜像内没有 `tests/`、`solution/`、`.git/`、缓存和备份。
- [x] 注释、文件名、变量名、数据元信息没有写出 `Colebrook`、`1-nu^2`、`n=1.4` 等答案；`environment/app/surge.py` 里只有可运行的近似写法。
- [x] Dockerfile 没有先复制正确版本再改坏。
- [x] `tests/` 和 `solution/` 不在 `environment/` 的构建上下文里。
- [x] `commissioning.json` 和隐藏算例都不带现场记录；候选不能靠复制记录得分。
