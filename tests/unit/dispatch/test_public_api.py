"""Tests for the public command dispatch API."""

import inspect

import kernel.dispatch as dispatch_package
import kernel.dispatch.dispatcher as dispatcher_module
from kernel.dispatch import CommandDispatcher


def test_command_dispatcher_is_publicly_importable() -> None:
    assert CommandDispatcher is dispatcher_module.CommandDispatcher
    assert dispatch_package.__all__ == ["CommandDispatcher"]


def test_no_concrete_production_dispatcher_is_introduced() -> None:
    production_dispatchers = [
        value
        for value in vars(dispatcher_module).values()
        if inspect.isclass(value)
        and value.__module__ == dispatcher_module.__name__
        and issubclass(value, CommandDispatcher)
        and not inspect.isabstract(value)
    ]

    assert production_dispatchers == []
