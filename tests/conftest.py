from __future__ import annotations

from pathlib import Path

import pytest

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def examples() -> Path:
    return EX
