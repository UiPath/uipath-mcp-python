from enum import Enum


class UiPathServerType(Enum):
    """Defines the different types of UiPath servers used in the MCP ecosystem.

    This enum is used to identify and configure the behavior of different server types
    during runtime registration and execution.

    Attributes:
        UiPath (0): Standard UiPath server for Processes, Agents, and Activities
        Command (1): Command server types like npx, uvx
        Coded (2): Coded MCP server (PackageType.MCPServer)
        SelfHosted (3): Tunnel to externally hosted server
    """

    UiPath = 0  # Processes, Agents, Activities
    Command = 1  # npx, uvx
    Coded = 2  # PackageType.MCPServer
    SelfHosted = 3  # tunnel to externally hosted server

    @classmethod
    def from_string(cls, name: str) -> "UiPathServerType":
        """Get enum value from string name."""
        try:
            return cls[name]
        except KeyError as e:
            raise ValueError(f"Unknown server type: {name}") from e

    @classmethod
    def get_description(cls, server_type: "UiPathServerType") -> str:
        """Get description for a server type."""
        descriptions = {
            cls.UiPath: "Standard UiPath server for Processes, Agents, and Activities",
            cls.Command: "Command server types like npx, uvx",
            cls.Coded: "Coded MCP server (PackageType.MCPServer)",
            cls.SelfHosted: "Tunnel to externally hosted server",
        }
        return descriptions.get(server_type, "Unknown server type")
