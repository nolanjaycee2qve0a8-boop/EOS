"""Public import test for the decision context assembler."""

from kernel.decision import DecisionContextAssembler


def test_decision_context_assembler_is_publicly_importable() -> None:
    assert DecisionContextAssembler.__name__ == "DecisionContextAssembler"
