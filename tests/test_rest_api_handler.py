from __future__ import annotations

import os
import pytest
import httpx
from unittest.mock import MagicMock, patch
from toolserver.tools.rest_api_handler import RestApiHandler


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def make_handler(overrides: dict = {}) -> RestApiHandler:
    """Build a minimal RestApiHandler config for testing."""
    base_config = {
        "tool_id": "test_tool",
        "config": {
            "base_url": "https://api.example.com",
            "endpoint": "/search",
            "method": "GET",
            "timeout_seconds": 10.0,
            "auth": {"type": "none"},
            "static_params": {},
            "path_params": {},
            "headers": {},
            "response_mapping": {},
            "response_format": "json",
        }
    }
    # Deep merge overrides into config
    for key, value in overrides.items():
        if key == "config":
            base_config["config"].update(value)
        else:
            base_config[key] = value
    return RestApiHandler(base_config)


def fake_log(msg: str) -> None:
    """No-op log function for tests."""
    pass


def make_response(json_data: dict = None, text: str = None, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_data is not None:
        response.json.return_value = json_data
    if text is not None:
        response.text = text
    return response


# ==================================================================
# __init__ / config parsing
# ==================================================================

class TestInit:

    def test_basic_init(self):
        handler = make_handler()
        assert handler.tool_id == "test_tool"
        assert handler.base_url == "https://api.example.com"
        assert handler.endpoint == "/search"
        assert handler.method == "GET"
        assert handler.timeout == 10.0

    def test_base_url_strips_trailing_slash(self):
        handler = make_handler({"config": {"base_url": "https://api.example.com/"}})
        assert handler.base_url == "https://api.example.com"

    def test_method_uppercased(self):
        handler = make_handler({"config": {"method": "post"}})
        assert handler.method == "POST"

    def test_defaults_when_config_empty(self):
        handler = RestApiHandler({
            "tool_id": "minimal",
            "config": {"base_url": "https://api.example.com"}
        })
        assert handler.endpoint == "/"
        assert handler.method == "GET"
        assert handler.timeout == 30.0
        assert handler.auth == {"type": "none"}
        assert handler.static_params == {}
        assert handler.path_params == {}
        assert handler.response_format == "json"


# ==================================================================
# _validate
# ==================================================================

class TestValidate:

    def test_validate_passes_with_no_required(self):
        handler = make_handler()
        result = handler._validate({"query": "test"}, {})
        assert result["ok"] is True
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_validate_fails_missing_required_input(self):
        handler = make_handler({"config": {"required_inputs": ["query", "size"]}})
        result = handler._validate({}, {})
        assert result["ok"] is False
        assert any("query" in e for e in result["errors"])
        assert any("size" in e for e in result["errors"])

    def test_validate_passes_all_required_present(self):
        handler = make_handler({"config": {"required_inputs": ["query"]}})
        result = handler._validate({"query": "BRCA2"}, {})
        assert result["ok"] is True

    def test_validate_api_key_missing_env_var(self, monkeypatch):
        monkeypatch.delenv("MY_API_KEY", raising=False)
        handler = make_handler({"config": {
            "auth": {"type": "api_key", "key": "${MY_API_KEY}"}
        }})
        result = handler._validate({}, {})
        assert result["ok"] is False
        assert any("MY_API_KEY" in e for e in result["errors"])

    def test_validate_api_key_env_var_present(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "secret123")
        handler = make_handler({"config": {
            "auth": {"type": "api_key", "key": "${MY_API_KEY}"}
        }})
        result = handler._validate({}, {})
        assert result["ok"] is True

    def test_validate_bearer_auth_no_check(self):
        # Bearer tokens don't require env var check
        handler = make_handler({"config": {
            "auth": {"type": "bearer", "token": "mytoken"}
        }})
        result = handler._validate({}, {})
        assert result["ok"] is True


# ==================================================================
# _build_url
# ==================================================================

class TestBuildUrl:

    def test_simple_url(self):
        handler = make_handler()
        url = handler._build_url({"query": "test"})
        assert url == "https://api.example.com/search"

    def test_path_params_replaced(self):
        handler = make_handler({"config": {
            "endpoint": "/lookup/{species}/{symbol}",
            "path_params": {
                "species": "inputs.species",
                "symbol": "inputs.symbol"
            }
        }})
        url = handler._build_url({"species": "human", "symbol": "BRCA2"})
        assert url == "https://api.example.com/lookup/human/BRCA2"

    def test_direct_input_substitution_in_endpoint(self):
        handler = make_handler({"config": {
            "endpoint": "/gene/{gene_id}",
            "path_params": {}
        }})
        url = handler._build_url({"gene_id": "TP53"})
        assert url == "https://api.example.com/gene/TP53"

    def test_missing_path_param_leaves_placeholder(self):
        handler = make_handler({"config": {
            "endpoint": "/lookup/{species}",
            "path_params": {"species": "inputs.species"}
        }})
        url = handler._build_url({})
        # Empty string substituted when input missing
        assert "{species}" not in url


# ==================================================================
# _build_headers
# ==================================================================

class TestBuildHeaders:

    def test_no_auth_returns_base_headers(self):
        handler = make_handler({"config": {
            "headers": {"Accept": "application/json"},
            "auth": {"type": "none"}
        }})
        headers = handler._build_headers()
        assert headers["Accept"] == "application/json"
        assert "Authorization" not in headers

    def test_bearer_auth(self):
        handler = make_handler({"config": {
            "auth": {"type": "bearer", "token": "mytoken123"}
        }})
        headers = handler._build_headers()
        assert headers["Authorization"] == "Bearer mytoken123"

    def test_bearer_auth_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secrettoken")
        handler = make_handler({"config": {
            "auth": {"type": "bearer", "token": "${MY_TOKEN}"}
        }})
        headers = handler._build_headers()
        assert headers["Authorization"] == "Bearer secrettoken"

    def test_api_key_default_header(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "apikey123")
        handler = make_handler({"config": {
            "auth": {"type": "api_key", "key": "${MY_KEY}"}
        }})
        headers = handler._build_headers()
        assert headers["X-API-Key"] == "apikey123"

    def test_api_key_custom_header(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "apikey123")
        handler = make_handler({"config": {
            "auth": {
                "type": "api_key",
                "key": "${MY_KEY}",
                "header": "Authorization"
            }
        }})
        headers = handler._build_headers()
        assert headers["Authorization"] == "apikey123"


# ==================================================================
# _build_params
# ==================================================================

class TestBuildParams:

    def test_get_includes_inputs_as_params(self):
        handler = make_handler({"config": {"method": "GET"}})
        params = handler._build_params({"query": "BRCA2", "size": 10})
        assert params["query"] == "BRCA2"
        assert params["size"] == 10

    def test_get_merges_static_params(self):
        handler = make_handler({"config": {
            "method": "GET",
            "static_params": {"db": "pubmed", "retmode": "json"}
        }})
        params = handler._build_params({"query": "cancer"})
        assert params["db"] == "pubmed"
        assert params["retmode"] == "json"
        assert params["query"] == "cancer"

    def test_get_skips_path_param_inputs(self):
        handler = make_handler({"config": {
            "method": "GET",
            "endpoint": "/lookup/{species}",
            "path_params": {"species": "inputs.species"}
        }})
        params = handler._build_params({"species": "human", "query": "BRCA2"})
        # species is a path param — should not appear in query params
        assert "species" not in params
        assert params["query"] == "BRCA2"

    def test_post_does_not_include_inputs_as_params(self):
        handler = make_handler({"config": {"method": "POST"}})
        params = handler._build_params({"query": "BRCA2"})
        assert "query" not in params


# ==================================================================
# _build_body
# ==================================================================

class TestBuildBody:

    def test_post_returns_inputs_as_body(self):
        handler = make_handler({"config": {"method": "POST"}})
        body = handler._build_body({"genes": ["TP53", "BRCA1"]})
        assert body == {"genes": ["TP53", "BRCA1"]}

    def test_get_returns_none_body(self):
        handler = make_handler({"config": {"method": "GET"}})
        body = handler._build_body({"query": "test"})
        assert body is None


# ==================================================================
# _parse_response
# ==================================================================

class TestParseResponse:

    def test_json_response_no_mapping(self):
        handler = make_handler()
        response = make_response(json_data={"results": [1, 2, 3], "total": 3})
        result = handler._parse_response(response, {})
        assert result["results"] == [1, 2, 3]
        assert result["total"] == 3

    def test_json_response_with_mapping(self):
        handler = make_handler({"config": {
            "response_mapping": {
                "items": "$.results",
                "count": "$.total"
            }
        }})
        response = make_response(json_data={"results": [1, 2], "total": 2})
        result = handler._parse_response(response, {})
        assert result["items"] == [1, 2]
        assert result["count"] == 2

    def test_json_response_nested_mapping(self):
        handler = make_handler({"config": {
            "response_mapping": {
                "name": "$.data.name"
            }
        }})
        response = make_response(json_data={"data": {"name": "BRCA2"}})
        result = handler._parse_response(response, {})
        assert result["name"] == "BRCA2"

    def test_text_response_raw(self):
        handler = make_handler({"config": {"response_format": "text"}})
        response = make_response(text="some raw text")
        result = handler._parse_response(response, {})
        assert result["raw"] == "some raw text"

    def test_text_response_kegg_list(self):
        handler = make_handler({"config": {
            "response_format": "text",
            "text_parser": "kegg_list"
        }})
        kegg_text = "path:hsa00010\tGlycolysis / Gluconeogenesis\npath:hsa00020\tCitrate cycle"
        response = make_response(text=kegg_text)
        result = handler._parse_response(response, {})
        assert result["n_pathways"] == 2
        assert result["pathways"][0]["id"] == "path:hsa00010"
        assert result["pathways"][0]["name"] == "Glycolysis / Gluconeogenesis"

    def test_json_list_response_wrapped(self):
        handler = make_handler()
        response = make_response(json_data=[1, 2, 3])
        result = handler._parse_response(response, {})
        assert result["data"] == [1, 2, 3]


# ==================================================================
# _extract_jsonpath
# ==================================================================

class TestExtractJsonpath:

    def test_simple_key(self):
        handler = make_handler()
        data = {"results": [1, 2, 3]}
        assert handler._extract_jsonpath(data, "$.results") == [1, 2, 3]

    def test_nested_key(self):
        handler = make_handler()
        data = {"meta": {"total": 42}}
        assert handler._extract_jsonpath(data, "$.meta.total") == 42

    def test_missing_key_returns_none(self):
        handler = make_handler()
        data = {"results": []}
        assert handler._extract_jsonpath(data, "$.missing") is None

    def test_missing_nested_key_returns_none(self):
        handler = make_handler()
        data = {"meta": {}}
        assert handler._extract_jsonpath(data, "$.meta.total") is None

    def test_non_jsonpath_returns_data(self):
        handler = make_handler()
        data = {"key": "value"}
        assert handler._extract_jsonpath(data, "key") == {"key": "value"}


# ==================================================================
# _resolve_value
# ==================================================================

class TestResolveValue:

    def test_resolves_inputs_prefix(self):
        handler = make_handler()
        result = handler._resolve_value("inputs.species", {"species": "human"})
        assert result == "human"

    def test_resolves_missing_input_returns_empty(self):
        handler = make_handler()
        result = handler._resolve_value("inputs.species", {})
        assert result == ""

    def test_non_inputs_prefix_returns_literal(self):
        handler = make_handler()
        result = handler._resolve_value("literal_value", {})
        assert result == "literal_value"


# ==================================================================
# _resolve_env
# ==================================================================

class TestResolveEnv:

    def test_resolves_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "supersecret")
        handler = make_handler()
        assert handler._resolve_env("${MY_SECRET}") == "supersecret"

    def test_missing_env_var_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        handler = make_handler()
        assert handler._resolve_env("${MISSING_VAR}") == ""

    def test_literal_value_returned_as_is(self):
        handler = make_handler()
        assert handler._resolve_env("plainvalue") == "plainvalue"

    def test_partial_env_syntax_not_resolved(self):
        handler = make_handler()
        assert handler._resolve_env("${INCOMPLETE") == "${INCOMPLETE"


# ==================================================================
# _parse_text_response
# ==================================================================

class TestParseTextResponse:

    def test_kegg_list_parser(self):
        handler = make_handler({"config": {"text_parser": "kegg_list"}})
        text = "path:hsa00010\tGlycolysis\npath:hsa00020\tCitrate cycle"
        result = handler._parse_text_response(text)
        assert result["n_pathways"] == 2
        assert result["pathways"][1]["id"] == "path:hsa00020"

    def test_kegg_list_skips_lines_without_tab(self):
        handler = make_handler({"config": {"text_parser": "kegg_list"}})
        text = "path:hsa00010\tGlycolysis\nmalformed line"
        result = handler._parse_text_response(text)
        assert result["n_pathways"] == 1

    def test_unknown_parser_returns_raw(self):
        handler = make_handler({"config": {"text_parser": None}})
        result = handler._parse_text_response("some text")
        assert result["raw"] == "some text"

    def test_empty_text_kegg(self):
        handler = make_handler({"config": {"text_parser": "kegg_list"}})
        result = handler._parse_text_response("")
        assert result["n_pathways"] == 0
        assert result["pathways"] == []


# ==================================================================
# _run (integration — mock httpx)
# ==================================================================

class TestRun:

    def test_get_request_success(self):
        handler = make_handler()
        mock_response = make_response(json_data={"results": ["gene1"]})
        mock_response.raise_for_status = MagicMock()

        logs = []
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            result = handler._run({"query": "BRCA2"}, {}, logs.append)

        assert result["ok"] is True
        assert result["results"] == ["gene1"]
        assert any("GET" in log for log in logs)

    def test_post_request_success(self):
        handler = make_handler({"config": {"method": "POST"}})
        mock_response = make_response(json_data={"ok": True})
        mock_response.raise_for_status = MagicMock()

        logs = []
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = handler._run({"genes": ["TP53"]}, {}, logs.append)

        assert result["ok"] is True
        mock_client.post.assert_called_once()

    def test_unsupported_method_raises(self):
        handler = make_handler({"config": {"method": "DELETE"}})
        with pytest.raises(ValueError, match="Unsupported method"):
            handler._run({}, {}, fake_log)

    def test_http_error_raises(self):
        handler = make_handler()
        mock_response = make_response(status_code=500)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                handler._run({"query": "test"}, {}, fake_log)

    def test_run_logs_url_and_status(self):
        handler = make_handler()
        mock_response = make_response(json_data={})
        mock_response.raise_for_status = MagicMock()

        logs = []
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            handler._run({"query": "test"}, {}, logs.append)

        assert any("https://api.example.com/search" in log for log in logs)
        assert any("status=" in log for log in logs)

    def test_run_with_response_mapping(self):
        handler = make_handler({"config": {
            "response_mapping": {"items": "$.results"}
        }})
        mock_response = make_response(json_data={"results": [1, 2, 3]})
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            result = handler._run({}, {}, fake_log)

        assert result["ok"] is True
        assert result["items"] == [1, 2, 3]
