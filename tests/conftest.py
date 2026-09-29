from pathlib import Path

import pytest

from accesspath.cards import load_library

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="session")
def library():
    return load_library(DATA / "card_library.xlsx")
