from __future__ import annotations

import secrets
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from toolserver.executor import Executor
from toolserver.models import RunCreateRequest, ValidateRequest
from toolserver.registry import ToolRegistry
from toolserver.store import RunStore
from toolserver.tools import register_tools


def _new_run_id() -> str:
    return f"ts_{secrets.token_urlsafe(10)}"


def create_app() -> FastAPI:
    app = FastAPI(title="toolserver_template")

    # Config knobs (hardcoded for now; env vars later)
    run_store_dir = "out/runs"
    store = RunStore(run_store_dir)

    registry = ToolRegistry()
    register_tools(registry)

    executor = Executor(store=store, registry=registry, max_workers=8)

    # ----------------
    # Capabilities
    # ----------------
    @app.get("/capabilities")
    def capabilities():
        return registry.capabilities().model_dump()

    # ----------------
    # Validate
    # ----------------
    @app.post("/validate")
    def validate(req: ValidateRequest):
        try:
            h = registry.get(req.tool_id)
        except KeyError as e:
            return {"ok": False, "errors": [{"code": "UNKNOWN_TOOL", "message": str(e)}], "warnings": []}
        return h.validate(req.inputs, req.resources)

    # ----------------
    # Submit run
    # ----------------
    @app.post("/runs")
    def create_run(req: RunCreateRequest):
        # 1) validate
        v = validate(ValidateRequest(tool_id=req.tool_id, inputs=req.inputs, resources=req.resources))
        if not v.get("ok", False):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": {"code": "VALIDATION_FAILED", "details": v}},
            )

        run_id = _new_run_id()
        now = int(time.time())

        # Store only lightweight inputs metadata in record
        rec = {
            "run_id": run_id,
            "tool_id": req.tool_id,
            "state": "QUEUED",
            "created_epoch": now,
            "updated_epoch": now,
            "inputs": {"summary": "stored externally"},  # keep record small
            "resources": req.resources,
            "logs": ["Queued"],
            "results": None,
            "error": None,
        }
        from toolserver.models import RunRecord
        store.create(RunRecord(**rec))

        # 2) async execution (full inputs passed to executor)
        executor.submit(store.get(run_id), full_inputs=req.inputs, resources=req.resources)

        # HttpToolServerAdapter expects JSON with "run_id"
        return {"run_id": run_id}

    # ----------------
    # Status
    # ----------------
    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        rec = store.try_get(run_id)
        if not rec:
            return {"state": "FAILED", "message": "unknown run"}
        return {"run_id": rec.run_id, "state": rec.state, "updated_epoch": rec.updated_epoch}

    # ----------------
    # Logs
    # ----------------
    @app.get("/runs/{run_id}/logs")
    def get_logs(run_id: str, tail: int = 200):
        rec = store.try_get(run_id)
        if not rec:
            return {"run_id": run_id, "logs": f"[{run_id}] unknown run"}
        lines = rec.logs or []
        if tail and tail > 0:
            lines = lines[-tail:]
        return {"run_id": run_id, "logs": "\n".join(lines)}

    # ----------------
    # Results
    # ----------------
    @app.get("/runs/{run_id}/results")
    def get_results(run_id: str):
        rec = store.try_get(run_id)
        if not rec:
            return {"ok": False, "error": {"code": "NOT_FOUND", "message": "unknown run"}}
        if rec.state != "COMPLETED":
            return {
                "ok": False, 
                "error": {"code": "NOT_READY", "message": f"state={rec.state}"},
                "state": rec.state,
            }
        return rec.results or {"ok": True, "results": {}}

    @app.get("/health")
    def health():
        return {"ok": True, "service": "toolserver_template"}

    return app
