from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Ensure RunStore writes into temp
    monkeypatch.setenv("TOOLSERVER_RUN_STORE_DIR", str(tmp_path / "runs"))

    # Must patch BEFORE app creation so registry captures fake_run
    import toolserver.tools.enrichr_pathway as enrichr_mod

    def fake_run(inputs, resources, log):
        log("FAKE RUN called")
        time.sleep(0.01)
        return {
            "ok": True,
            "results": {
                "WikiPathways_2024_Human": {
                    "library": "WikiPathways_2024_Human",
                    "columns": ["rank", "term", "p_value"],
                    "items": [{"rank": 1, "term": "DummyPathway", "p_value": 1e-6}],
                    "n_terms": 1,
                }
            },
        }

    # Patch BEFORE create_app so register_tools() captures fake_run
    monkeypatch.setattr(enrichr_mod, "_run", fake_run, raising=True)

    # Import and create app AFTER patch is applied
    from toolserver_app import create_app  # noqa: E402

    app = create_app()
    return TestClient(app)
