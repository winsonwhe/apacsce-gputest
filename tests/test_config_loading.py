"""Tests for modular configuration loading."""

from pathlib import Path

from gputest.core import load_config

ROOT = Path(__file__).resolve().parent.parent


def test_modular_loader_selects_one_sku_and_default_environment():
    config = load_config(ROOT / "config", sku="gb300")
    assert set(config["skus"]) == {"gb300"}
    assert config["skus"]["gb300"]["gpu_count"] == 4
    assert config["_environment"] == "default"
    assert config["tools"]["nvidia_smi"] == "nvidia-smi"
    assert set(config["levels"]) >= {"basic", "standard", "extended"}


def test_modular_loader_supports_environment_overlay(tmp_path):
    root = tmp_path / "config"
    (root / "skus").mkdir(parents=True)
    (root / "environments").mkdir()
    (root / "tools").mkdir()
    (root / "base.yaml").write_text("network: {mode: auto}\nskus: {}\n")
    (root / "manifest.yaml").write_text("default_environment: lab\ndefault_tools: default\n")
    (root / "environments" / "lab.yaml").write_text("network: {fallback_mode: multiplanar}\n")
    (root / "tools" / "default.yaml").write_text("tools: {curl: curl}\n")
    (root / "skus" / "x.yaml").write_text("skus: {x: {gpu_count: 1}}\n")

    config = load_config(root, sku="x")
    assert config["network"] == {"mode": "auto", "fallback_mode": "multiplanar"}
    assert config["skus"] == {"x": {"gpu_count": 1}}
