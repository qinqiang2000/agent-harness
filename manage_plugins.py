#!/usr/bin/env python3
"""Plugin management CLI tool."""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api.constants import BUNDLED_PLUGINS_DIR, INSTALLED_PLUGINS_DIR, PLUGIN_CONFIG_FILE
from api.plugins.config import PluginConfigService
from api.plugins.discovery import PluginDiscovery


def get_discovery() -> PluginDiscovery:
    """Create a PluginDiscovery instance."""
    search_paths = [
        (BUNDLED_PLUGINS_DIR, "bundled"),
        (INSTALLED_PLUGINS_DIR, "installed"),
    ]
    return PluginDiscovery(search_paths)


def get_config() -> PluginConfigService:
    """Create a PluginConfigService instance."""
    return PluginConfigService(PLUGIN_CONFIG_FILE)


def cmd_list(args):
    """List all discovered plugins."""
    discovery = get_discovery()
    config = get_config()
    plugins = discovery.discover_all()

    if not plugins:
        print("No plugins found.")
        return

    enabled_ids = config.get_enabled_list()

    print(f"{'ID':<20} {'Name':<30} {'Type':<10} {'Source':<10} {'Enabled':<8} {'Version'}")
    print("-" * 100)

    for p in plugins:
        enabled = "Yes" if p.id in enabled_ids else "No"
        print(
            f"{p.manifest.id:<20} {p.manifest.name:<30} {p.manifest.type:<10} "
            f"{p.source:<10} {enabled:<8} {p.manifest.version}"
        )


def cmd_info(args):
    """Show detailed plugin information."""
    discovery = get_discovery()
    config = get_config()
    plugins = discovery.discover_all()

    plugin = next((p for p in plugins if p.manifest.id == args.plugin_id), None)
    if not plugin:
        print(f"Plugin '{args.plugin_id}' not found.")
        sys.exit(1)

    enabled = plugin.manifest.id in config.get_enabled_list()
    plugin_config = config.get_plugin_config(plugin.manifest.id)

    print(f"Plugin: {plugin.manifest.id}")
    print(f"  Name:        {plugin.manifest.name}")
    print(f"  Version:     {plugin.manifest.version}")
    print(f"  Type:        {plugin.manifest.type}")
    print(f"  Description: {plugin.manifest.description}")
    print(f"  Source:      {plugin.source}")
    print(f"  Path:        {plugin.path}")
    print(f"  Entry Point: {plugin.manifest.entry_point}")
    print(f"  Enabled:     {enabled}")
    if plugin_config:
        print(f"  Config:      {json.dumps(plugin_config, indent=4, ensure_ascii=False)}")
    if plugin.manifest.config_schema:
        print(f"  Schema:      {json.dumps(plugin.manifest.config_schema, indent=4)}")


def cmd_enable(args):
    """Enable a plugin."""
    config = get_config()
    discovery = get_discovery()
    plugins = discovery.discover_all()

    plugin = next((p for p in plugins if p.manifest.id == args.plugin_id), None)
    if not plugin:
        print(f"Plugin '{args.plugin_id}' not found.")
        sys.exit(1)

    config.enable(args.plugin_id)
    print(f"Plugin '{args.plugin_id}' enabled. Restart the service to take effect.")


def cmd_disable(args):
    """Disable a plugin."""
    config = get_config()
    config.disable(args.plugin_id)
    print(f"Plugin '{args.plugin_id}' disabled. Restart the service to take effect.")


def cmd_install(args):
    """Install a plugin from a local path."""
    import shutil

    source = Path(args.path).resolve()
    if not source.exists():
        print(f"Path does not exist: {source}")
        sys.exit(1)

    manifest_file = source / "plugin.json"
    if not manifest_file.exists():
        print(f"No plugin.json found at {source}")
        sys.exit(1)

    with open(manifest_file) as f:
        manifest = json.load(f)

    plugin_id = manifest.get("id")
    if not plugin_id:
        print("plugin.json missing 'id' field")
        sys.exit(1)

    dest = INSTALLED_PLUGINS_DIR / plugin_id
    if dest.exists():
        print(f"Plugin '{plugin_id}' already installed at {dest}")
        sys.exit(1)

    INSTALLED_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)
    print(f"Plugin '{plugin_id}' installed to {dest}")
    print(f"Run 'python manage_plugins.py enable {plugin_id}' to enable it.")


def cmd_doctor(args):
    """Run health checks on the plugin system."""
    issues = []

    # Check directories
    if not BUNDLED_PLUGINS_DIR.exists():
        issues.append(f"Bundled plugins directory missing: {BUNDLED_PLUGINS_DIR}")
    if not INSTALLED_PLUGINS_DIR.exists():
        issues.append(f"Installed plugins directory missing: {INSTALLED_PLUGINS_DIR}")

    # Check config file
    if not PLUGIN_CONFIG_FILE.exists():
        issues.append(f"Plugin config file missing: {PLUGIN_CONFIG_FILE}")
    else:
        try:
            with open(PLUGIN_CONFIG_FILE) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            issues.append(f"Plugin config file has invalid JSON: {e}")

    # Discover and validate plugins
    discovery = get_discovery()
    config = get_config()
    plugins = discovery.discover_all()
    enabled_ids = config.get_enabled_list()

    # Check for enabled plugins that don't exist
    discovered_ids = {p.manifest.id for p in plugins}
    for eid in enabled_ids:
        if eid not in discovered_ids:
            issues.append(f"Enabled plugin '{eid}' not found in any search path")

    # Check plugin entry points
    for p in plugins:
        entry_module = p.manifest.entry_point.split(":")[0]
        entry_file = p.path / f"{entry_module}.py"
        if not entry_file.exists():
            issues.append(f"Plugin '{p.manifest.id}': entry point file missing: {entry_file}")

    if issues:
        print(f"Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        sys.exit(1)
    else:
        print(f"All checks passed. {len(plugins)} plugin(s) found, {len(enabled_ids)} enabled.")


def main():
    parser = argparse.ArgumentParser(description="Agent-Harness Plugin Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    subparsers.add_parser("list", help="List all plugins")

    # info
    info_parser = subparsers.add_parser("info", help="Show plugin details")
    info_parser.add_argument("plugin_id", help="Plugin ID")

    # enable
    enable_parser = subparsers.add_parser("enable", help="Enable a plugin")
    enable_parser.add_argument("plugin_id", help="Plugin ID")

    # disable
    disable_parser = subparsers.add_parser("disable", help="Disable a plugin")
    disable_parser.add_argument("plugin_id", help="Plugin ID")

    # install
    install_parser = subparsers.add_parser("install", help="Install a plugin from local path")
    install_parser.add_argument("path", help="Path to plugin directory")

    # doctor
    subparsers.add_parser("doctor", help="Run health checks")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "info": cmd_info,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "install": cmd_install,
        "doctor": cmd_doctor,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
