"""Append-only decision log.

Every evaluated bar is recorded, including HOLD days: in semi-automatic
operation the reason a trade did not happen is the interesting part. SQLite
will replace this once the daily runner needs to query history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from ...domain.models import Decision


class JsonlDecisionStore:
    def __init__(self, path: str | Path, append: bool = True):
        self.path = Path(path)
        self._file: TextIO | None = None
        self._mode = "a" if append else "w"

    def _handle(self) -> TextIO:
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open(self._mode, encoding="utf-8")
        return self._file

    def record(self, decision: Decision) -> None:
        handle = self._handle()
        handle.write(json.dumps(decision.to_dict(), ensure_ascii=False, default=str) + "\n")
        handle.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> "JsonlDecisionStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class NullDecisionStore:
    def record(self, decision: Decision) -> None:
        return None

    def close(self) -> None:
        return None
