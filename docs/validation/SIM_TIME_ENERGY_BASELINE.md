# 仿真时间与能量最小基线

此模块是独立、确定性的工程实验入口：`ems_simulator.time_energy.simulate_time_energy`。它读取调用方给出的有限功率区间，以仿真秒数积分，返回不可变的逐段实际功率、SOC 与能量结果。它不接入既有 24 小时日仿真、EMS 决策或边缘执行链路。

## 时间口径

- `physical_step_seconds`：物理计算的最大步长。输入功率发生变化或 SOC 达到边界时还会提前分段。
- `decision_seconds`、`forecast_seconds`、`record_seconds`、`display_seconds`：分别标记控制、预测、记录、界面周期。当前实验不自动调度这些动作；仅改变它们不会改变物理结果。
- `PowerInterval.start_seconds/end_seconds`：从仿真起点算起的时间，单位秒。区间必须从 0 开始、连续且按顺序给出；重复、倒序和缺口会拒绝。
- 暂停界面或重复调用不会自动推进仿真时间；模块不保存累计状态。调用方若要表达真实物理过程中的停机，必须给出相应的仿真区间和功率事实。

## 能量与符号

每段 `energy_kwh = actual_power_kw × duration_seconds / 3600`。电池正功率为充电，负功率为放电；电网正功率为购电，负功率为卖电。电池请求功率先受功率限值和 SOC 边界约束；能量账使用实际交付功率。充电效率只作用于入库能量，放电效率只作用于库存消耗，不在电网账中再次折算。

负载、PV 或电池请求变化由调用方拆为新 `PowerInterval`。SOC 在步内达到上限或 reserve 时，结果会分成边界前交付与边界后零交付两段；电网购售电分别积分，避免整步按未执行的命令计账。

## 本阶段尚未覆盖

模块不读取真实累计电表，也不处理其复位、溢出、缺测或乱序；不含待机损耗、响应延迟、Zero Export/Grid Charging 开关、预测器、控制调度或真实设备测量。`actual_battery_power_kw` 是仿真模型的交付值，不是 PCS 遥测或硬件执行证明。记录周期和界面周期目前没有采样器实现。

## 最小验证

```powershell
python -m pytest tests/unit/ems_simulator/test_time_energy.py -p no:cacheprovider --basetemp <全新专用临时目录>
```

测试覆盖 1 kW 持续 1 小时、物理步长变化、独立记录/决策周期、PV 阶跃、SOC 触顶触底、请求与实际交付分离、效率一次作用、重复求值与无效时间区间拒绝。
