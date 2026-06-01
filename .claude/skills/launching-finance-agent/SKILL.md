---
name: launching-finance-agent
description: Use when asked to run, start, or interact with finance_agent — launches agent.py inside a tmux session and drives it via send-keys / capture-pane.
---

# Launching finance_agent

The app is an interactive Chinese REPL (`input()` loop in [agent.py](../../../agent.py)). Drive it through tmux so you can both type to it and read its output.

## Preflight

- `.env` must define `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` — all three are read with `os.environ[...]` and `KeyError` otherwise. `OPENAI_BASE_URL` being mandatory implies an OpenAI-compatible endpoint, don't drop it.
- Use the project's own venv (`.venv/bin/python`). Do not `pip install` into system Python.

## Launch

```bash
tmux kill-session -t finance 2>/dev/null
tmux new-session -d -s finance -x 200 -y 50 '.venv/bin/python agent.py 2>&1; echo "[exited with $?]"; exec bash'
sleep 3
tmux capture-pane -t finance -p
```

Wait for the `你:` prompt before sending input. A LangGraph `LangChainPendingDeprecationWarning` about `allowed_objects` is harmless — ignore it.

## Drive

```bash
tmux send-keys -t finance '茅台现在多少钱' Enter
sleep 10   # LLM round-trip + tool call; A-share tool is faster, US tool sometimes slower
tmux capture-pane -t finance -p
```

For longer queries or multi-tool flows, raise the sleep to 15–20s and re-capture rather than guess.

## What a healthy turn looks like

```
[节点: agent]
工具调用: [{'name': 'get_a_share_realtime'|'get_stock_price', 'args': {...}, ...}]

[节点: tools]
输出内容: <price line from the tool>

[节点: agent]
输出内容: <中文 reply containing the price AND a timestamp>
```

Regression signals — flag these, don't silently accept:
- Final reply has a price but no timestamp → violates the `SYSTEM_PROMPT` rule #4.
- Final reply gives buy/sell advice → violates rule #5.
- Agent answered without any `[节点: tools]` step on a price question → violates rule #1 ("永远使用工具查真实数据").
- For 茅台/平安/宁德 etc. the tool called was `get_stock_price` instead of `get_a_share_realtime` (or vice versa for US/HK) → routing regression in either the prompt or the docstrings.

## Cleanup

```bash
tmux send-keys -t finance 'q' Enter
tmux kill-session -t finance 2>/dev/null
```
