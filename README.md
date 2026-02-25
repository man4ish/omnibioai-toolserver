# omnibioai-toolserver

A standalone **HTTP ToolServer** for the **OmniBioAI** ecosystem.

This service implements the REST contract expected by
`omnibioai-tes (Tool Execution Service, legacy package name: `omnibioai-tes`) `HttpToolServerAdapter`, enabling **secure, validated, and reproducible execution of REST-backed bioinformatics tools** (e.g. Enrichr, annotation services, external APIs).

It is designed to run **independently** and be registered as a remote execution server in OmniBioAI TES.

---

## Implemented API Contract

The ToolServer exposes the following endpoints:

* `GET  /capabilities`
  Advertise supported tools, engines, resources, and runtime policies.

* `POST /validate`
  Validate tool inputs and resource requests.

* `POST /runs`
  Submit a tool execution request.

* `GET  /runs/{id}`
  Retrieve run state (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`).

* `GET  /runs/{id}/logs`
  Retrieve execution logs.

* `GET  /runs/{id}/results`
  Retrieve structured tool results once the run is completed.

This contract matches the expectations of
**`omnibioai-tes` → `HttpToolServerAdapter`**.

---

## Current Capabilities

* Engine: `http_toolserver`
* Tools:

  * `enrichr_pathway` — Pathway enrichment via Enrichr (REST, multipart-safe)
* Execution model:

  * Stateless REST calls
  * Structured validation
  * Run lifecycle tracking
* Designed for:

  * OmniBioAI agents
  * TES-controlled execution
  * Future multi-tool expansion (OMIM, GO, UniProt, etc.)

---

## Running the ToolServer

### Requirements

* Python ≥ 3.11

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
uvicorn toolserver_app:create_app --factory --host 0.0.0.0 --port 9090
```

### Verify

```bash
curl http://127.0.0.1:9090/capabilities | python -m json.tool
```

---

## Integration with OmniBioAI TES

Register this service as a server in `omnibioai-tes`:

```yaml
- server_id: enrichment_remote
  display_name: Enrichment ToolServer
  adapter_type: http_toolserver
  config:
    base_url: "http://127.0.0.1:9090"
```

Then submit runs through TES:

```bash
POST /api/runs/submit
```

The ToolServer is **never called directly by the browser or LLM**—all execution is mediated by TES.

---

## Adding a New REST-Backed Tool

1. Create a new handler:

```
toolserver/tools/<new_tool>.py
```

Implement:

```python
def _validate(inputs, resources) -> {
  "ok": bool,
  "errors": [],
  "warnings": []
}

def _run(inputs, resources, log) -> Dict[str, Any]
```

2. Register the tool in:

```
toolserver/tools/__init__.py
```

```python
registry.register(ToolHandler(...))
```

3. Restart the server.

The tool will be **automatically advertised** via `/capabilities`.

No changes are required in TES beyond refreshing server capabilities.

---

## Design Principles

* **LLMs never execute tools directly**
* **All execution is validated and audited**
* **Strict separation** between:

  * intent (agents / UI)
  * orchestration (TES)
  * execution (ToolServer)
* REST-first, container-friendly, and infrastructure-agnostic

---

## Status

* **Frozen initial release**
* Enrichr pathway enrichment working end-to-end with TES
* Stable API contract

