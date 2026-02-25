# registry.py — fix mutable default
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

ValidateFn = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
RunFn = Callable[[Dict[str, Any], Dict[str, Any], Callable[[str], None]], Dict[str, Any]]


@dataclass(frozen=True)
class ToolHandler:
    tool_id: str
    validate: ValidateFn
    run: RunFn
    version: str = "v1"
    features: Optional[Dict[str, Any]] = None  # ← already Optional, just confirming

    def has_feature(self, key: str) -> bool:
        return bool(self.features and key in self.features)

    def get_feature(self, key: str, default: Any = None) -> Any:
        if self.features:
            return self.features.get(key, default)
        return default


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, h: ToolHandler) -> None:
        self._handlers[h.tool_id] = h

    def get(self, tool_id: str) -> ToolHandler:
        if tool_id not in self._handlers:
            raise KeyError(f"tool not registered: {tool_id}")
        return self._handlers[tool_id]

    def has(self, tool_id: str) -> bool:
        """Check if tool is already registered."""
        return tool_id in self._handlers

    def list_tool_ids(self) -> list:
        return list(self._handlers.keys())

    def capabilities(self) -> ServerCapabilities:
        tools = []
        for h in self._handlers.values():
            tools.append(
                {
                    "tool_id": h.tool_id,
                    "version": h.version,
                    "features": h.features or {},
                }
            )
        return ServerCapabilities(
            engines=["http_toolserver"],
            tools=tools,
            resources={"max_cpu": 8, "max_ram_gb": 32},
            storage={"allowed_uri_schemes": ["inline"]},
            policies={"max_runtime_minutes": 60},
        )