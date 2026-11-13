import os
import sys

import pytest

# Las pruebas no dependen de la licencia instalada (tests/test_licensing.py prueba las ediciones)
os.environ["OLVGL_LICENSE_ENFORCE"] = "0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from olvgl.application.viewmodel import ProjectViewModel  # noqa: E402
from olvgl.infrastructure import json_store  # noqa: E402
from olvgl.infrastructure.esphome_generator import generate_yaml  # noqa: E402
from olvgl.infrastructure.esphome_importer import import_esphome_file  # noqa: E402
from olvgl.infrastructure.sync_adapters import make_session  # noqa: E402


@pytest.fixture
def vm():
    return ProjectViewModel(generator=generate_yaml, saver=json_store.save_project,
                            loader=json_store.load_project, importer=import_esphome_file,
                            sync_factory=make_session)


@pytest.fixture
def demo_path():
    return os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")


@pytest.fixture
def fixtures_dir():
    return os.path.join(ROOT, "tests", "fixtures")
