from typing import Literal, Optional
from pydantic import BaseModel
import google.genai
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import McpToolset
from agent.tools.mcp_config import (
    get_search_mcp_toolset,
    get_scraper_mcp_toolset,
    get_knowledge_base_mcp_toolset,
)
from agent.app_utils.env import SERPER_API_KEY, PROJECT_ID, LOCATION


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class CompetitorIntelReport(BaseModel):
    competitor_name: str
    new_feature_summary: str
    pricing_change: Optional[str] = None
    threat_level: Literal["low", "medium", "high", "critical"]
    our_counter_strategy: str
    source_urls: list[str] = []
    already_reported: bool = False

# ---------------------------------------------------------------------------
# Vertex AI Client Configuration
# ---------------------------------------------------------------------------
# 強制覆寫 google.genai.Client 的初始化行為，讓所有 Agent 自動使用 Vertex AI
# 這樣就不需要傳入 client 參數 (LlmAgent 不支援)，也能解決 "No API Key" 問題

_original_init = google.genai.Client.__init__

def _patched_init(self, *args, **kwargs):
    # 強制注入 Vertex AI 設定
    kwargs["vertexai"] = True
    kwargs["project"] = PROJECT_ID
    kwargs["location"] = LOCATION
    _original_init(self, *args, **kwargs)

google.genai.Client.__init__ = _patched_init

# ---------------------------------------------------------------------------
# Researcher Agent  —  discovers & scrapes competitor signals
# ---------------------------------------------------------------------------

RESEARCHER_PROMPT = """
You are a Market Researcher specializing in competitive intelligence.

Your workflow:
1. Before searching, recall if this competitor/topic was already reported in the last 7 days.
   If yes, set already_reported=true and focus on NEW market reactions instead.
2. Use competitor_search_tool to find **LATEST (2025-2026)** news about new features, pricing changes,
   or product launches for the given competitor keywords.
3. For the top 3 most relevant results, use web_scraper_tool to read the full article.
4. Extract only high-signal information: new feature releases, pricing changes, major partnerships.
   Ignore marketing fluff and repeat news.
5. Return a list of raw findings (facts) with source URLs. DO NOT provide analysis.

Constraints:
- Be concise. Quality over quantity.
- **Do NOT write a narrative summary or a final report.** Just list the facts.
- Your output is internal data for the 'pm_lead' agent.
- **Summarize findings in Traditional Chinese (繁體中文).**
  (Start your response with: "Raw Market Intelligence Gathered:")
"""

# ---------------------------------------------------------------------------
# PM Lead Agent  —  analyses findings against own product & writes report
# ---------------------------------------------------------------------------

PM_LEAD_PROMPT = """
You are a Senior Product Manager conducting competitive analysis.

Your workflow:
1. Read the researcher_findings from the previous agent.
2. Use your tools to read our internal product spec ('my_product_spec.md') to understand our product, "舒柔衛生紙".
3. Compare the competitor's activities from researcher_findings against our product specs. Identify gaps and opportunities.
4. Assess the threat_level based on this comparison:
   - critical: competitor directly replicates our core differentiator
   - high: significant feature gap that affects retention
   - medium: notable but we have a roadmap response
   - low: minor or unrelated to our core market
5. Propose a concrete counter_strategy (e.g., "Accelerate wet wipe launch", "Match the 10% discount on family packs").
6. Generate a report in the required `CompetitorIntelReport` format.

Be direct and actionable. This report goes straight to the CPO.
**IMPORTANT: All text content in the final report must be in Traditional Chinese (繁體中文).**
"""

def create_root_agent():
    """Create a fresh instance of the agent pipeline with new tool connections."""
    researcher = LlmAgent(
        name="market_researcher",
        model="gemini-2.5-flash",
        instruction=RESEARCHER_PROMPT,
        tools=[
            get_search_mcp_toolset(api_key=SERPER_API_KEY),
            get_scraper_mcp_toolset(),
        ],
        output_key="researcher_findings",
    )

    pm_lead = LlmAgent(
        name="pm_lead",
        model="gemini-2.5-flash",
        instruction=PM_LEAD_PROMPT,
        tools=[get_knowledge_base_mcp_toolset()],
        output_schema=CompetitorIntelReport,
        output_key="intel_report",
    )

    # ---------------------------------------------------------------------------
    # Architecture Decision: Why SequentialAgent?
    # ---------------------------------------------------------------------------
    # 原因 (Cause):
    # 使用單一 LLM 作為總管 (Orchestrator) 時，常發生「過早收斂」問題。
    # 當 Researcher 查完資料並回傳摘要後，總管常誤判任務已完成，直接將摘要回傳，
    # 導致 PM Lead (負責讀取內部規格與產出 JSON) 根本沒機會執行。
    #
    # 結果 (Result):
    # 改用 SequentialAgent 強制鎖定執行順序 (Researcher -> PM Lead)。
    # 無論 Researcher 查到什麼，資料流必定會傳遞給 PM Lead，
    # 確保最終輸出一定是經過內部規格比對的 CompetitorIntelReport JSON 格式。
    return SequentialAgent(
        name="product_intel_agent",
        sub_agents=[researcher, pm_lead],
    )
