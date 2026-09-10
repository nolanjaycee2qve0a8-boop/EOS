# Residential Edge P0.9 Device-Fact Readiness 学习指南

## 1. 一句话目标

P0.9 是一个 test-only、同步、caller-driven 的确定性 evaluator：它把 caller 给出的设备事实评为 immutable PASS/GAP，而不是发命令、连接设备或推进控制周期。

## 2. 工程问题与架构位置

真实设备接入前，工程团队需要先问“当前被声明的事实是否足够、相互一致且仍新鲜”，而不是把 ACK 或某个 telemetry 字段误当作执行完成。

```text
caller profile + policy(max_age) + evidence + explicit as_of
                         │
                         ▼
      DeterministicDeviceFactReadinessEvaluator.evaluate
                         │
                         ▼
          immutable PASS/GAP audit assessment
```

P0.3 runtime、P0.4 adapter、P0.5 handoff 和 P0.6–P0.8 是事实/authority 分层的语义来源；P0.9 不导入、调用或替代它们。

## 3. 输入、输出与正常/故障路径

输入是 `DeviceFactCapabilityProfile`、每项 `DeviceFactRequirementPolicy`、`DeviceFactEvidenceSample` 和 `DeviceFactReadinessInput.as_of`。caller 显式拥有 `as_of` 与 `maximum_age`；不存在 global clock 或默认阈值。输出是 immutable assessment 与 requirement finding。

六项要求分别覆盖 identity/provenance、availability/time、ACK ID/sequence/correlation、actual presence、disconnect/reboot 及 fresh reassessment。缺失、future、stale、mismatch、disconnect 或 reboot 都形成 GAP；不猜测零功率、不自动恢复或重试。

## 4. Authority 与安全边界

| 事实 | P0.9 可做 | P0.9 不可做 |
| --- | --- | --- |
| ACK | 核对 identity/correlation | 证明 actual、physical completion 或 hardware readiness |
| actual sample | 核对 presence | 覆盖 P0.3 reconciliation 或取得 device authority |
| PASS/GAP assessment | 提供审计结论 | 创建 command、adapter、runtime、session 或 handoff |

证据和值对象不携带 factory、hydration、历史 replay 或 command authority。这是软件合同边界，不是协议安全、Python sandbox 或硬件权限系统。

## 5. API 导航与最小确定性示例

入口在 `edge_runtime/device_fact_readiness/__init__.py`，实现位于 `evaluator.py`，focused tests 位于 `tests/unit/edge_runtime/test_device_fact_readiness.py`。

```python
from datetime import UTC, datetime, timedelta

from edge_runtime.device_fact_readiness import (
    DeterministicDeviceFactReadinessEvaluator,
    DeviceFactAvailability,
    DeviceFactCapabilityProfile,
    DeviceFactEvidenceSample,
    DeviceFactReadinessInput,
    DeviceFactRequirement,
    DeviceFactRequirementPolicy,
)

requirements = frozenset(DeviceFactRequirement)
profile = DeviceFactCapabilityProfile(
    "profile-a", "source-a", "prov-a", "boot-a", requirements
)
as_of = datetime(2034, 1, 1, tzinfo=UTC)
policies = tuple(
    DeviceFactRequirementPolicy(item, timedelta(minutes=5)) for item in requirements
)


def sample(item: DeviceFactRequirement) -> DeviceFactEvidenceSample:
    ack = (
        {
            "request_id": "request-a",
            "request_sequence": 7,
            "request_correlation_id": "correlation-a",
            "acknowledgement_request_id": "request-a",
            "acknowledgement_sequence": 7,
            "acknowledgement_correlation_id": "correlation-a",
        }
        if item is DeviceFactRequirement.ACK_CORRELATION
        else {}
    )
    return DeviceFactEvidenceSample(
        f"fact-{item}",
        item,
        "source-a",
        "prov-a",
        "boot-a",
        "assessment-a",
        "evidence-a",
        as_of,
        DeviceFactAvailability.AVAILABLE,
        actual_present=item is DeviceFactRequirement.ACTUAL_TELEMETRY,
        **ack,
    )


evidence = tuple(sample(item) for item in requirements)
assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
    DeviceFactReadinessInput(
        "assessment-a", "evidence-a", profile, policies, evidence, as_of
    )
)
```

该示例不创建 command、不发送协议、不执行设备；它只读取 `assessment.status` 与 findings。

## 6. 验证、mutation 与实际系统映射

ACK requirement 的六个 request/ACK ID、sequence 与 correlation 字段必须全部明确存在并完全一致；all-None 不是有效 ACK，而是 fail-closed GAP。

最终本地候选证据包括 P0.1–P0.9 focused、Residential frozen `530 passed, 62 deselected`、Campaign A–F `62 passed in 978.15s`、full pytest `2736 passed in 716.52s`、静态门禁及 pre-commit 四 hook exit 0。七个有效 mutation（identity/provenance、future timestamp、supplied ACK mismatch、missing six ACK fields、actual presence、reassessment、package-level forbidden ImportFrom alias）均被测试杀死；早期一次错误导入正式模块的 mutation 尝试无效，未计入证据。独立学习材料审阅、本地 integration、独立最终审阅、用户批准 push、Draft PR、remote Quality checks SUCCESS 与 PR #203 的普通 main merge 已完成（`4690d47cbfa4cac0ae4eb4e9a27b722d68aa17a7`）。该仓库合并不是硬件、现场或产品发布结论；任何后续能力仍须 capability-gap review 与显式用户批准。

未来 PCS/BMS 可把真实 observation、ACK 与 telemetry 映射为 caller facts；当前没有 protocol/network/HTTP/Modbus/CAN/serial、thread/scheduler/persistence/auto-retry、HIL、PCS/BMS connection、DSP/STM32、hardware control 或 field deployment。

## 7. 学习成果与一页总结

读者应能区分“事实满足声明语义”与“设备已执行”，理解 freshness 必须由 caller 显式定义，并能解释为什么 ACK、actual、reconciliation 与 command authority 不能混用。P0.9 的价值是把未来设备事实接入前的证据口径变为可测试、可审计的本地合同；它不是硬件 readiness 或产品发布结论。
