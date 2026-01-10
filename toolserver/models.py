from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

RunState = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]


class ValidateRequest(BaseModel):
    tool_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    resources: Dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    tool_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    resources: Dict[str, Any] = Field(default_factory=dict)


class RunStatusResponse(BaseModel):
    run_id: str
    state: RunState
    updated_epoch: int
    message: Optional[str] = None


class RunRecord(BaseModel):
    run_id: str
    tool_id: str
    state: RunState
    created_epoch: int
    updated_epoch: int

    inputs: Dict[str, Any] = Field(default_factory=dict)     # lightweight metadata ok
    resources: Dict[str, Any] = Field(default_factory=dict)

    logs: List[str] = Field(default_factory=list)
    results: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class ToolCapability(BaseModel):
    tool_id: str
    version: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)


class ServerCapabilities(BaseModel):
    engines: List[str] = Field(default_factory=list)
    tools: List[ToolCapability] = Field(default_factory=list)
    resources: Dict[str, Any] = Field(default_factory=dict)
    storage: Dict[str, Any] = Field(default_factory=dict)
    policies: Dict[str, Any] = Field(default_factory=dict)
