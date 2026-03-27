"""Plugin lifecycle management - handles state transitions."""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from api.plugins.registry import PluginInstance, PluginState

if TYPE_CHECKING:
    from api.plugins.api import PluginAPI

logger = logging.getLogger(__name__)


class PluginLifecycle:
    """Manages plugin state transitions: load → register → start → stop."""

    def load(self, instance: PluginInstance) -> bool:
        """Load plugin module and resolve entry_point function.

        Args:
            instance: Plugin instance to load

        Returns:
            True if loaded successfully
        """
        try:
            entry_point = instance.manifest.entry_point  # e.g. "plugin:register"
            module_name, func_name = entry_point.split(":")

            # Add plugin directory to sys.path temporarily for import
            plugin_dir = str(instance.path)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)

            try:
                # Use importlib to load the module
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{instance.id}_{module_name}",
                    instance.path / f"{module_name}.py",
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot find module {module_name}.py in {instance.path}")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            finally:
                # Clean up sys.path
                if plugin_dir in sys.path:
                    sys.path.remove(plugin_dir)

            # Resolve the register function
            register_func = getattr(module, func_name, None)
            if register_func is None:
                raise AttributeError(
                    f"Module {module_name} has no function '{func_name}'"
                )
            if not callable(register_func):
                raise TypeError(f"{module_name}.{func_name} is not callable")

            instance.plugin_object = register_func
            instance.state = PluginState.LOADED
            logger.info(f"Loaded plugin: {instance.id}")
            return True

        except Exception as e:
            instance.state = PluginState.ERROR
            instance.error = str(e)
            logger.error(f"Failed to load plugin {instance.id}: {e}")
            return False

    def register(self, instance: PluginInstance, api: PluginAPI) -> bool:
        """Call the plugin's register() function with the PluginAPI.

        Args:
            instance: Plugin instance to register
            api: PluginAPI object to pass to the plugin

        Returns:
            True if registered successfully
        """
        if instance.state != PluginState.LOADED:
            logger.error(
                f"Cannot register plugin {instance.id}: state is {instance.state}, expected LOADED"
            )
            return False

        try:
            register_func: Callable = instance.plugin_object
            result = register_func(api)

            # If register() returns a plugin object (e.g. ChannelPlugin), store it
            if result is not None:
                instance.plugin_object = result

            instance.api = api
            instance.state = PluginState.REGISTERED
            logger.info(f"Registered plugin: {instance.id}")
            return True

        except Exception as e:
            instance.state = PluginState.ERROR
            instance.error = str(e)
            logger.error(f"Failed to register plugin {instance.id}: {e}")
            return False

    async def start(self, instance: PluginInstance) -> bool:
        """Start a registered plugin (call on_start if available).

        Args:
            instance: Plugin instance to start

        Returns:
            True if started successfully
        """
        if instance.state != PluginState.REGISTERED:
            logger.error(
                f"Cannot start plugin {instance.id}: state is {instance.state}, expected REGISTERED"
            )
            return False

        try:
            # Call on_start if the plugin object has it
            if hasattr(instance.plugin_object, "on_start"):
                await instance.plugin_object.on_start()

            instance.state = PluginState.STARTED
            logger.info(f"Started plugin: {instance.id}")
            return True

        except Exception as e:
            instance.state = PluginState.ERROR
            instance.error = str(e)
            logger.error(f"Failed to start plugin {instance.id}: {e}")
            return False

    async def stop(self, instance: PluginInstance) -> bool:
        """Stop a running plugin (call on_stop if available).

        Args:
            instance: Plugin instance to stop

        Returns:
            True if stopped successfully
        """
        if instance.state != PluginState.STARTED:
            logger.debug(f"Plugin {instance.id} not started, skip stop")
            return True

        try:
            if hasattr(instance.plugin_object, "on_stop"):
                await instance.plugin_object.on_stop()

            instance.state = PluginState.STOPPED
            logger.info(f"Stopped plugin: {instance.id}")
            return True

        except Exception as e:
            instance.error = str(e)
            logger.error(f"Failed to stop plugin {instance.id}: {e}")
            return False
