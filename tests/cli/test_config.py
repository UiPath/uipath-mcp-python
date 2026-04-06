from uipath_mcp._cli._utils._config import McpConfig


def test_get_server_exact_match_single_server(tmp_path):
    """Single-server config should NOT return the server for a mismatched name."""
    config_file = tmp_path / "mcp.json"
    config_file.write_text('{"servers": {"my-server": {"command": "python"}}}')

    config = McpConfig(config_path=str(config_file))

    assert config.get_server("my-server") is not None
    assert config.get_server("wrong-name") is None


def test_get_server_exact_match_multiple_servers(tmp_path):
    """Multi-server config returns correct server by name."""
    config_file = tmp_path / "mcp.json"
    config_file.write_text(
        '{"servers": {"server-a": {"command": "a"}, "server-b": {"command": "b"}}}'
    )

    config = McpConfig(config_path=str(config_file))

    server_a = config.get_server("server-a")
    server_b = config.get_server("server-b")
    assert server_a is not None
    assert server_b is not None
    assert server_a.name == "server-a"
    assert server_b.name == "server-b"
    assert config.get_server("server-c") is None
