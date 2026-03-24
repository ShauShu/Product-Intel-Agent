# LLM Agent 開發踩坑實錄 (Lessons Learned)

記錄在開發 Product Intel Agent 過程中遇到的 Multi-Agent 溝通與協作問題，以及最終的解決方案。

## 1. 核心問題：偷懶的總管 (The Lazy Orchestrator)

### 現象
在原本使用單一 **Orchestrator (總管)** 來調度多個子 Agent 的架構下，經常發生「過早收斂 (Premature Convergence)」的情況：

1. **流程中斷**：總管委派 `Researcher` 找完資料後，看到 `Researcher` 回傳了一段詳細的新聞摘要。
2. **誤判結束**：總管認為「使用者的問題（分析競品）已經被回答了」，於是直接把這段摘要印出來給使用者。
3. **PM 失業**：負責深度分析、讀取內部規格書的 `PM Lead` 完全沒有被呼叫，導致最終報告缺乏「威脅等級」與「反制策略」。

### 原因分析
- **模型天性**：LLM 被訓練為「盡快提供有用的回答」。當它看到 `Researcher` 提供的豐富資訊時，傾向於直接滿足使用者，而不是執行繁瑣的後續步驟。
- **Prompt 漏洞**：如果沒有明確禁止總管「自己寫報告」，它會傾向於用自己的預訓練知識或剛拿到的 Context 來瞎掰結論。

---

## 2. 角色越權與幻覺 (Scope Creep & Hallucination)

### 現象
當我們試圖強迫總管產出 JSON 格式的報告 (`CompetitorIntelReport`) 時，若它沒有正確呼叫 `PM Lead`：

- **瞎掰數據**：總管會憑空捏造 `threat_level`（威脅等級）和 `our_counter_strategy`（反制策略）。
- **缺乏依據**：因為總管身上沒有 `read_product_doc` 工具（該工具綁定在 PM 身上），這些策略完全沒有根據自家產品規格來制定，毫無參考價值。

---

## 3. 解決方案 (The Fix)

為了根治上述問題，我們放棄了讓 LLM 自由判斷流程，轉而採用 **更嚴格的架構控制** 與 **提示工程**。

### A. 架構層面：改用 `SequentialAgent`

我們將原本的動態路由 (Router) 改為強制序列 (Pipeline)：

```python
# agent.py
return SequentialAgent(
    name="product_intel_agent",
    sub_agents=[researcher, pm_lead], # 強制鎖定順序：先找資料 -> 再分析
)
```
**效果**：無論 `Researcher` 查到什麼，資料流 **一定** 會被送到 `PM Lead` 手上，總管沒有權力提早結束。

### B. 提示工程 (Prompt Engineering)

- **對 Researcher 的約束**：明確要求「**不要寫總結 (Do NOT summarize)**」、「只提供條列式事實 (List facts)」、「你的輸出是給 PM 看的內部資料」。
- **對 PM Lead 的約束**：給予明確的工具 `read_product_doc` 並要求必須參考內部文件才能產出報告。