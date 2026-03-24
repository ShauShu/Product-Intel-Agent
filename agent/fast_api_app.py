import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import VertexAiMemoryBankService
from google.genai import types

from agent.agent import create_root_agent
from agent.app_utils.env import PROJECT_ID, LOCATION, MEMORY_BANK_ID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Memory & Session setup
# ---------------------------------------------------------------------------

session_service = InMemorySessionService()
memory_service = None

if MEMORY_BANK_ID:
    memory_service = VertexAiMemoryBankService(
        project=PROJECT_ID,
        location=LOCATION,
        memory_bank_id=MEMORY_BANK_ID,
    )

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("Product Intel Agent starting up.")
    yield
    logger.info("Product Intel Agent shutting down.")


app = FastAPI(title="Product Intel Agent", lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    competitor: str
    session_id: str = "default"
    user_id: str = "default-user"


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """Trigger competitive intelligence analysis for a given competitor."""
    logger.info(f"🚀 Starting analysis for: {req.competitor} (Session: {req.session_id})")
    try:
        # 為每個請求建立全新的 Agent 和 Runner，避免工具連線死鎖
        agent = create_root_agent()
        runner = Runner(
            agent=agent,
            app_name="product-intel-agent",
            session_service=session_service,
            memory_service=memory_service,
        )

        session = await session_service.create_session(
            app_name="product-intel-agent",
            user_id=req.user_id,
            session_id=req.session_id,
        )
        message = types.Content(
            role="user",
            parts=[types.Part(text=f"Analyze competitor: {req.competitor}")],
        )
        final_response = None
        async for event in runner.run_async(
            user_id=req.user_id,
            session_id=session.id,
            new_message=message,
        ):
            # 顯示 Agent 的思考過程與工具呼叫細節
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        logger.info(f"🤖 Thought: {part.text[:150]}...")
                    if part.function_call:
                        logger.info(f"🛠️ Tool Call: {part.function_call.name} args={part.function_call.args}")

            if event.is_final_response():
                final_response = event.content.parts[0].text if event.content else ""
                logger.info("✅ Analysis complete.")

        return {"competitor": req.competitor, "report": final_response}
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清除因為每個請求新建 Agent 所產生的子程序 (MCP server)，避免連線和 File Handle 洩漏導致 Uvicorn 卡住
        from google.adk.tools import McpToolset
        async def close_agent_tools(a):
            if hasattr(a, "tools") and a.tools:
                for t in a.tools:
                    if isinstance(t, McpToolset) and hasattr(t, "_mcp_session_manager"):
                        try:
                            await t._mcp_session_manager.close()
                        except Exception as close_err:
                            logger.error(f"Failed to close McpToolset: {close_err}")
            if hasattr(a, "sub_agents") and a.sub_agents:
                for sub in a.sub_agents:
                    await close_agent_tools(sub)
        
        if 'agent' in locals():
            await close_agent_tools(agent)

@app.get("/health")
def health():
    return {"status": "ok"}
