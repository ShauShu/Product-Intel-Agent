import logging
import os
import sys
from pathlib import Path
from fastmcp import FastMCP
from dotenv import load_dotenv

def _init_logging():
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stderr)], force=True)

load_dotenv()
mcp = FastMCP(name="KnowledgeBase")
DOCS_PATH = Path(os.getenv("DOCS_PATH", os.path.join("agent", "docs")))


@mcp.tool()
def list_product_docs() -> list[str]:
    """List all available product documentation files."""
    if not DOCS_PATH.exists():
        return []
    return [f.name for f in DOCS_PATH.glob("*.md")]


@mcp.tool()
def read_product_doc(filename: str) -> dict:
    """
    Read the full content of a product documentation file.
    Use list_product_docs() first to see available files.
    """
    file_path = DOCS_PATH / filename
    if not file_path.exists() or not file_path.is_file():
        return {"error": f"File '{filename}' not found in docs directory."}
    return {"filename": filename, "content": file_path.read_text(encoding="utf-8")}


if __name__ == "__main__":
    _init_logging()
    mcp.run(transport="stdio")
