# 水锤瞬变报告

城南调压站的夜班要把输水管线的水锤试验记录转成仿真报告。现场记录来自两个压力测点，一个在管线中段，一个在调压塔底部。`/app/surge.py` 现在能跑，但最近几条线的峰值、末态水头和波到达时间跟记录对不上。

## 现场情况

`/app/cases/commissioning.json` 是一条 HDPE 管线的交接算例，里面附了 `measured` 现场记录，可以直接和程序输出对照。`/app/cases/steady.json` 是一条简单管线，用来确认输入输出能走通。

管线的支承方式不统一：有的段落用伸缩节，允许轴向自由变形；有的段落用锚固墩固定。输入里的 `axial_restraint` 会写 `free` 或 `anchored`。锚固段的压力波速要按管道的轴向约束计算，不能和伸缩节段用同一个值。锚固段的压力波到达时间比同壁厚的伸缩节段早；现有工具把两段算成一样。

旧钢管的内壁粗糙度会随运行年限变大。粗糙旧管在高流量下，首端稳态压力比工具算的低；流量越大，偏差越明显。

调压塔的气垫在快速关阀时压缩得很快，塔内水位也会跟着变化。快速关阀时，调压塔的峰值水头和末态水头与现场记录对不上；关阀慢、塔面积大的工况偏差较小。

## 要交付的内容

修好 `/app/surge.py`。用法是：

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

报告要写出波速、摩阻系数、塔端峰值水头、末态水头和两个测点的水头序列。参数个数不对时退出码为 2，不写报告文件。

## 约束

- 只使用 Python 标准库。
- 同一份输入重复运行，结果必须一致。
- `commissioning.json` 里的 `measured` 只用于对照，程序不能依赖它；新算例不一定带这段记录。
