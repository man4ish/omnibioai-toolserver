from __future__ import annotations

from ..registry import ToolHandler
from .enrichr_pathway import _run, _validate


def register_tools(registry):
    # Enrichr pathway tool
    registry.register(
        ToolHandler(
            tool_id="enrichr_pathway",
            validate=_validate,
            run=_run,
            version="v1",
            features={"libraries_default": ["WikiPathways_2024_Human", "Reactome_2022"]},
        )
    )
