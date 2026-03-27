"""Plugin system for agent-harness.

Imports are lazy to avoid pulling in heavy dependencies (e.g. claude_agent_sdk)
when only lightweight components like PluginConfigService or PluginDiscovery are needed.
"""

__all__ = [
    "PluginManifest",
    "PluginAPI",
    "PluginRegistry",
    "PluginInstance",
    "PluginState",
    "PluginDiscovery",
    "PluginLifecycle",
    "PluginManager",
    "PluginConfigService",
    "ChannelPlugin",
    "ChannelMeta",
    "ChannelCapabilities",
]


def __getattr__(name):
    if name == "PluginManifest":
        from api.plugins.manifest import PluginManifest
        return PluginManifest
    if name == "PluginAPI":
        from api.plugins.api import PluginAPI
        return PluginAPI
    if name in ("PluginRegistry", "PluginInstance", "PluginState"):
        from api.plugins import registry
        return getattr(registry, name)
    if name == "PluginDiscovery":
        from api.plugins.discovery import PluginDiscovery
        return PluginDiscovery
    if name == "PluginLifecycle":
        from api.plugins.lifecycle import PluginLifecycle
        return PluginLifecycle
    if name == "PluginManager":
        from api.plugins.manager import PluginManager
        return PluginManager
    if name == "PluginConfigService":
        from api.plugins.config import PluginConfigService
        return PluginConfigService
    if name in ("ChannelPlugin", "ChannelMeta", "ChannelCapabilities"):
        from api.plugins import channel
        return getattr(channel, name)
    raise AttributeError(f"module 'api.plugins' has no attribute {name!r}")
