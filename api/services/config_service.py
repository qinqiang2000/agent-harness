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
    auth_env_target: str = "auth_token"  # "auth_token", "api_key", or "both"
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

        # Set both uppercase and lowercase for maximum compatibility
        return {
            "HTTPS_PROXY": proxy_url,
            "HTTP_PROXY": proxy_url,
            "https_proxy": proxy_url,
            "http_proxy": proxy_url,
        }

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate configuration.

        Returns:
            (is_valid, error_message)
        """
        # Check auth token (skip if using SDK built-in auth, i.e. auth_token_env is empty)
        if self.auth_token_env and not self.get_auth_token():
            return False, f"Auth token not found (env: {self.auth_token_env})"

        # Check base_url format (empty string means use SDK default)
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
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
    "claude": ModelConfig(
        name="claude",
        description="Claude Official API (官方 API，使用 SDK 内置认证)",
        base_url="",  # Use SDK default (https://api.anthropic.com)
        auth_token_env="",  # 不设置，使用 SDK 内置认证（需先 claude login）
        timeout_ms=600000,
        proxy_env="CLAUDE_PROXY",  # Optional proxy for official API
        extra_env={}
    ),
    "litellm": ModelConfig(
        name="litellm",
        description="LiteLLM Proxy (通过 LiteLLM 代理访问 Claude)",
        base_url=os.getenv("LITELLM_BASE_URL", "http://129.226.88.226:4000"),
        auth_token_env="LITELLM_API_KEY",
        timeout_ms=600000,
        proxy_env=None,
        auth_env_target="api_key",  # LiteLLM uses standard API key, not OAuth token
        extra_env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
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

    # 环境变量映射字典（数据驱动配置）
    ENV_KEY_MAPPING = {
        # Claude SDK基础配置
        "ANTHROPIC_BASE_URL": lambda c: c.base_url,
        "ANTHROPIC_AUTH_TOKEN": lambda c: c.get_auth_token() if c.auth_env_target in ("auth_token", "both") else "",
        "ANTHROPIC_API_KEY": lambda c: c.get_auth_token() if c.auth_env_target in ("api_key", "both") else "",
        "API_TIMEOUT_MS": lambda c: str(c.timeout_ms),

        # 可选模型配置
        "ANTHROPIC_MODEL": lambda c: c.model,
        "ANTHROPIC_SMALL_FAST_MODEL": lambda c: c.small_fast_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": lambda c: c.sonnet_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": lambda c: c.opus_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": lambda c: c.haiku_model,
    }

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
        # 1. 应用基础配置（使用字典驱动，消除重复代码）
        for env_key, value_getter in self.ENV_KEY_MAPPING.items():
            value = value_getter(config)
            self._set_or_clear_env(env_key, value)

        # 2. 清理并应用代理配置
        self._apply_proxy_settings(config)

        # 3. 应用额外环境变量
        for key, value in config.extra_env.items():
            os.environ[key] = value

    def _apply_proxy_settings(self, config: ModelConfig):
        """独立的代理设置应用

        Args:
            config: 模型配置
        """
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
