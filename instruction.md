# 区域供热管网水力-热力仿真

城南供热站上周的调度记录和仿真组的结果对不上。管网不是一根管：泵从回水母管抽水，送到供水母管，两路支管在末端汇合，用户支路又把供水和回水连起来。有的支路带保温，有的管段是环路边。

要修的是 `/app/dhn.py`。它读一个算例 JSON，写出一份管网报告。

## 算例里有什么

`fluid` 给密度、比热和运动黏度；`ambient.ground_temperature` 是地温；`plant` 给供水温度、供/回水节点、泵曲线（一串 `[流量, 扬程]` 点）和转速；`pipes` 每根管给 `id`、起止节点、长度、直径、粗糙度、局部损失，有保温的再给保温层厚度和导热系数，环路边会带 `"loop": true`；`consumers` 给供热负荷、阀门 `kv` 和开度；`measurement` 给时长、采样时刻和测点。

## 报告要写什么

JSON 对象，字段就这些，不多不少：

```
case_id
pipe_flows_kg_s        每根管的质量流量，kg/s
node_pressures_kpa     每个节点的表压，kPa
pump_head_kpa          泵扬程，kPa
pump_flow_kg_s         泵质量流量，kg/s
consumer_flow_kg_s     每个用户的质量流量，kg/s
consumer_heat_kw       每个用户的供热功率，kW
supply_temperatures_c  供水节点温度，°C
return_temperatures_c  回水节点温度，°C
plant_return_c         热源回水温度，°C
station_temperatures   每个测点的温度序列，°C
```

数值留 4 到 6 位小数，同一个算例跑两遍结果要完全一样。参数个数不对就退 2。

## 几个容易做错的地方

环路边的流量不能当成零，泵曲线不是一条直线，阀门开度决定支路流量。保温层要真的算进沿程热损，节点混合按流量加权，不能取算术平均。瞬态要保留管段的输运延迟和热惯性，`supply_profile` / `load_profile` 是阶跃或折线。

只用 Python 标准库。`/app/cases` 里只有两份交接算例；隐藏算例不带现场温度记录，别把可见算例的结果抄成常数。
