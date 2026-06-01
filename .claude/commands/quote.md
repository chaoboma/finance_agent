---
description: Ask the finance agent for a quote. Pass a code or Chinese name, e.g. /quote 茅台 or /quote NVDA or /quote 0700.HK.
---

Get a quote for: **$ARGUMENTS**

1. If the tmux session `finance` does not already exist, invoke the `launching-finance-agent` skill to start it. If it does exist, reuse it.
2. Send `$ARGUMENTS 现在多少钱` to the session via `tmux send-keys -t finance ... Enter`, then `sleep 10` and `tmux capture-pane -t finance -p`.
3. From the captured output, return ONLY the final `[节点: agent]` 中文 reply (the price + timestamp line) — not the tool-call JSON or the intermediate node logs.
4. If the reply is missing a timestamp, contains buy/sell advice, or skipped the tool call, flag it as a `SYSTEM_PROMPT` regression instead of silently returning the price.
