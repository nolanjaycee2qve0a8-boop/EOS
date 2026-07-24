"""Abstract boundary for submitting immutable domain commands."""

from abc import ABC, abstractmethod

from kernel.domain import Command


class CommandDispatcher(ABC):
    """Accept one exact Command for implementation-defined submission."""

    __slots__ = ()

    @abstractmethod
    def dispatch(self, command: Command) -> None:
        """Submit the exact Command or raise an implementation exception."""
        raise NotImplementedError
