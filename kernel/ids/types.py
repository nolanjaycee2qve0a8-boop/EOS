"""Strongly typed string identifiers used by the EOS kernel."""

from typing import NewType

SnapshotId = NewType("SnapshotId", str)
MissionId = NewType("MissionId", str)
CommandId = NewType("CommandId", str)
EventId = NewType("EventId", str)
AssetId = NewType("AssetId", str)
CorrelationId = NewType("CorrelationId", str)
CausationId = NewType("CausationId", str)
