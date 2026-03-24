import logging
import os
import sys
import httpx
from fastmcp import FastMCP
from dotenv import load_dotenv

def _init_logging():
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stderr)], force=True)

load_dotenv()
mcp = FastMCP(name="CompetitorSearch")


@mcp.tool()
async def competitor_search_tool(query: str, num_results: int = 10) -> list[dict]:
    """
    Search the web for competitor news, feature releases, and pricing changes.
    Returns a list of results with title, link, and snippet.
    """
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        return [{"error": "SERPER_API_KEY not set"}]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    return [
        {"title": r.get("title"), "link": r.get("link"), "snippet": r.get("snippet")}
        for r in data.get("organic", [])
    ]


if __name__ == "__main__":
    _init_logging()
    mcp.run(transport="stdio")
