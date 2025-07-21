import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class McpServer:
    """Model representing an MCP server configuration."""

    def __init__(
        self,
        name: str,
        server_config: Dict[str, Any],
    ):
        self.name = name
        self.type = server_config.get("type")
        self.command = server_config.get("command")
        self.args = server_config.get("args", [])
        self.env = server_config.get("env", {})
        for key in list(self.env.keys()):
            if key in os.environ:
                self.env[key] = os.environ[key]

    @property
    def file_path(self) -> Optional[str]:
        """Get the file path from args if available."""
        return self.args[0] if self.args and len(self.args) > 0 else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the server model back to a dictionary."""
        return {"type": self.type, "command": self.command, "args": self.args}

    def __repr__(self) -> str:
        return f"McpServer(name='{self.name}', type='{self.type}', command='{self.command}', args={self.args})"


class McpConfig:
    def __init__(self, config_path: str = "mcp.json"):
        self.config_path = config_path
        self._servers: Dict[str, McpServer] = {}
        self._raw_config: Dict[str, Any] = {}

        if self.exists:
            self._load_config()

    @property
    def exists(self) -> bool:
        """Check if mcp.json exists"""
        return os.path.exists(self.config_path)

    def _load_config(self) -> None:
        """Load and process MCP configuration."""
        try:
            with open(self.config_path, "r") as f:
                self._raw_config = json.load(f)

            servers_config = self._raw_config.get("servers", {})
            self._servers = {
                name: McpServer(name, config) for name, config in servers_config.items()
            }

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.config_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to load mcp.json: {str(e)}")
            raise

    def get_servers(self) -> List[McpServer]:
        """Get list of all server models."""
        return list(self._servers.values())

    def get_server(self, name: str) -> Optional[McpServer]:
        """
        Get a server model by name.
        If there's only one server available, return that one regardless of name.
        Otherwise, look up the server by the provided name.
        """
        # If there's only one server, return it
        if len(self._servers) == 1:
            return next(iter(self._servers.values()))

        # Otherwise, fall back to looking up by name
        return self._servers.get(name)

    def get_server_names(self) -> List[str]:
        """Get list of all server names."""
        return list(self._servers.keys())

    def load_config(self) -> Dict[str, Any]:
        """Load and validate MCP servers configuration."""
        if not self.exists:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        self._load_config()
        return self._raw_config
