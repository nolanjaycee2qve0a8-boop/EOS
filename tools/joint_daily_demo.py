"""Independent daily joint simulation. The legacy Demo is never replaced."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from tools.dynamic_constraint_probe import Case
from tools.joint_daily_output import report_status, write_daily_output
from tools.joint_execution_contract import (
    DailyEvent,
    JointExecutionContext,
    daily_case,
    finite_number,
    validate_daily_case,
)
from tools.pv_grid_charge_joint_probe import JointResult, run_joint


def run_daily_case(
    case: Case,
    *,
    mode: str,
    physical_step_s: float = 60,
    record_period_s: int = 60,
    display_period_s: int = 5,
) -> JointResult:
    context = JointExecutionContext()
    validate_daily_case(case, context)
    if finite_number(physical_step_s, "physical step") <= 0:
        raise ValueError("physical step must be positive")
    for period in (record_period_s, display_period_s):
        if type(period) is not int or period <= 0:
            raise ValueError("view periods must be positive integers")
    return run_joint(
        case,
        mode=mode,
        physical_step_s=physical_step_s,
        record_period_s=record_period_s,
        display_period_s=display_period_s,
        context=context,
    )


def run_daily(
    output: Path,
    *,
    mode: str,
    physical_step_s: float = 60,
    record_period_s: int = 60,
    display_period_s: int = 5,
    case: Case | None = None,
) -> JointResult:
    if not isinstance(output, Path):
        raise TypeError("output must be a Path")
    case = daily_case() if case is None else case
    validate_daily_case(case, JointExecutionContext())
    # A new run never overwrites an old directory, even when the old run failed.
    output.mkdir(parents=True, exist_ok=False)
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps({"state": "running"}), encoding="utf-8")
    try:
        result = run_daily_case(
            case,
            mode=mode,
            physical_step_s=physical_step_s,
            record_period_s=record_period_s,
            display_period_s=display_period_s,
        )
        summary = write_daily_output(
            result,
            output,
            record_period_s=record_period_s,
            display_period_s=display_period_s,
        )
        state = "completed" if summary["assessment"] == "PASS" else "failed_acceptance"
        manifest.write_text(
            json.dumps(
                {
                    "state": state,
                    "assessment": summary["assessment"],
                    "pause_resume": False,
                }
            ),
            encoding="utf-8",
        )
        return result
    except Exception as exc:
        manifest.write_text(
            json.dumps(
                {"state": "failed", "error_type": type(exc).__name__, "error": str(exc)}
            ),
            encoding="utf-8",
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("ideal", "dynamic"), required=True)
    parser.add_argument("--step", type=float, default=60)
    parser.add_argument("--record-period", type=int, default=60)
    parser.add_argument("--display-period", type=int, default=5)
    parser.add_argument("--initial-soc", type=float, default=0.5)
    parser.add_argument(
        "--events", type=Path, help="JSON array of explicit DailyEvent facts"
    )
    args = parser.parse_args()
    events: tuple[DailyEvent, ...] = ()
    if args.events:
        data = json.loads(args.events.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            parser.error("events must be a JSON array")
        events = tuple(DailyEvent(**item) for item in data)
    case = replace(daily_case(events=events), initial_soc=args.initial_soc)
    result = run_daily(
        args.output,
        mode=args.mode,
        physical_step_s=args.step,
        record_period_s=args.record_period,
        display_period_s=args.display_period,
        case=case,
    )
    status, reasons = report_status(result)
    print(
        f"UTC day finished: assessment={status}; SOC={result.execution.final_soc}; "
        f"limitations={reasons}"
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
