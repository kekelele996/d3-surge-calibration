# 水锤瞬变报告

城南调压站上周做了一次关阀试验，中段和塔底各布了一个压力测点。记录交到仿真组，`/app/surge.py` 跑出来的峰值、末段水头和波到达时间跟纸面记录对不上。夜班要先把这个入口修好，白班才能拿它复核别的线。

## 现场情况

上周三的关阀试验，老周把中段和塔底两个测点的纸带交给仿真组。`/app/surge.py` 跑出来的波速、首端稳态压力、塔端峰值和末段水头跟纸带对不上。

`/app/cases/commissioning.json` 是那次 HDPE 管的记录，`measured` 里是现场水头；`steady.json` 是更早的短管，格式一样，先拿它试一下入口。

这条线一段埋在锚固墩里，一段装了伸缩节。旧钢管这段粗糙度 0.15 到 0.25 mm。调压塔气室只有几十升，关阀不到 1 s。具体差多少，拿 commissioning 的 measured 对一下就知道了。

## 要交付的内容

修好 `/app/surge.py`，用法不变：

`python3 /app/surge.py <case.json> <report.json>`

输入 JSON 的字段：

- `case_id`：算例编号。
- `fluid`：`density`（kg/m³）、`bulk_modulus`（Pa）、`kinematic_viscosity`（m²/s）。
- `pipe`：`length`、`diameter`、`wall_thickness`、`youngs_modulus`（Pa）、`poisson_ratio`、`roughness`（m）、`axial_restraint`。
- `valve`：`area`（m²）、`discharge_coefficient`、`closure_time`（s）。
- `surge_tank`：`area`（m²）、`gas_volume`（m³）。
- `reservoir_head`、`downstream_head`：水头，m。
- `measurement`：`duration`（s）、`times`（s 的升序数组）、`stations`（每个含 `id` 和 `distance`，m）。

输出写到第二个参数指定的文件，是一个 JSON 对象：

- `case_id`：原样抄回。
- `wave_speed_m_s`：按管材、壁厚和支承方式算出的压力波速，m/s。
- `friction_factor`：按初始流量算出的达西摩阻系数，无量纲。
- `peak_head_m`：塔端水头序列的最大值，m。
- `final_head_m`：塔端水头序列末段 10% 采样的平均值，m。
- `station_heads`：键是测点 `id`，值是按 `times` 顺序排列的水头，m。

报告的结构是：

```json
{
  "case_id": "字符串",
  "wave_speed_m_s": "数值",
  "friction_factor": "数值",
  "peak_head_m": "数值",
  "final_head_m": "数值",
  "station_heads": {"测点 id": ["数值", "..."]}
}
```

报告里的字段集合恰好是六项，不能多也不能少。参数个数不对时退出码为 2，不写报告文件。

## 约束

- 只使用 Python 标准库。
- 同一份输入重复运行，结果必须一致。
- `commissioning.json` 里的 `measured` 只用于对照，程序不能依赖它；新算例不一定带这段记录。
