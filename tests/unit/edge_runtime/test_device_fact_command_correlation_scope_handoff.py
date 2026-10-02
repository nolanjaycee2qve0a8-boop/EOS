"""P0.13 contract assertions using real, independently audited P0.11 raw facts."""

from __future__ import annotations

import ast
import copy
import inspect
import pickle
from dataclasses import FrozenInstanceError, asdict, fields, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from itertools import product
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from edge_runtime.device_fact_command_correlation import (
    DeterministicDeviceFactCommandCorrelationAuditor,
    DeviceFactAcknowledgementObservation,
    DeviceFactActualObservation,
)
from edge_runtime.device_fact_command_correlation import (
    DeviceFactCommandCorrelationAvailability as Availability,
)
from edge_runtime.device_fact_command_correlation import (
    DeviceFactCommandCorrelationInput as Member,
)
from edge_runtime.device_fact_command_correlation import (
    DeviceFactSourceEpochRelationship as Relationship,
)
from edge_runtime.device_fact_command_correlation import (
    DeviceFactTransmissionIdentity as Transmission,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeterministicDeviceFactCommandCorrelationContinuityAuditor as Predecessor,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeviceFactCommandCorrelationContinuityAssessment as PredecessorAssessment,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeviceFactCommandCorrelationContinuityInput as RawScope,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeviceFactCommandCorrelationContinuityScope as Scope,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeviceFactCommandCorrelationContinuityStatus as PredecessorStatus,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeterministicDeviceFactCommandCorrelationScopeHandoffAuditor as Auditor,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeFacts as Facts,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffAssessment as Assessment,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffDeclaration as Declaration,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffFinding as Finding,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffGapCode as Gap,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffInput as Input,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import (
    DeviceFactCommandCorrelationScopeHandoffStatus as Status,
)
from edge_runtime.device_fact_command_correlation_scope_handoff import evaluator

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)
AGE = timedelta(minutes=5)


def relationship(source: str = "source-a", epoch: str = "epoch-a") -> Relationship:
    return Relationship(source, epoch, source, epoch, source, epoch)


def member(
    index: int,
    sequence: int,
    minute: int,
    *,
    source: str = "source-a",
    epoch: str = "epoch-a",
    origin: str = "caller",
) -> Member:
    time = NOW + timedelta(minutes=minute)
    return Member(
        f"member-{index}",
        time,
        AGE,
        Transmission(
            f"tx-{index}", sequence, origin, time - timedelta(seconds=2), source, epoch
        ),
        DeviceFactAcknowledgementObservation(
            f"tx-{index}",
            sequence,
            origin,
            time - timedelta(seconds=1),
            source,
            epoch,
            Availability.AVAILABLE,
        ),
        DeviceFactActualObservation(
            f"actual-{index}",
            time - timedelta(seconds=1),
            source,
            epoch,
            Availability.AVAILABLE,
            1.25,
        ),
        relationship(source, epoch),
    )


def request() -> Input:
    previous = RawScope(
        "p12-a",
        NOW,
        AGE,
        Scope("scope-a", "caller", relationship()),
        (member(1, 9, -4), member(2, 10, -3)),
    )
    following = RawScope(
        "p12-b",
        NOW,
        AGE,
        Scope("scope-b", "caller", relationship()),
        (member(3, 12, -2), member(4, 13, -1)),
    )
    # Literal expectations do not use the evaluator or a shared boundary producer.
    declaration = Declaration(
        Scope("scope-a", "caller", relationship()),
        Scope("scope-b", "caller", relationship()),
        "member-2",
        "member-3",
        10,
        12,
        NOW - timedelta(minutes=3),
        NOW - timedelta(minutes=2),
        2,
        timedelta(minutes=1),
        "distinct",
    )
    return Input("p13-new", NOW, AGE, (Facts(previous), Facts(following)), declaration)


def raw(value: Input, index: int) -> RawScope:
    return cast(RawScope, cast(Facts, value.scopes[index]).continuity_input)


def with_raw(value: Input, index: int, replacement: object) -> Input:
    scopes = list(value.scopes)
    scopes[index] = Facts(replacement)
    return replace(value, scopes=tuple(scopes))


def with_member(
    value: Input, scope_index: int, member_index: int, replacement: object
) -> Input:
    original = raw(value, scope_index)
    members = list(original.members)
    members[member_index] = replacement
    return with_raw(value, scope_index, replace(original, members=tuple(members)))


def declared(value: Input, **changes: object) -> Input:
    return replace(
        value, declaration=replace(cast(Declaration, value.declaration), **changes)
    )


def assert_gap(value: Input, expected: Gap) -> Assessment:
    result = Auditor().evaluate(value)
    assert result.status is Status.GAP
    assert expected in {finding.gap_code for finding in result.findings}
    return result


def test_real_raw_scopes_pass_with_explicit_10_to_12_advance() -> None:
    value = request()
    assert all(
        Predecessor().evaluate(raw(value, i)).status is PredecessorStatus.PASS
        for i in (0, 1)
    )
    result = Auditor().evaluate(value)
    assert result == Assessment("p13-new", NOW, Status.PASS, ())


def test_each_scope_delegates_once_preserving_exact_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = request()
    calls: list[RawScope] = []
    upstream = Predecessor.evaluate

    def counted(self: Predecessor, item: object) -> PredecessorAssessment:
        assert isinstance(item, RawScope)
        calls.append(item)
        return upstream(self, item)

    monkeypatch.setattr(Predecessor, "evaluate", counted)
    before = copy.deepcopy(value)
    assert Auditor().evaluate(value).status is Status.PASS
    assert len(calls) == 2
    assert calls[0] is raw(value, 0) and calls[1] is raw(value, 1)
    assert value == before


@pytest.mark.parametrize("index", [0, 1])
def test_predecessor_gap_still_calls_other_scope_once_and_blocks_handoff(
    index: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    scope = raw(value, index)
    value = with_raw(
        value, index, replace(scope, members=tuple(reversed(scope.members)))
    )
    calls: list[object] = []
    upstream = Predecessor.evaluate

    def counted(self: Predecessor, item: object) -> PredecessorAssessment:
        calls.append(item)
        return upstream(self, item)

    def forbidden(*args: object) -> list[Finding]:
        pytest.fail("handoff must not inspect scopes before both P0.12 PASS")

    monkeypatch.setattr(Predecessor, "evaluate", counted)
    monkeypatch.setattr(Auditor, "_handoff", forbidden)
    assert_gap(value, Gap.P0_12_GAP)
    assert len(calls) == 2
    assert calls[0] is raw(value, 0) and calls[1] is raw(value, 1)


@pytest.mark.parametrize(
    "scopes",
    [
        (),
        (Facts(None),),
        (Facts(None),) * 3,
        (None, None),
        ({"status": "pass"}, "pass"),
    ],
)
def test_exactly_two_raw_scopes_required(scopes: tuple[object, ...]) -> None:
    assert_gap(replace(request(), scopes=scopes), Gap.INVALID_SCOPE)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize(
    "kind",
    [
        "absent",
        "object",
        "assessment",
        "serialized",
        "summary",
        "p11_assessment",
        "missing_scope",
        "missing_member",
        "subclass",
    ],
)
def test_historical_malformed_and_authority_scopes_rejected(
    index: int, kind: str
) -> None:
    value = request()
    original = raw(value, index)
    historical = Predecessor().evaluate(original)

    class AuthorityScope(RawScope):
        def execute(self) -> None:
            pytest.fail("authority must never execute")

    alternatives: dict[str, object] = {
        "absent": None,
        "object": object(),
        "assessment": historical,
        "serialized": asdict(historical),
        "summary": "PASS",
        "p11_assessment": replace(
            original,
            members=(
                DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
                    original.members[0]
                ),
                original.members[1],
            ),
        ),
        "missing_scope": replace(original, scope=None),
        "missing_member": replace(original, members=(None, original.members[1])),
        "subclass": AuthorityScope(
            original.assessment_identity,
            original.assessment_as_of,
            original.maximum_age,
            original.scope,
            original.members,
        ),
    }
    assert_gap(with_raw(value, index, alternatives[kind]), Gap.INVALID_SCOPE)


@pytest.mark.parametrize("mode", ["same_instance", "same_raw", "same_identity"])
def test_duplicate_scope_gate(mode: str) -> None:
    value = request()
    if mode == "same_instance":
        value = replace(value, scopes=(value.scopes[0], value.scopes[0]))
    elif mode == "same_raw":
        value = replace(value, scopes=(value.scopes[0], Facts(raw(value, 0))))
    else:
        second = raw(value, 1)
        scope = replace(cast(Scope, second.scope), scope_identity="scope-a")
        value = declared(
            with_raw(value, 1, replace(second, scope=scope)), next_scope=scope
        )
    assert_gap(value, Gap.DUPLICATE_SCOPE)


@pytest.mark.parametrize("declaration", [None, "unknown", {"status": "pass"}, object()])
def test_missing_or_wrong_declaration_is_gap(declaration: object) -> None:
    assert_gap(replace(request(), declaration=declaration), Gap.DECLARATION_MISMATCH)


@pytest.mark.parametrize("field", ["previous_scope", "next_scope"])
@pytest.mark.parametrize(
    "change", ["identity", "origin", "source", "epoch", "unknown", "absent"]
)
def test_exact_scope_identity_origin_relationship_declaration(
    field: str, change: str
) -> None:
    value = request()
    scope = cast(Scope, getattr(value.declaration, field))
    changes: dict[str, object] = {
        "identity": replace(scope, scope_identity="wrong"),
        "origin": replace(scope, transmission_origin="wrong"),
        "source": replace(scope, source_epoch_relationship=relationship("changed")),
        "epoch": replace(
            scope, source_epoch_relationship=relationship(epoch="changed")
        ),
        "unknown": replace(scope, source_epoch_relationship="unknown"),
        "absent": None,
    }
    assert_gap(declared(value, **{field: changes[change]}), Gap.DECLARATION_MISMATCH)


@pytest.mark.parametrize(
    "relationship_field", [field.name for field in fields(Relationship)]
)
def test_all_six_source_epoch_fields_match(relationship_field: str) -> None:
    value = request()
    scope = cast(Scope, cast(Declaration, value.declaration).next_scope)
    changed = replace(relationship(), **{relationship_field: "changed"})
    assert_gap(
        declared(value, next_scope=replace(scope, source_epoch_relationship=changed)),
        Gap.DECLARATION_MISMATCH,
    )


def test_explicit_origin_source_epoch_change_is_not_lifecycle_inference() -> None:
    value = request()
    scope = Scope("scope-b", "other-caller", relationship("source-b", "epoch-b"))
    following = replace(
        raw(value, 1),
        scope=scope,
        members=(
            member(
                3, 12, -2, source="source-b", epoch="epoch-b", origin="other-caller"
            ),
            member(
                4, 13, -1, source="source-b", epoch="epoch-b", origin="other-caller"
            ),
        ),
    )
    changed = with_raw(value, 1, following)
    assert_gap(changed, Gap.DECLARATION_MISMATCH)
    assert Auditor().evaluate(declared(changed, next_scope=scope)) == Assessment(
        "p13-new", NOW, Status.PASS, ()
    )


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("previous_terminal_identity", "member-1"),
        ("next_initial_identity", "member-4"),
        ("previous_terminal_identity", None),
        ("next_initial_identity", "unknown"),
        ("previous_terminal_sequence", 9),
        ("next_initial_sequence", 13),
        ("previous_terminal_sequence", True),
        ("next_initial_sequence", 12.0),
        ("previous_terminal_as_of", NOW - timedelta(minutes=4)),
        ("next_initial_as_of", NOW - timedelta(minutes=1)),
        ("previous_terminal_as_of", None),
        ("next_initial_as_of", NOW.replace(tzinfo=None)),
    ],
)
def test_only_actual_terminal_initial_boundary_is_accepted(
    field: str, replacement: object
) -> None:
    assert_gap(declared(request(), **{field: replacement}), Gap.BOUNDARY_MISMATCH)


@pytest.mark.parametrize("advance", [None, "unknown", 0, -1, True, 2.0, 1, 3])
def test_sequence_advance_must_be_explicit_positive_exact(advance: object) -> None:
    assert_gap(
        declared(request(), sequence_advance=advance), Gap.SEQUENCE_RELATION_INVALID
    )


@pytest.mark.parametrize(
    "advance",
    [
        None,
        "unknown",
        timedelta(0),
        timedelta(minutes=-1),
        timedelta(seconds=59),
        timedelta(minutes=2),
    ],
)
def test_time_advance_must_be_explicit_positive_exact(advance: object) -> None:
    assert_gap(declared(request(), time_advance=advance), Gap.TIME_RELATION_INVALID)


@pytest.mark.parametrize("sequence", [8, 9, 10])
def test_global_sequence_reverse_duplicate_or_overlap_not_sorted(sequence: int) -> None:
    value = with_member(request(), 1, 0, member(3, sequence, -2))
    value = declared(
        value, next_initial_sequence=sequence, sequence_advance=sequence - 10
    )
    assert Predecessor().evaluate(raw(value, 1)).status is PredecessorStatus.PASS
    assert_gap(value, Gap.SEQUENCE_RELATION_INVALID)


@pytest.mark.parametrize("minute", [-5, -4, -3])
def test_global_time_reverse_duplicate_or_overlap_not_sorted(minute: int) -> None:
    value = with_member(request(), 1, 0, member(3, 12, minute))
    value = declared(
        value,
        next_initial_as_of=NOW + timedelta(minutes=minute),
        time_advance=timedelta(minutes=minute + 3),
    )
    assert Predecessor().evaluate(raw(value, 1)).status is PredecessorStatus.PASS
    assert_gap(value, Gap.TIME_RELATION_INVALID)


def test_scope_order_is_not_repaired() -> None:
    value = request()
    assert_gap(
        replace(value, scopes=tuple(reversed(value.scopes))),
        Gap.SEQUENCE_RELATION_INVALID,
    )


@pytest.mark.parametrize(
    "mode",
    [
        "new_id",
        "scope_id",
        "member_id",
        "transmission_id",
        "actual_id",
        "unknown_member",
    ],
)
def test_cross_scope_identity_uniqueness(mode: str) -> None:
    value = request()
    item = cast(Member, raw(value, 1).members[1])
    if mode == "new_id":
        value = replace(value, assessment_identity="member-1")
    elif mode == "scope_id":
        value = with_raw(value, 1, replace(raw(value, 1), assessment_identity="p12-a"))
    elif mode == "member_id":
        value = with_member(value, 1, 1, replace(item, assessment_identity="member-1"))
    elif mode == "unknown_member":
        value = with_member(value, 1, 1, replace(item, assessment_identity="unknown"))
    elif mode == "transmission_id":
        value = with_member(
            value,
            1,
            1,
            replace(
                item,
                transmission=replace(
                    cast(Transmission, item.transmission), transmission_identity="tx-1"
                ),
                acknowledgement=replace(
                    cast(DeviceFactAcknowledgementObservation, item.acknowledgement),
                    transmission_identity="tx-1",
                ),
            ),
        )
    else:
        value = with_member(
            value,
            1,
            1,
            replace(
                item,
                actual=replace(
                    cast(DeviceFactActualObservation, item.actual),
                    observation_identity="actual-1",
                ),
            ),
        )
    assert_gap(value, Gap.IDENTITY_MISMATCH)


@pytest.mark.parametrize(
    "relation", [None, "same", "unknown", "physical_completion", "reconciled", "reboot"]
)
def test_only_explicit_distinct_member_audit_relation(relation: object) -> None:
    assert_gap(
        declared(request(), member_identity_relationship=relation),
        Gap.DECLARATION_MISMATCH,
    )


@pytest.mark.parametrize(
    "as_of, age",
    [
        (NOW, timedelta(minutes=3)),
        (NOW + timedelta(minutes=6), AGE),
        (NOW - timedelta(seconds=1), AGE),
    ],
)
def test_new_freshness_checks_entire_range_and_predecessor_as_of(
    as_of: datetime, age: timedelta
) -> None:
    assert_gap(
        replace(request(), assessment_as_of=as_of, maximum_age=age),
        Gap.TIME_SCOPE_INVALID,
    )


def test_freshness_exact_boundary_passes() -> None:
    assert (
        Auditor().evaluate(replace(request(), maximum_age=timedelta(minutes=4))).status
        is Status.PASS
    )


@pytest.mark.parametrize(
    "fact",
    [
        "ack_missing",
        "ack_mismatch",
        "actual_missing",
        "actual_reconciliation",
        "scope_origin",
        "scope_sequence",
        "scope_time",
        "too_few",
    ],
)
def test_real_frozen_failures_cannot_be_repaired(fact: str) -> None:
    value = request()
    item = cast(Member, raw(value, 0).members[0])
    ack = cast(DeviceFactAcknowledgementObservation, item.acknowledgement)
    actual = cast(DeviceFactActualObservation, item.actual)
    if fact == "ack_missing":
        item = replace(
            item, acknowledgement=replace(ack, availability=Availability.UNAVAILABLE)
        )
    elif fact == "ack_mismatch":
        item = replace(item, acknowledgement=replace(ack, sequence=99))
    elif fact == "actual_missing":
        item = replace(
            item, actual=replace(actual, availability=Availability.UNAVAILABLE)
        )
    elif fact == "actual_reconciliation":
        item = replace(item, actual={"reconciled": True, "actual_power_kw": 1.25})
    elif fact == "scope_origin":
        item = member(1, 9, -4, origin="outside")
    elif fact == "scope_sequence":
        item = member(1, 10, -4)
    elif fact == "scope_time":
        item = member(1, 9, -3)
    else:
        value = with_raw(value, 0, replace(raw(value, 0), members=(item,)))
    if fact != "too_few":
        value = with_member(value, 0, 0, item)
    assert_gap(
        value, Gap.INVALID_SCOPE if fact == "actual_reconciliation" else Gap.P0_12_GAP
    )


def test_deterministic_stateless_inert_and_no_future_authority() -> None:
    value = request()
    before = copy.deepcopy(value)
    auditor = Auditor()
    result = auditor.evaluate(value)
    assert auditor.evaluate(copy.deepcopy(value)) == result == Auditor().evaluate(value)
    assert_gap(declared(value, sequence_advance=None), Gap.SEQUENCE_RELATION_INVALID)
    assert auditor.evaluate(value) == result
    assert value == before
    assert auditor.__slots__ == () and not hasattr(auditor, "__dict__")
    assert tuple(inspect.signature(auditor.evaluate).parameters) == ("value",)
    assert {name for name in dir(auditor) if not name.startswith("_")} == {"evaluate"}
    assert {field.name for field in fields(result)} == {
        "assessment_identity",
        "assessment_as_of",
        "status",
        "findings",
    }
    assert {field.name for field in fields(Finding)} == {
        "scope_index",
        "gap_code",
        "detail",
    }
    for evidence in (
        result,
        copy.copy(result),
        copy.deepcopy(result),
        pickle.loads(pickle.dumps(result)),
    ):
        assert evidence == result
        assert not any(
            callable(getattr(evidence, name))
            for name in dir(evidence)
            if not name.startswith("_")
        )
        with pytest.raises(TypeError):
            auditor.evaluate(evidence)
        assert_gap(with_raw(value, 0, evidence), Gap.INVALID_SCOPE)
    for immutable, field_name in (
        (value, "assessment_identity"),
        (value.scopes[0], "continuity_input"),
        (value.declaration, "previous_scope"),
        (result, "status"),
        (Finding(None, Gap.INVALID_SCOPE, "gap"), "detail"),
    ):
        assert not hasattr(immutable, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(immutable, field_name, None)


@pytest.mark.parametrize("value", [None, {}, "PASS", object()])
def test_outer_invalid_input_is_rejected_without_inventing_identity_or_clock(
    value: object,
) -> None:
    with pytest.raises(TypeError):
        Auditor().evaluate(value)


def test_public_surface_and_import_allowlist() -> None:
    import edge_runtime.device_fact_command_correlation_scope_handoff as public

    expected = {Auditor, Facts, Input, Declaration, Assessment, Finding, Gap, Status}
    assert set(public.__all__) == {item.__name__ for item in expected}
    assert set(Status) == {Status.PASS, Status.GAP}
    allowed = {
        "__future__",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "zoneinfo",
        "edge_runtime.device_fact_command_correlation",
        "edge_runtime.device_fact_command_correlation_continuity",
        "edge_runtime.device_fact_command_correlation_scope_handoff.contracts",
        "contracts",
        "evaluator",
    }
    package = Path(evaluator.__file__).parent
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module in allowed
            elif isinstance(node, ast.Call):
                assert not (
                    isinstance(node.func, ast.Name)
                    and node.func.id in {"eval", "exec", "open", "__import__"}
                )
                assert not (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr
                    in {
                        "now",
                        "utcnow",
                        "today",
                        "execute",
                        "send",
                        "replay",
                        "restore",
                    }
                )


def test_declared_unit_advance_also_passes() -> None:
    value = with_member(request(), 1, 0, member(3, 11, -2))
    value = declared(value, next_initial_sequence=11, sequence_advance=1)
    assert Auditor().evaluate(value).status is Status.PASS


def test_untrusted_relationship_cannot_supply_equality_authority() -> None:
    class ForgedRelationship:
        def __eq__(self, other: object) -> bool:
            pytest.fail("an authority-like object's equality must not run")

    value = request()
    scope = cast(Scope, cast(Declaration, value.declaration).next_scope)
    assert_gap(
        declared(
            value,
            next_scope=replace(scope, source_epoch_relationship=ForgedRelationship()),
        ),
        Gap.DECLARATION_MISMATCH,
    )


@pytest.mark.parametrize(
    "field, value",
    [
        ("assessment_identity", "unknown"),
        ("assessment_identity", ""),
        ("assessment_as_of", NOW.replace(tzinfo=None)),
        ("maximum_age", timedelta(seconds=-1)),
        ("maximum_age", None),
        ("scopes", []),
    ],
)
def test_invalid_envelope_rejected(field: str, value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        replace(request(), **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("index", [0, 1])
def test_unknown_scope_identity_is_gap(index: int) -> None:
    value = request()
    original = raw(value, index)
    scope = replace(cast(Scope, original.scope), scope_identity="unknown")
    value = with_raw(value, index, replace(original, scope=scope))
    value = declared(value, **{"previous_scope" if index == 0 else "next_scope": scope})
    assert_gap(value, Gap.DECLARATION_MISMATCH)


def test_output_cannot_claim_pass_with_findings_or_add_authority() -> None:
    finding = Finding(None, Gap.INVALID_SCOPE, "missing facts")
    with pytest.raises(ValueError):
        Assessment("new", NOW, Status.PASS, (finding,))
    with pytest.raises(ValueError):
        Assessment("new", NOW, Status.GAP, ())
    with pytest.raises(TypeError):
        Assessment("new", NOW, "pass", ())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Assessment("new", NOW, Status.GAP, (object(),))  # type: ignore[arg-type]
    for scope_index in (-1, 2, True):
        with pytest.raises(ValueError):
            Finding(scope_index, Gap.INVALID_SCOPE, "bad index")
    with pytest.raises(TypeError):
        Finding(None, "gap", "bad code")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Finding(None, Gap.INVALID_SCOPE, "")


# Initial independent review counterexamples, now permanent regressions.
def time_request(times: tuple[datetime, ...], as_of: datetime) -> Input:
    members = tuple(
        Member(
            f"review-m{i}",
            at,
            timedelta(hours=4),
            Transmission(f"review-t{i}", i, "caller", at, "source-a", "epoch-a"),
            DeviceFactAcknowledgementObservation(
                f"review-t{i}",
                i,
                "caller",
                at,
                "source-a",
                "epoch-a",
                Availability.AVAILABLE,
            ),
            DeviceFactActualObservation(
                f"review-a{i}", at, "source-a", "epoch-a", Availability.AVAILABLE, 1.0
            ),
            relationship(),
        )
        for i, at in enumerate(times, start=1)
    )
    first = RawScope(
        "review-p12-a",
        as_of,
        timedelta(hours=4),
        Scope("review-scope-a", "caller", relationship()),
        members[:2],
    )
    second = RawScope(
        "review-p12-b",
        as_of,
        timedelta(hours=4),
        Scope("review-scope-b", "caller", relationship()),
        members[2:],
    )
    declaration = Declaration(
        first.scope,
        second.scope,
        "review-m2",
        "review-m3",
        2,
        3,
        times[1],
        times[2],
        1,
        timedelta(minutes=10),
        "distinct",
    )
    return Input(
        "review-p13",
        as_of,
        timedelta(hours=4),
        (Facts(first), Facts(second)),
        declaration,
    )


def fold_request(folds: tuple[int, ...] = (0, 0, 0, 0)) -> Input:
    zone = ZoneInfo("America/New_York")
    times = tuple(
        datetime(2026, 11, 1, 1, minute, tzinfo=zone, fold=fold)
        for minute, fold in zip((0, 10, 20, 30), folds, strict=True)
    )
    return time_request(times, datetime(2026, 11, 1, 2, tzinfo=zone))


def assert_predecessors_pass(value: Input) -> None:
    assert all(
        Predecessor().evaluate(raw(value, index)).status is PredecessorStatus.PASS
        for index in (0, 1)
    )


def test_review_dst_backwards_handoff_is_gap() -> None:
    value = fold_request((1, 1, 0, 0))
    assert_predecessors_pass(value)
    terminal = cast(Member, raw(value, 0).members[-1]).assessment_as_of
    initial = cast(Member, raw(value, 1).members[0]).assessment_as_of
    assert terminal.astimezone(UTC) - initial.astimezone(UTC) == timedelta(minutes=50)
    assert_gap(value, Gap.TIME_RELATION_INVALID)


def test_review_dst_wrong_instant_in_declaration_is_gap() -> None:
    value = fold_request()
    assert_predecessors_pass(value)
    terminal = cast(Member, raw(value, 0).members[-1]).assessment_as_of
    wrong = terminal.replace(fold=1)
    assert wrong.astimezone(UTC) - terminal.astimezone(UTC) == timedelta(hours=1)
    assert_gap(declared(value, previous_terminal_as_of=wrong), Gap.BOUNDARY_MISMATCH)


def test_review_dst_stale_member_is_gap() -> None:
    value = fold_request()
    as_of = datetime(2026, 11, 1, 1, 50, tzinfo=ZoneInfo("America/New_York"), fold=1)
    for index in (0, 1):
        value = with_raw(
            value, index, replace(raw(value, index), assessment_as_of=as_of)
        )
    value = replace(value, assessment_as_of=as_of, maximum_age=timedelta(hours=1))
    assert_predecessors_pass(value)
    earliest = cast(Member, raw(value, 0).members[0]).assessment_as_of
    assert as_of.astimezone(UTC) - earliest.astimezone(UTC) == timedelta(minutes=110)
    assert_gap(value, Gap.TIME_SCOPE_INVALID)


def test_dst_future_member_is_gap_even_when_wall_time_looks_past() -> None:
    value = fold_request((1, 1, 1, 1))
    as_of = datetime(2026, 11, 1, 1, 50, tzinfo=ZoneInfo("America/New_York"), fold=0)
    for index in (0, 1):
        value = with_raw(
            value, index, replace(raw(value, index), assessment_as_of=as_of)
        )
    value = replace(value, assessment_as_of=as_of)
    assert_predecessors_pass(value)
    assert_gap(value, Gap.TIME_SCOPE_INVALID)


@pytest.mark.parametrize("folds", [(0, 0, 0, 0), (1, 1, 1, 1), (0, 0, 1, 1)])
def test_legal_fold_and_exact_absolute_time_advance_pass(
    folds: tuple[int, ...],
) -> None:
    value = fold_request(folds)
    advance = 70 if folds == (0, 0, 1, 1) else 10
    value = declared(value, time_advance=timedelta(minutes=advance))
    assert_predecessors_pass(value)
    assert Auditor().evaluate(value).status is Status.PASS
    # Equivalent instants in a different safe timezone are valid declarations.
    decl = cast(Declaration, value.declaration)
    value = declared(
        value,
        previous_terminal_as_of=cast(datetime, decl.previous_terminal_as_of).astimezone(
            UTC
        ),
        next_initial_as_of=cast(datetime, decl.next_initial_as_of).astimezone(UTC),
    )
    assert Auditor().evaluate(value).status is Status.PASS


@pytest.mark.parametrize(
    "zone",
    [
        UTC,
        timezone(timedelta(hours=5, minutes=30)),
        ZoneInfo("Asia/Shanghai"),
        ZoneInfo("America/New_York"),
    ],
)
def test_legal_timezones_preserve_real_delegation_and_inert_output(
    zone: tzinfo, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_of = datetime(2026, 10, 2, 12, tzinfo=zone)
    value = time_request(
        tuple(as_of - timedelta(minutes=m) for m in (40, 30, 20, 10)), as_of
    )
    calls: list[object] = []
    upstream = Predecessor.evaluate

    def counted(self: Predecessor, item: object) -> PredecessorAssessment:
        calls.append(item)
        return upstream(self, item)

    monkeypatch.setattr(Predecessor, "evaluate", counted)
    before = copy.deepcopy(value)
    result = Auditor().evaluate(value)
    assert (
        result.status is Status.PASS
        and result.assessment_as_of is value.assessment_as_of
    )
    assert calls[0] is raw(value, 0) and calls[1] is raw(value, 1) and len(calls) == 2
    assert value == before
    assert type(result.assessment_as_of.tzinfo) in (timezone, ZoneInfo)
    assert not hasattr(result.assessment_as_of.tzinfo, "__dict__")


class HookTimezone(tzinfo):
    def __init__(self, payload: object) -> None:
        self.raw = payload
        self.calls = 0

    def utcoffset(self, dt: datetime | None) -> timedelta:
        self.calls += 1
        raise AssertionError("untrusted timezone hook executed")

    def dst(self, dt: datetime | None) -> timedelta:
        raise AssertionError("untrusted timezone hook executed")

    def tzname(self, dt: datetime | None) -> str:
        raise AssertionError("untrusted timezone hook executed")

    def execute(self) -> None:
        raise AssertionError("authority must never execute")


def test_review_output_rejects_payload_timezone_without_running_hook() -> None:
    value = request()
    zone = HookTimezone(raw(value, 0))
    timestamp = NOW.replace(tzinfo=zone)
    with pytest.raises(TypeError):
        replace(value, assessment_as_of=timestamp)
    with pytest.raises(TypeError):
        Assessment("new", timestamp, Status.PASS, ())
    assert zone.calls == 0


@pytest.mark.parametrize(
    "slot",
    [
        "scope",
        "member",
        "transmission",
        "acknowledgement",
        "actual",
        "previous_terminal_as_of",
        "next_initial_as_of",
    ],
)
def test_untrusted_timezone_in_all_nested_slots_is_gap_without_hook(slot: str) -> None:
    value = request()
    zone = HookTimezone(raw(value, 0))
    timestamp = NOW.replace(tzinfo=zone)
    item = cast(Member, raw(value, 0).members[0])
    if slot == "scope":
        value = with_raw(value, 0, replace(raw(value, 0), assessment_as_of=timestamp))
    elif slot == "member":
        value = with_member(value, 0, 0, replace(item, assessment_as_of=timestamp))
    elif slot == "transmission":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                transmission=replace(
                    cast(Transmission, item.transmission), declared_at=timestamp
                ),
            ),
        )
    elif slot == "acknowledgement":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                acknowledgement=replace(
                    cast(DeviceFactAcknowledgementObservation, item.acknowledgement),
                    observed_at=timestamp,
                ),
            ),
        )
    elif slot == "actual":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                actual=replace(
                    cast(DeviceFactActualObservation, item.actual),
                    observed_at=timestamp,
                ),
            ),
        )
    else:
        value = declared(value, **{slot: timestamp})
    assert_gap(
        value, Gap.BOUNDARY_MISMATCH if slot.endswith("as_of") else Gap.INVALID_SCOPE
    )
    assert zone.calls == 0


class AuthorityTuple(tuple[object, ...]):
    def execute(self) -> None:
        raise AssertionError("authority must never execute")


class AuthorityNumber(float):
    def execute(self) -> None:
        raise AssertionError("authority must never execute")


class AuthorityString(str):
    def execute(self) -> None:
        raise AssertionError("authority must never execute")


class AuthorityDuration(timedelta):
    def execute(self) -> None:
        raise AssertionError("authority must never execute")


class AuthorityInteger(int):
    def execute(self) -> None:
        raise AssertionError("authority must never execute")


@pytest.mark.parametrize(
    "slot",
    [
        "members",
        "power",
        "integer_power",
        "sequence",
        "origin",
        "identity",
        "source_epoch",
        "scope_duration",
        "member_duration",
    ],
)
def test_review_nested_authority_values_are_gap_before_delegation(
    slot: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = request()
    scope = raw(value, 0)
    item = cast(Member, scope.members[0])
    if slot == "members":
        value = with_raw(
            value, 0, replace(scope, members=AuthorityTuple(scope.members))
        )
    elif slot in ("power", "integer_power"):
        power = AuthorityNumber(1.0) if slot == "power" else AuthorityInteger(1)
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                actual=replace(
                    cast(DeviceFactActualObservation, item.actual),
                    actual_power_kw=power,
                ),
            ),
        )
    elif slot == "sequence":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                transmission=replace(
                    cast(Transmission, item.transmission), sequence=AuthorityInteger(9)
                ),
            ),
        )
    elif slot == "origin":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                transmission=replace(
                    cast(Transmission, item.transmission),
                    origin=AuthorityString("caller"),
                ),
            ),
        )
    elif slot == "identity":
        value = with_member(
            value,
            0,
            0,
            replace(
                item, assessment_identity=AuthorityString(item.assessment_identity)
            ),
        )
    elif slot == "source_epoch":
        value = with_member(
            value,
            0,
            0,
            replace(
                item,
                source_epoch_relationship=replace(
                    relationship(), actual_identity_epoch=AuthorityString("epoch-a")
                ),
            ),
        )
    elif slot == "scope_duration":
        value = with_raw(
            value, 0, replace(scope, maximum_age=AuthorityDuration(minutes=5))
        )
    else:
        value = with_member(
            value, 0, 0, replace(item, maximum_age=AuthorityDuration(minutes=5))
        )
    assert_predecessors_pass(value)
    calls: list[object] = []
    upstream = Predecessor.evaluate

    def counted(self: Predecessor, item: object) -> PredecessorAssessment:
        calls.append(item)
        return upstream(self, item)

    monkeypatch.setattr(Predecessor, "evaluate", counted)
    assert_gap(value, Gap.INVALID_SCOPE)
    assert len(calls) == 1 and calls[0] is raw(value, 1)


def test_review_malformed_tuple_returns_gap_without_iterating() -> None:
    class RaisesOnIteration(tuple[object, ...]):
        def __iter__(self) -> object:  # type: ignore[override]
            raise RuntimeError("caller iterator was executed")

    value = request()
    scope = raw(value, 0)
    value = with_raw(value, 0, replace(scope, members=RaisesOnIteration(scope.members)))
    assert_gap(value, Gap.INVALID_SCOPE)


@pytest.mark.parametrize("kind", ["name", "offset", "zone_subclass"])
def test_timezone_internal_payloads_and_subclasses_rejected(kind: str) -> None:
    class AuthorityZone(ZoneInfo):
        def utcoffset(self, dt: datetime | None) -> timedelta:
            raise AssertionError("subclass timezone hook executed")

    if kind == "name":
        zone: tzinfo = timezone(timedelta(hours=1), AuthorityString("caller-zone"))
    elif kind == "offset":
        zone = timezone(AuthorityDuration(hours=1))
    else:
        zone = AuthorityZone("UTC")
    with pytest.raises(TypeError):
        replace(request(), assessment_as_of=NOW.replace(tzinfo=zone))


@pytest.mark.parametrize(
    "as_of",
    [
        datetime.min.replace(tzinfo=timezone(timedelta(hours=23))),
        datetime.max.replace(tzinfo=timezone(timedelta(hours=-23))),
    ],
)
def test_absolute_coordinate_handles_datetime_limits_without_overflow(
    as_of: datetime,
) -> None:
    # The supplied scopes are stale/future; rejecting must not overflow conversion.
    assert_gap(replace(request(), assessment_as_of=as_of), Gap.TIME_SCOPE_INVALID)


@pytest.mark.parametrize("key", [None, "UTC", AuthorityString("UTC"), object()])
def test_file_stream_zoneinfo_rejected_for_all_keys(key: object) -> None:
    import io
    import struct

    # Minimal valid TZif v1 fixed UTC: no transitions, one type and abbreviation.
    data = b"TZif\0" + b"\0" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
    data += struct.pack(">lbb", 0, 0, 0) + b"UTC\0"
    zone = ZoneInfo.from_file(io.BytesIO(data), key=key)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(request(), assessment_as_of=NOW.replace(tzinfo=zone))


def test_leaf_type_check_never_dispatches_metaclass_equality() -> None:
    class HookMeta(type):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("caller metaclass equality executed")

    class HookNumber(float, metaclass=HookMeta):
        pass

    value = request()
    item = cast(Member, raw(value, 0).members[0])
    item = replace(
        item,
        actual=replace(
            cast(DeviceFactActualObservation, item.actual),
            actual_power_kw=HookNumber(1.0),
        ),
    )
    assert_gap(with_member(value, 0, 0, item), Gap.INVALID_SCOPE)


def test_file_stream_timezone_hidden_repr_cannot_retain_raw_or_run_hook() -> None:
    import io
    import struct
    import weakref

    class ReprPayload(str):
        raw: object

        def __str__(self) -> str:
            raise AssertionError("caller repr payload hook executed")

    class CallerFile(io.BytesIO):
        label: ReprPayload

        def __repr__(self) -> str:
            return self.label

    payload = ReprPayload("source-file")
    payload.raw = raw(request(), 0)
    payload_ref = weakref.ref(payload)
    data = b"TZif\0" + b"\0" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
    data += struct.pack(">lbb", 0, 0, 0) + b"UTC\0"
    source = CallerFile(data)
    source.label = payload
    zone = ZoneInfo.from_file(source, key="UTC")
    del source, payload
    assert payload_ref() is not None  # The otherwise exact ZoneInfo retains it.
    timestamp = NOW.replace(tzinfo=zone)
    with pytest.raises(TypeError):
        replace(request(), assessment_as_of=timestamp)
    with pytest.raises(TypeError):
        Assessment("new", timestamp, Status.PASS, ())


def test_nocache_standard_zoneinfo_is_supported() -> None:
    value = replace(
        request(), assessment_as_of=NOW.replace(tzinfo=ZoneInfo.no_cache("UTC"))
    )
    assert Auditor().evaluate(value).status is Status.PASS


def test_zoneinfo_constructor_key_subclass_is_rejected() -> None:
    key = AuthorityString("UTC")
    zone = ZoneInfo.no_cache(key)
    assert zone.key is key
    with pytest.raises(TypeError):
        replace(request(), assessment_as_of=NOW.replace(tzinfo=zone))


@pytest.mark.parametrize("folds", list(product((0, 1), repeat=4)))
def test_review_cross_scope_absolute_ranges(folds: tuple[int, ...]) -> None:
    value = fold_request(folds)
    assert_predecessors_pass(value)
    times = [
        cast(Member, item).assessment_as_of.astimezone(UTC)
        for index in (0, 1)
        for item in raw(value, index).members
    ]
    value = declared(value, time_advance=times[2] - times[1])
    # UTC is an independent oracle; only compare across the scopes.
    separated = max(times[:2]) < min(times[2:])
    if separated:
        assert Auditor().evaluate(value).status is Status.PASS
    else:
        assert_gap(value, Gap.TIME_RELATION_INVALID)


def test_disjoint_ranges_preserve_frozen_scope_internal_semantics() -> None:
    zone = ZoneInfo("America/New_York")
    times = (
        datetime(2026, 11, 1, 1, 0, tzinfo=zone, fold=1),
        datetime(2026, 11, 1, 1, 10, tzinfo=zone, fold=0),
        datetime(2026, 11, 1, 2, 20, tzinfo=zone),
        datetime(2026, 11, 1, 2, 30, tzinfo=zone),
    )
    value = time_request(times, datetime(2026, 11, 1, 3, tzinfo=zone))
    value = declared(value, time_advance=timedelta(minutes=130))
    assert_predecessors_pass(value)
    assert times[0].astimezone(UTC) > times[1].astimezone(UTC)
    assert max(t.astimezone(UTC) for t in times[:2]) < min(
        t.astimezone(UTC) for t in times[2:]
    )
    assert Auditor().evaluate(value).status is Status.PASS
