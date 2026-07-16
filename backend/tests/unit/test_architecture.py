import importlib.util
from pathlib import Path
from typing import Any


def _load_checker() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_architecture.py"
    spec = importlib.util.spec_from_file_location("check_architecture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_domain_dependency_violation_is_detected_and_recovery_passes() -> None:
    checker = _load_checker()
    assert checker.forbidden_imports("from fastapi import APIRouter\nimport sqlalchemy.orm") == {
        "fastapi",
        "sqlalchemy.orm",
    }
    assert checker.forbidden_imports("from dataclasses import dataclass") == set()
