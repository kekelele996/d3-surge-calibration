# 水锤瞬变报告

城南调压站上周做了一次关阀试验，中段和塔底各布了一个压力测点。记录交到仿真组，`/app/surge.py` 跑出来的峰值、末段水头和波到达时间跟纸面记录对不上。夜班要先把这个入口修好，白班才能拿它复核别的线。这次只复核 commissioning 一条线，steady 用来试入口。

## 现场情况

`/app/surge.py` 跑出来的波速、首端稳态压力、塔端峰值和末段水头跟纸带对不上。管材、支承和粗糙度那套已经核过，问题不在那里。

`/app/cases/commissioning.json` 是 commissioning 线的记录，纸带在桌上，算例文件里不附现场水头；`steady.json` 是更早的短管，格式一样，先拿它试一下入口。

这段液体里夹着气泡，含气率按体积分数给，气泡按等温膨胀算。老钢管这段关阀不到 1 s，瞬变摩阻不能只用稳态值。调压塔气室只有几十升，气室和塔壁有传热；阀门开度按 position_table 给。

## 要交付的内容

修好 `/app/surge.py`，用法不变：

`python3 /app/surge.py <case.json> <report.json>`

输入 JSON 分五段：fluid 是流体物性，pipe 是管道几何和支承，valve 是阀门，surge_tank 是调压塔，measurement 是采样时刻和测点。fluid 里可能有 air_fraction 和 reference_pressure；pipe 里可能有 unsteady_coefficient；surge_tank 里可能有 gas_temperature、wall_temperature、heat_transfer_coefficient、gas_constant、cv；valve 里可能有 position_table。没有这些键就按 0 或默认值处理。

输出写到第二个参数指定的文件，是一个 JSON 对象：

- `case_id`：原样抄回。
- `wave_speed_m_s`：按管材、壁厚、支承和含气率算出的压力波速，m/s。
- `friction_factor`：按初始流量算出的达西摩阻系数，无量纲。
- `peak_head_m`：塔端水头序列的最大值，m。
- `final_head_m`：塔端水头序列末段 10% 采样的平均值，m。
- `station_heads`：键是测点 `id`，值是按 `times` 顺序排列的水头，m。

数值对到厘米，序列长度和 times 一样。报告里的字段集合恰好是六项，不能多也不能少。现场记录只到两个测点，不要加中间节点。参数个数不对时退出码为 2，不写报告文件。

## 约束

- 只使用 Python 标准库。报告只写一个文件，不改输入，不留旧结果。
- 水头用米，波速用米每秒，摩阻系数不带量纲；时间按秒，距离按米，序列按 times 从小到大。
- 同一份输入两次跑出来的数要一样，字段名和单位不要改。
- 同一份输入重复运行，结果必须一致。
- 算例文件里不一定带现场水头记录；程序不能依赖它，也不能从纸带抄答案。
