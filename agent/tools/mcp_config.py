import os
from mcp import StdioServerParameters
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams, StdioConnectionParams


def get_search_mcp_toolset(api_key: str = "") -> McpToolset:
    """
    Competitor search tool via Serper.dev API.
    Runs as a local subprocess (stdio).
    """
    path = os.path.join("agent", "tools", "web_scraper_mcp", "search_server.py")
    env = {
        **os.environ,
        "SERPER_API_KEY": api_key or os.getenv("SERPER_API_KEY", ""),
    }
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="uv",
                args=["run", path],
                env=env,
            ),
            timeout=60.0,
        )
    )


def get_scraper_mcp_toolset() -> McpToolset:
    """
    Web scraper tool for reading full article content.
    Runs as a local subprocess (stdio).
    """
    path = os.path.join("agent", "tools", "web_scraper_mcp", "scraper_server.py")
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="uv",
                args=["run", path],
                env=dict(os.environ),
            ),
            timeout=60.0,
        )
    )


def get_knowledge_base_mcp_toolset() -> McpToolset:
    """
    Local knowledge base tool for reading own product docs from agent/docs/.
    Runs as a local subprocess (stdio).
    """
    path = os.path.join("agent", "tools", "web_scraper_mcp", "knowledge_base_server.py")
    docs_path = os.path.abspath(os.path.join("agent", "docs"))
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="uv",
                args=["run", path],
                env={**os.environ, "DOCS_PATH": docs_path},
            ),
            timeout=30.0,
        )
    )
