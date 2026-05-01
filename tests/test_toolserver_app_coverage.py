# tests/test_toolserver_app_coverage.py
import pytest
import yaml
from fastapi.testclient import TestClient
from unittest.mock import patch
import os


# ── helper ──────────────────────────────────────────────────────────────────
def get_client(tools_yaml_exists=False):
    """Create a TestClient with controlled YAML path."""
    yaml_path = "configs/tools.example.yaml" if tools_yaml_exists else "/nonexistent/path.yaml"
    with patch.dict(os.environ, {"TOOLS_YAML_PATH": yaml_path}):
        from toolserver_app import create_app
        return TestClient(create_app())


# ── Line 42: YAML not found warning ─────────────────────────────────────────
def test_create_app_yaml_not_found(capsys):
    """Covers the else branch (line 42) when tools YAML is missing."""
    client = get_client(tools_yaml_exists=False)
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "only legacy tools loaded" in captured.out


# ── Line 120→122: get_results when state != COMPLETED ───────────────────────
# Replace test_get_results_not_ready and add test for line 160

# ── Lines 145-174: /register_tools endpoint ──────────────────────────────────
def test_register_tools_with_http_block():
    """Covers the http-handler branch in register_tools_endpoint."""
    from toolserver_app import create_app
    client = TestClient(create_app())

    resp = client.post("/register_tools", json={"tools": [{
        "tool_id": "my_http_tool",
        "version": "v1",
        "features": {"async": True},
        "http": {
            "url": "http://example.com/run",
            "method": "POST"
        }
    }]})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "registered": 1}


def test_register_tools_without_http_block():
    """Covers the stub-handler else branch in register_tools_endpoint."""
    from toolserver_app import create_app
    client = TestClient(create_app())

    resp = client.post("/register_tools", json={"tools": [{
        "tool_id": "my_stub_tool",
        "version": "v1",
    }]})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "registered": 1}


def test_register_tools_skips_missing_tool_id():
    """Covers the 'if not tool_id: continue' branch."""
    from toolserver_app import create_app
    client = TestClient(create_app())

    resp = client.post("/register_tools", json={"tools": [
        {},                          # no tool_id → skipped
        {"tool_id": "valid_tool"},   # registered
    ]})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "registered": 1}


def test_register_tools_empty():
    """Edge case: empty tools list."""
    from toolserver_app import create_app
    client = TestClient(create_app())

    resp = client.post("/register_tools", json={"tools": []})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "registered": 0}


# ── Line 42: YAML file found → load_tools_from_yaml called ──────────────────
def test_create_app_yaml_found(tmp_path):
    """Covers line 42: when TOOLS_YAML_PATH exists, load_tools_from_yaml is called."""
    tool_defs = [{
        "tool_id": "yaml_loaded_tool",
        "version": "v2",
        "http": {"method": "GET", "url": "https://api.example.com/test"},
        "inputs": [],
        "response_map": {},
    }]
    yaml_file = tmp_path / "tools.yaml"
    yaml_file.write_text(yaml.dump(tool_defs))

    with patch.dict(os.environ, {"TOOLS_YAML_PATH": str(yaml_file)}):
        from toolserver_app import create_app
        client = TestClient(create_app())

    tools = client.get("/capabilities").json()["tools"]
    tool_ids = [t["tool_id"] for t in tools]
    assert "yaml_loaded_tool" in tool_ids