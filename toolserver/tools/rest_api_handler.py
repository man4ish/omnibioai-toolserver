# toolserver/tools/rest_api_handler.py
from __future__ import annotations
import os
import re
import httpx
from typing import Any, Dict, List, Optional


class RestApiHandler:
    """
    Generic REST API handler driven entirely by YAML config.
    Supports GET/POST, path params, query params, static params,
    bearer/api_key/none auth, JSON and text responses.
    No custom code needed per tool.
    """

    def __init__(self, tool_config: Dict[str, Any]) -> None:
        self.tool_id = tool_config["tool_id"]
        self.config = tool_config.get("config", {})
        self.base_url = self.config["base_url"].rstrip("/")
        self.endpoint = self.config.get("endpoint", "/")
        self.method = self.config.get("method", "GET").upper()
        self.timeout = self.config.get("timeout_seconds", 30.0)
        self.auth = self.config.get("auth", {"type": "none"})
        self.static_params = self.config.get("static_params", {})
        self.path_params = self.config.get("path_params", {})
        self.headers_config = self.config.get("headers", {})
        self.response_mapping = self.config.get("response_mapping", {})
        self.response_format = self.config.get("response_format", "json")
        self.text_parser = self.config.get("text_parser", None)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(
        self,
        inputs: Dict[str, Any],
        resources: Dict[str, Any]
    ) -> Dict[str, Any]:
        errors = []
        warnings = []

        # Check required inputs from schema
        required = self.config.get("required_inputs", [])
        for field in required:
            if field not in inputs:
                errors.append(f"Missing required input: {field}")

        # Check API key if needed
        if self.auth.get("type") == "api_key":
            key = self.auth.get("key", "")
            if key.startswith("${"):
                env_var = key[2:-1]
                if not os.environ.get(env_var):
                    errors.append(
                        f"Missing environment variable: {env_var}"
                    )

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _run(
        self,
        inputs: Dict[str, Any],
        resources: Dict[str, Any],
        log
    ) -> Dict[str, Any]:

        # Build URL with path params
        url = self._build_url(inputs)
        headers = self._build_headers()
        params = self._build_params(inputs)
        body = self._build_body(inputs)

        log(f"[{self.tool_id}] {self.method} {url}")
        log(f"[{self.tool_id}] params={params}")

        with httpx.Client(timeout=self.timeout) as client:
            if self.method == "GET":
                response = client.get(url, headers=headers, params=params)
            elif self.method == "POST":
                response = client.post(
                    url, headers=headers,
                    params=params, json=body
                )
            else:
                raise ValueError(f"Unsupported method: {self.method}")

            response.raise_for_status()
            log(f"[{self.tool_id}] status={response.status_code}")

        # Parse response
        result = self._parse_response(response, inputs)
        result["ok"] = True
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_url(self, inputs: Dict[str, Any]) -> str:
        """Replace path params like {species} with input values."""
        endpoint = self.endpoint
        for param, source in self.path_params.items():
            # source format: "inputs.field_name"
            value = self._resolve_value(source, inputs)
            endpoint = endpoint.replace(f"{{{param}}}", str(value))

        # Also handle direct {field} in endpoint
        for key, value in inputs.items():
            endpoint = endpoint.replace(f"{{{key}}}", str(value))

        return f"{self.base_url}{endpoint}"

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including auth."""
        headers = dict(self.headers_config)

        auth_type = self.auth.get("type", "none")
        if auth_type == "bearer":
            token = self._resolve_env(self.auth.get("token", ""))
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            key = self._resolve_env(self.auth.get("key", ""))
            header_name = self.auth.get("header", "X-API-Key")
            headers[header_name] = key

        return headers

    def _build_params(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Build query parameters from static + inputs."""
        params = dict(self.static_params)

        # Add inputs as query params for GET requests
        if self.method == "GET":
            skip_as_params = set(self.path_params.values())
            for key, value in inputs.items():
                source = f"inputs.{key}"
                if source not in skip_as_params:
                    params[key] = value

        return params

    def _build_body(self, inputs: Dict[str, Any]) -> Optional[Dict]:
        """Build request body for POST requests."""
        if self.method == "POST":
            return inputs
        return None

    def _parse_response(
        self,
        response: httpx.Response,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse response based on format and mapping."""

        if self.response_format == "text":
            return self._parse_text_response(response.text)

        # JSON response
        data = response.json()

        # Apply response mapping if defined
        if self.response_mapping:
            result = {}
            for output_key, json_path in self.response_mapping.items():
                result[output_key] = self._extract_jsonpath(
                    data, json_path
                )
            return result

        # Return raw response if no mapping
        return data if isinstance(data, dict) else {"data": data}

    def _parse_text_response(self, text: str) -> Dict[str, Any]:
        """Parse text responses e.g. KEGG list format."""
        if self.text_parser == "kegg_list":
            pathways = []
            for line in text.strip().split("\n"):
                if "\t" in line:
                    parts = line.split("\t")
                    pathways.append({
                        "id": parts[0],
                        "name": parts[1] if len(parts) > 1 else ""
                    })
            return {
                "pathways": pathways,
                "n_pathways": len(pathways)
            }
        return {"raw": text}

    def _extract_jsonpath(
        self,
        data: Any,
        path: str
    ) -> Any:
        """Simple JSONPath extraction e.g. $.results."""
        if path.startswith("$."):
            key = path[2:]
            if "." in key:
                parts = key.split(".")
                result = data
                for part in parts:
                    if isinstance(result, dict):
                        result = result.get(part)
                    else:
                        return None
                return result
            return data.get(key) if isinstance(data, dict) else None
        return data

    def _resolve_value(self, source: str, inputs: Dict[str, Any]) -> Any:
        """Resolve value from source like inputs.field_name."""
        if source.startswith("inputs."):
            field = source[7:]
            return inputs.get(field, "")
        return source

    def _resolve_env(self, value: str) -> str:
        """Resolve environment variable references like ${VAR}."""
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.environ.get(env_var, "")
        return value