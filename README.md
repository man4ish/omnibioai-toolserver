# toolserver_template

A reusable ToolServer implementing the contract expected by omnibioai-tool-exec HttpToolServerAdapter:

- GET  /capabilities
- POST /validate
- POST /runs
- GET  /runs/{id}
- GET  /runs/{id}/logs
- GET  /runs/{id}/results

## Run

pip install -r requirements.txt
uvicorn toolserver_app:create_app --factory --host 0.0.0.0 --port 9090

## Add a new REST-backed tool

1) Create `toolserver/tools/<new_tool>.py` with:
- `_validate(inputs, resources) -> {"ok": bool, "errors": [], "warnings": []}`
- `_run(inputs, resources, log) -> results_dict`

2) Register it in `toolserver/tools/__init__.py` via `registry.register(ToolHandler(...))`

3) Ensure `/capabilities` advertises it (automatic)
