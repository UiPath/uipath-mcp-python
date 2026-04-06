import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


class McpServer:
    """Model representing an MCP server configuration."""

    def __init__(
        self,
        name: str,
        server_config: dict[str, Any],
    ):
        self.name = name
        self.type = server_config.get("type")
        self.transport: str = server_config.get("transport", "stdio")
        self.url: str | None = server_config.get("url")
        self.command: str = str(server_config.get("command"))
        self.args = server_config.get("args", [])
        self.env = server_config.get("env", {})
        for key in list(self.env.keys()):
            if key in os.environ:
                self.env[key] = os.environ[key]

    @property
    def is_streamable_http(self) -> bool:
        """Whether this server uses streamable-http transport."""
        return self.transport == "streamable-http"

    @property
    def file_path(self) -> str | None:
        """Get the file path from args if available."""
        return self.args[0] if self.args and len(self.args) > 0 else None

    def to_dict(self) -> dict[str, Any]:
        """Convert the server model back to a dictionary."""
        result: dict[str, Any] = {
            "type": self.type,
            "command": self.command,
            "args": self.args,
        }
        if self.transport:
            result["transport"] = self.transport
        if self.url:
            result["url"] = self.url
        return result

    def __repr__(self) -> str:
        return f"McpServer(name='{self.name}', type='{self.type}', transport='{self.transport}', command='{self.command}', args={self.args}, url='{self.url}')"


class McpConfig:
    def __init__(self, config_path: str = "mcp.json"):
        self.config_path = config_path
        self._servers: dict[str, McpServer] = {}
        self._raw_config: dict[str, Any] = {}

        if self.exists:
            self._load_config()

    @property
    def exists(self) -> bool:
        """Check if mcp.json exists"""
        return os.path.exists(self.config_path)

    @staticmethod
    def validate_server_name(name: str) -> None:
        """
        Validate the server name.

        The server name must only contain letters (a-z, A-Z), numbers (0-9), and hyphens (-).
        Raises a ValueError if the name is invalid.
        """
        if not re.match(r"^[a-zA-Z0-9-]+$", name):
            raise ValueError(
                f'Invalid server name "{name}": only letters, numbers, and hyphens are allowed.'
            )

    def _load_config(self) -> None:
        """Load and process MCP configuration."""
        try:
            with open(self.config_path, "r") as f:
                self._raw_config = json.load(f)

            servers_config = self._raw_config.get("servers", {})
            self._servers = {}
            for name in servers_config.keys():
                self.validate_server_name(name)
                self._servers[name] = McpServer(name, servers_config[name])

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.config_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to load mcp.json: {str(e)}")
            raise

    def get_servers(self) -> list[McpServer]:
        """Get list of all server models."""
        return list(self._servers.values())

    def get_server(self, name: str) -> McpServer | None:
        """
        Get a server model by name.
        """
        return self._servers.get(name)

    def get_server_names(self) -> list[str]:
        """Get list of all server names."""
        return list(self._servers.keys())

    def load_config(self) -> dict[str, Any]:
        """Load and validate MCP servers configuration."""
        if not self.exists:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        self._load_config()
        return self._raw_config
