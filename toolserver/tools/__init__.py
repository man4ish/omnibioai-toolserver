# toolserver/tools/__init__.py
from __future__ import annotations

import yaml
from dataclasses import fields
from pathlib import Path
from typing import Optional

from ..registry import ToolHandler, ToolRegistry
from .enrichr_pathway import _run as enrichr_run, _validate as enrichr_validate


def register_tools(registry: ToolRegistry, yaml_path: Optional[str] = None) -> None:
    """
    Register all tools:
    1. Custom handlers (existing tools with specific logic)
    2. Config-driven REST API tools from YAML (new generic tools)
    """

    # ------------------------------------------------------------------
    # 1. Custom handlers — keep exactly as before
    # ------------------------------------------------------------------
    registry.register(
        ToolHandler(
            tool_id="enrichr_pathway",
            validate=enrichr_validate,
            run=enrichr_run,
            version="v1",
            features={
                "libraries_default": [
                    "WikiPathways_2024_Human",
                    "Reactome_2022"
                ]
            },
        )
    )

    # ------------------------------------------------------------------
    # 2. Config-driven REST API tools from YAML
    # ------------------------------------------------------------------
    if yaml_path:
        _register_from_yaml(yaml_path, registry)


def _register_from_yaml(yaml_path: str, registry: ToolRegistry) -> None:
    """
    Auto-load and register all tools with adapter_type: rest_api
    from YAML config. Matches exact ToolHandler signature.
    """
    from .rest_api_handler import RestApiHandler

    config = yaml.safe_load(Path(yaml_path).read_text())
    tools = config.get("tools", [])

    registered = []
    skipped = []

    for tool_config in tools:
        tool_id = tool_config.get("tool_id")

        if not tool_id:
            continue

        adapter_type = tool_config.get("adapter_type", "custom")

        # Skip non-REST tools — must be registered as custom handlers
        if adapter_type != "rest_api":
            skipped.append(f"{tool_id} (custom handler)")
            continue

        # Skip if already registered
        if tool_id in registry._handlers:
            skipped.append(f"{tool_id} (already registered)")
            continue

        handler = RestApiHandler(tool_config)

        registry.register(
            ToolHandler(
                tool_id=tool_id,
                validate=handler._validate,
                run=handler._run,
                version="v1",
                # features advertised via /capabilities
                features={
                    "display_name": tool_config.get("display_name", tool_id),
                    "description": tool_config.get("description", ""),
                    "tags": tool_config.get("tags", []),
                    "adapter_type": "rest_api",
                    "inputs_schema": tool_config.get("inputs_schema", {}),
                    "outputs_schema": tool_config.get("outputs_schema", {}),
                }
            )
        )
        registered.append(tool_id)

    if registered:
        print(f"✓ Auto-registered {len(registered)} REST tools: {registered}")
    if skipped:
        print(f"⚠  Skipped {len(skipped)} tools: {skipped}")