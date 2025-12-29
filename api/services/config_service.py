"""Configuration management service for dynamic model switching (Thread-safe version)."""

import os
import logging
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Default configuration (can be overridden by environment variable DEFAULT_MODEL_CONFIG)
_DEFAULT_FALLBACK = "glm"
DEFAULT_CONFIG = os.getenv("DEFAULT_MODEL_CONFIG", _DEFAULT_FALLBACK)

@dataclass
class ModelConfig:
    """Configuration for a single model provider."""
    name: str
    description: str
    base_url: str
    auth_token_env: str  # Environment variable name for auth token
    timeout_ms: int = 600000
    model: Optional[str] = None
    small_fast_model: Optional[str] = None
    sonnet_model: Optional[str] = None
    opus_model: Optional[str] = None
    haiku_model: Optional[str] = None
    proxy_env: Optional[str] = None  # Environment variable name for proxy URL
    extra_env: Dict[str, str] = field(default_factory=dict)

    def get_auth_token(self) -> str:
        """Get auth token from environment variable."""
        return os.getenv(self.auth_token_env, "")

    def get_proxy_settings(self) -> Optional[Dict[str, str]]:
        """Get proxy settings from environment variable."""
        if not self.proxy_env:
            return None

        proxy_url = os.getenv(self.proxy_env)
        if not proxy_url:
            return None

        return {
            "https_proxy": proxy_url,
            "http_proxy": proxy_url
        }

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate configuration.

        Returns:
            (is_valid, error_message)
        """
        # Check auth token
        if not self.get_auth_token():
            return False, f"Auth token not found (env: {self.auth_token_env})"

        # Check base_url format
        if not self.base_url.startswith(("http://", "https://")):
            return False, f"Invalid base_url format: {self.base_url}"

        return True, None


# Predefined model configurations - NO SECRETS, only metadata
PREDEFINED_CONFIGS: Dict[str, ModelConfig] = {
    "glm": ModelConfig(
        name="glm",
        description="GLM-4 (智谱清言) 模型",
        base_url="https://open.bigmodel.cn/api/anthropic",
        auth_token_env="GLM_AUTH_TOKEN",
        timeout_ms=3000000,
        proxy_env=None,  # No proxy needed
        extra_env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    ),
    "claude-router": ModelConfig(
        name="claude-router",
        description="Claude Code Router (本地代理)",
        base_url="http://127.0.0.1:3456",
        auth_token_env="CLAUDE_ROUTER_AUTH_TOKEN",
        timeout_ms=600000,
        proxy_env="CLAUDE_ROUTER_PROXY",  # Read from environment variable
        extra_env={
            "DISABLE_TELEMETRY": "true",
            "DISABLE_COST_WARNINGS": "true"
        }
    ),
}

# Validate that the default config exists
if DEFAULT_CONFIG not in PREDEFINED_CONFIGS:
    logger.warning(
        f"Invalid DEFAULT_MODEL_CONFIG '{DEFAULT_CONFIG}' specified in environment. "
        f"Available configs: {list(PREDEFINED_CONFIGS.keys())}. "
        f"Falling back to '{_DEFAULT_FALLBACK}'"
    )
    DEFAULT_CONFIG = _DEFAULT_FALLBACK


class ConfigService:
    """
    Configuration management service (Thread-safe version).

    Improvements from original:
    - Thread-safe using threading.Lock
    - Atomic switch_config operation
    - Configuration validation
    - Supports dependency injection (not global singleton)
    """

    def __init__(self, default_config: str = DEFAULT_CONFIG):
        """
        Args:
            default_config: Default configuration name
        """
        self._current_config = default_config
        self._lock = threading.Lock()  # Thread safety
        self._initialized = False
        self._apply_default_config()

    def _apply_default_config(self):
        """Apply default configuration."""
        if self._initialized:
            return

        success = self.switch_config(self._current_config)
        if not success:
            logger.warning(
                f"Failed to apply default config {self._current_config}, "
                "environment may be incomplete"
            )
        self._initialized = True

    def get_current_config_name(self) -> str:
        """Get the name of the current active configuration."""
        with self._lock:
            return self._current_config

    def get_current_config(self) -> ModelConfig:
        """Get the current active configuration."""
        with self._lock:
            return PREDEFINED_CONFIGS.get(
                self._current_config,
                PREDEFINED_CONFIGS["claude-router"]
            )

    def get_available_configs(self) -> List[Dict]:
        """Get list of all available configurations."""
        with self._lock:
            current = self._current_config
            return [
                {
                    "name": config.name,
                    "description": config.description,
                    "base_url": config.base_url,
                    "is_active": config.name == current
                }
                for config in PREDEFINED_CONFIGS.values()
            ]

    def switch_config(self, config_name: str) -> bool:
        """
        Switch to a different configuration (Thread-safe, atomic operation).

        This updates the environment variables in the current process.
        Note: For Claude SDK, changes take effect on the next query.
        """
        with self._lock:  # Atomic operation
            # Validate config exists
            if config_name not in PREDEFINED_CONFIGS:
                logger.error(f"Unknown config: {config_name}")
                return False

            config = PREDEFINED_CONFIGS[config_name]

            # Validate configuration
            is_valid, error_msg = config.validate()
            if not is_valid:
                logger.error(f"Invalid config {config_name}: {error_msg}")
                return False

            # Apply configuration (atomic)
            try:
                self._apply_config(config)
                self._current_config = config_name
                logger.info(f"Switched to config: {config_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to apply config {config_name}: {e}")
                return False

    def _apply_config(self, config: ModelConfig):
        """Apply configuration to environment variables (internal method)."""
        # Basic configuration
        os.environ["ANTHROPIC_BASE_URL"] = config.base_url
        os.environ["ANTHROPIC_AUTH_TOKEN"] = config.get_auth_token()
        os.environ["ANTHROPIC_API_KEY"] = config.get_auth_token()
        os.environ["API_TIMEOUT_MS"] = str(config.timeout_ms)

        # Model configuration
        self._set_or_clear_env("ANTHROPIC_MODEL", config.model)
        self._set_or_clear_env("ANTHROPIC_SMALL_FAST_MODEL", config.small_fast_model)
        self._set_or_clear_env("ANTHROPIC_DEFAULT_SONNET_MODEL", config.sonnet_model)
        self._set_or_clear_env("ANTHROPIC_DEFAULT_OPUS_MODEL", config.opus_model)
        self._set_or_clear_env("ANTHROPIC_DEFAULT_HAIKU_MODEL", config.haiku_model)

        # Clear all proxy settings first
        proxy_keys = ["https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY", "no_proxy", "NO_PROXY"]
        for key in proxy_keys:
            os.environ.pop(key, None)

        # Apply proxy settings if configured
        proxy_settings = config.get_proxy_settings()
        if proxy_settings:
            for key, value in proxy_settings.items():
                os.environ[key] = value
            logger.info(f"Applied proxy settings from {config.proxy_env}: {list(proxy_settings.keys())}")
        else:
            if config.proxy_env:
                logger.info(f"No proxy configured ({config.proxy_env} not set, using direct connection)")
            else:
                logger.info("No proxy configured (direct connection)")

        # Apply extra environment variables
        for key, value in config.extra_env.items():
            os.environ[key] = value

    def _set_or_clear_env(self, key: str, value: Optional[str]):
        """Set or clear environment variable."""
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    def get_current_env_snapshot(self) -> Dict[str, str]:
        """Get a snapshot of the current relevant environment variables."""
        relevant_keys = [
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_SMALL_FAST_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "API_TIMEOUT_MS",
            "https_proxy",
            "http_proxy",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "NO_PROXY",
            "no_proxy",
            "DISABLE_TELEMETRY",
            "DISABLE_COST_WARNINGS",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        ]
        with self._lock:
            return {
                key: os.getenv(key, "")
                for key in relevant_keys
                if os.getenv(key)
            }
