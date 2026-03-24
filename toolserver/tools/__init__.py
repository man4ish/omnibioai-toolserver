# toolserver/tools/__init__.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from ..adapters.http_tool_executor import make_run, make_validate
from ..registry import ToolHandler
from .enrichr_pathway import _run, _validate


def register_tools(registry) -> None:
    """Register enrichr_pathway — legacy handler, kept exactly as-is."""
    registry.register(
        ToolHandler(
            tool_id="enrichr_pathway",
            validate=_validate,
            run=_run,
            version="v1",
            features={"libraries_default": ["WikiPathways_2024_Human", "Reactome_2022"]},
        )
    )


def load_tools_from_yaml(registry, yaml_path: str) -> None:
    """
    Read tools YAML and register every tool that has an 'http' block
    using the generic HTTP executor — zero Python per tool.

    Tools without an 'http' block are silently skipped (legacy handlers
    like enrichr_pathway are already registered via register_tools()).
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"tools YAML not found: {yaml_path}")

    tools: List[Dict[str, Any]] = yaml.safe_load(path.read_text()) or []
    registered = 0

    for tool_def in tools:
        if "http" not in tool_def:
            continue

        tool_id = tool_def.get("tool_id")
        if not tool_id:
            print(f"[toolserver] WARNING: skipping tool with no tool_id: {tool_def}")
            continue

        registry.register(
            ToolHandler(
                tool_id=tool_id,
                validate=make_validate(tool_def),
                run=make_run(tool_def),
                version=tool_def.get("version", "v1"),
                features=tool_def.get("features", {}),
            )
        )
        registered += 1

    print(f"[toolserver] Loaded {registered} HTTP tools from {yaml_path}")