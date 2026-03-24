import logging
import sys
import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from dotenv import load_dotenv

def _init_logging():
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stderr)], force=True)

load_dotenv()
mcp = FastMCP(name="WebScraper")


@mcp.tool()
async def web_scraper_tool(url: str) -> dict:
    """
    Fetch and extract the main text content from a webpage URL.
    Returns the page title and cleaned body text.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ProductIntelAgent/1.0)"}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title else ""
        text = " ".join(soup.get_text(separator=" ").split())
        return {"title": title, "content": text[:8000]}  # cap at 8k chars
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    _init_logging()
    mcp.run(transport="stdio")
