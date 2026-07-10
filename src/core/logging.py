# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utilities for logging."""

import os
from logging import Logger, getLogger
from typing import Any, Callable, Literal, TypeAlias, TypedDict

PathLike: TypeAlias = str | os.PathLike[str]

LevelTypes = Literal[
    "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET", 50, 40, 30, 20, 10, 0
]
StrLevelTypes = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]


class LevelsDict(TypedDict):
    """Log Levels."""

    CRITICAL: Literal[50]
    ERROR: Literal[40]
    WARNING: Literal[30]
    INFO: Literal[20]
    DEBUG: Literal[10]
    NOTSET: Literal[0]


DEFAULT_LOG_LEVEL: StrLevelTypes = "INFO"

levels: LevelsDict = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "NOTSET": 0,
}


class WithLogging:
    """Base class to be used for providing a logger embedded in the class."""

    @property
    def logger(self) -> Logger:
        """Return a logger for the current class."""
        name_logger = str(self.__class__).replace("<class '", "").replace("'>", "")
        return getLogger(name_logger)

    def log_result(
        self, msg: Callable[..., str] | str, level: StrLevelTypes = "INFO"
    ) -> Callable[..., Any]:
        """Return a decorator that logs a message for the decorated result."""

        def wrap(x: Any) -> Any:
            if isinstance(msg, str):
                self.logger.log(levels[level], msg)
            else:
                self.logger.log(levels[level], msg(x))
            return x

        return wrap
