"""Lazy configuration loader that initializes after argparse."""

import yaml
from pathlib import Path
from typing import Any, Optional


class ConfigManager:
    """Global configuration manager - lazy loads after CLI parsing."""
    
    _instance = None
    _config = None
    _config_path = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, config_path: Optional[str] = None) -> None:
        """Call this AFTER argparse with the custom config path."""
        if self._initialized:
            return
            
        self._config_path = config_path or "config.d/config.yaml"
        
        # Handle relative paths
        path = Path(self._config_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        self._initialized = True
    
    def _check_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "Config not initialized. Call ConfigManager.initialize(config_path) "
                "after parsing command line arguments."
            )
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a specific configuration value."""
        self._check_initialized()
        return self._config.get(section, {}).get(key, default)
    
    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        value = self.get(section, key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', 'yes', '1', 'on')
    
    def get_section(self, section: str) -> dict:
        """Get an entire configuration section."""
        self._check_initialized()
        return self._config.get(section, {})
    
    def get_all(self) -> dict:
        """Get the entire configuration."""
        self._check_initialized()
        return self._config
    
    def validate(self) -> None:
        """Validate required configuration sections exist."""
        self._check_initialized()
        required = ['database', 'accounts', 'Folders', 'DaemonSettings']
        for section in required:
            if section not in self._config:
                raise ValueError(f"Missing required config section: {section}")


# Global singleton instance
config_manager = ConfigManager()