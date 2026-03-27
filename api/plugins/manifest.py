"""Plugin manifest model - describes a plugin's metadata and configuration."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Plugin manifest loaded from plugin.json."""

    id: str = Field(..., description="Unique plugin identifier (kebab-case)")
    name: str = Field(..., description="Human-readable plugin name")
    version: str = Field(default="1.0.0", description="Plugin version")
    description: str = Field(default="", description="Plugin description")
    type: str = Field(..., description="Plugin type: channel | hook | tool")
    entry_point: str = Field(
        ...,
        description="Python module:function path relative to plugin directory, e.g. 'plugin:register'",
    )
    config_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema for plugin configuration validation",
    )
