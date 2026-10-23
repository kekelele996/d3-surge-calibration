# 参考解说明

入口：`/app/dhn.py`，只依赖 Python 标准库。读算例 JSON，写第二个命令行参数指定的报告 JSON。

## 三个难点与测试

### D1 多环水力（0.40）
- 参考解：`hydraulic()` 用节点水头法，管段 Q=sign(dH)sqrt(|dH|/R)，泵曲线二次拟合 + 相似律，用户支路 Q=kv*pos*sqrt(dP)，Newton 解节点水头。
- 错误环境：`active_pipes()` 过滤掉 `"loop": true` 的环路边，PS3/PR3 直接变 0，节点压力重新分配。
- 测试：`test_loop_flow_a`（hyd_1 PS3）、`test_loop_flow_b`（hyd_2 PR3）、`test_loop_pressure_c`（hyd_3 S2 压力）。
- 容差：流量 0.03 kg/s、压力 0.5 kPa；参考解与独立回路法差 < 1e-4 kg/s，远小于容差。

### D2 沿程热损与节点混合（0.30）
- 参考解：保温层单位长度热阻 R'=ln((r+t)/r)/(2 pi k)，UA=L/R'，T_out=T_amb+(T_in-T_amb)exp(-UA/(m cp))；节点按流量加权混合；用户 T_r=T_s-P/(m cp)。
- 错误环境：`pipe_outlet_temp()` 直接返回入口温度，等于热损为 0。
- 测试：`test_supply_temp_a`（therm_1 S1）、`test_plant_return_b`（therm_2 热源回水）、`test_return_temp_c`（therm_3 R1）。
- 容差 0.3 °C；参考解与独立解析单管+混合差 < 0.02 °C。

### D3 输运延迟与热惯性（0.30）
- 参考解：管段驻留时间 tau=rho A L / m，出口用 t-tau 的入口温度再做热损，节点按流量混合；初始从稳态启动。
- 错误环境：`pipe_delay()` 返回 0，瞬态变成瞬时响应。
- 测试：`test_transient_a/b/c/d`，分别看 trans_1 S1、trans_2 S2、trans_3 S1、trans_3 R0。
- 容差逐点 1.5 °C；参考解与独立阶跃到达时刻估计差 < 1 个采样间隔。

## 独立复核
`research/verify_hydraulic.py`、`verify_thermal.py`、`verify_delay.py`、`verify_friction.py`、`verify_pump.py`；`research/claims.json` 里每条 claim 都有参考解路径和独立路径。

## 全修与留一法
- 全修：Oracle 2/2 = 1.0。
- 只留 D1 错：0.6；只留 D2 错：0.7；只留 D3 错：0.7；全错：0.0。
