# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
.venv/bin/python agent.py     # interactive REPL; exit with exit/quit/q
```

`.env` must define `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` — all three are read with `os.environ[...]` and will raise `KeyError` if missing. `OPENAI_BASE_URL` being mandatory implies an OpenAI-compatible endpoint (not the default `api.openai.com`); preserve that assumption.

No test suite, lint config, or build step exists. Don't invent commands for them.

## Architecture

Single-file LangGraph agent ([agent.py](agent.py)) — a Chinese-language stock assistant named "小盘".

**Graph shape:** `agent → (tools → agent)* → END`. `call_model` always re-prepends `SYSTEM_PROMPT` to `state["messages"]` before invoking the LLM, so the prompt is not stored in state. `should_continue` routes to `tools` iff the last AIMessage has `tool_calls`. Checkpointing uses `MemorySaver` with a hardcoded `thread_id="session-1"` — restarting the process drops history.

**Tool routing is market-specific and must stay that way:**
- [`get_stock_price`](agent.py#L22-L33) — yfinance daily close for US/HK (`AAPL`, `0700.HK`, …). Daily data only, never intraday.
- [`get_a_share_realtime`](agent.py#L57-L85) — A-share quasi-realtime via `hq.sinajs.cn` (Sina Finance). Required header `Referer: https://finance.sina.com.cn` — without it Sina returns empty. Response is GBK-encoded; `r.encoding = "gbk"` is load-bearing.

**A-share code normalization** ([_normalize_a_share_code](agent.py#L36-L44), [_sina_prefix](agent.py#L47-L54)): strips `sh/sz/bj` prefixes and `.SS/.SZ/.BJ` suffixes, then re-derives the Sina prefix from the leading digits (`60/68/9/5→sh`, `00/30/20→sz`, `8/43→bj`). When adding new code ranges (e.g. new STAR/ChiNext series), update both functions.

**System prompt invariants** ([SYSTEM_PROMPT](agent.py#L99-L108)) — these are product rules, not stylistic suggestions:
1. The model must call a tool for any price/quote — no answering from memory.
2. Chinese stock names must be translated to codes before the tool call (茅台→600519, 英伟达→NVDA).
3. Every price in the reply must carry its data timestamp.
4. No buy/sell recommendations; deflect with risk disclaimer.

When changing tools, mirror updates in the prompt's routing rules (item 2) — the LLM relies on prompt text, not docstrings alone, to pick the right tool.
