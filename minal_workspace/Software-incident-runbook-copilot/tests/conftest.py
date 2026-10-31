from pathlib import Path

import pytest


@pytest.fixture

def corpus_root() -> Path:
    return Path(__file__).parents[1] / "corpus"
