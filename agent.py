import os
from typing import Annotated, Literal, TypedDict

import requests
import yfinance as yf
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

load_dotenv()


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def get_stock_price(symbol: str) -> str:
    """查询股票最近收盘价（日线，非实时）。适用于美股（AAPL）、港股（0700.HK）等 Yahoo Finance 代码。A 股请用 get_a_share_realtime。"""
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty:
            return f"{symbol}: 未查到行情数据，可能代码错误。"
        last = hist.iloc[-1]
        date = hist.index[-1].strftime("%Y-%m-%d")
        return f"{symbol} 最近收盘价（{date}）: {float(last['Close']):.2f}"
    except Exception as e:
        return f"{symbol} 查询失败: {e}"


def _normalize_a_share_code(symbol: str) -> str:
    code = symbol.strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            code = code[len(prefix):]
    for suffix in (".ss", ".sz", ".bj"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
    return code


def _sina_prefix(code: str) -> str:
    if code.startswith(("60", "68", "9", "5")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    if code.startswith(("8", "43")):
        return "bj"
    return "sh"


@tool
def get_a_share_realtime(symbol: str) -> str:
    """查询 A 股实时行情（盘中近实时，来源新浪财经）。输入 6 位代码，例如 600519（茅台）、000001（平安银行）、300750（宁德时代）。支持带 sh/sz 前缀或 .SS/.SZ 后缀。"""
    code = _normalize_a_share_code(symbol)
    sina_code = f"{_sina_prefix(code)}{code}"
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={sina_code}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=10,
        )
        r.encoding = "gbk"
        body = r.text.split('"', 2)
        if len(body) < 2 or not body[1]:
            return f"{code} 未查到行情，可能代码错误或停牌。"
        fields = body[1].split(",")
        name, today_open, prev_close, latest, high, low = (
            fields[0], float(fields[1]), float(fields[2]),
            float(fields[3]), float(fields[4]), float(fields[5]),
        )
        date, time_ = fields[30], fields[31]
        change_pct = (latest - prev_close) / prev_close * 100 if prev_close else 0.0
        return (
            f"{name}({code}) {date} {time_} 实时: 最新 {latest:.2f} "
            f"涨跌幅 {change_pct:+.2f}% "
            f"今开 {today_open:.2f} 最高 {high:.2f} 最低 {low:.2f} 昨收 {prev_close:.2f}"
        )
    except Exception as e:
        return f"{code} 查询失败: {e}"


tools = [get_stock_price, get_a_share_realtime]
tool_node = ToolNode(tools)

llm = ChatOpenAI(
    model=os.environ["OPENAI_MODEL"],
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
    temperature=0,
).bind_tools(tools)


SYSTEM_PROMPT = SystemMessage(content="""你是一名专业的股票投资助手，名叫"小盘"。回答用户问题时请遵循以下规则：

1. **永远使用工具查真实数据**，不要凭记忆或推测说出价格、涨跌幅、成交量等行情数字。即使用户问的是几小时前的价格，也应调用工具确认。
2. 工具路由：
   - 美股（AAPL、NVDA 等）、港股（0700.HK 等）→ `get_stock_price`，返回日线收盘价
   - A 股（茅台、宁德时代、平安银行 等）→ `get_a_share_realtime`，返回盘中实时
3. 用户用中文名提到股票时（如"茅台""英伟达"），自动翻译成对应代码再调工具（茅台→600519，英伟达→NVDA，宁德时代→300750 等）。
4. 输出价格时一定要带数据时间，让用户知道数据新鲜度。例如"贵州茅台 1361.84 元（2026-05-11 13:47 盘中）"或"NVDA $215.20（2026-05-08 收盘）"。
5. **不提供买卖建议**。如果用户问"该不该买""涨到 X 该不该卖"，礼貌说明你只提供信息和分析框架，最终决策需用户自负；提醒"投资有风险，入市需谨慎"。
6. 回答简洁专业，用中文。涉及多只股票对比时，列表或表格呈现更清晰。""")


def call_model(state: State):
    response = llm.invoke([SYSTEM_PROMPT] + state["messages"])
    return {"messages": [response]}


def should_continue(state: State) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


workflow = StateGraph(State)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile(checkpointer=MemorySaver())


def main():
    print("--- Agent 已启动，输入 exit / quit / q 退出 ---")
    config = {"configurable": {"thread_id": "session-1"}}

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("再见。")
            break

        inputs = {"messages": [HumanMessage(content=user_input)]}
        for event in app.stream(inputs, config):
            for node, value in event.items():
                print(f"\n[节点: {node}]")
                for msg in value["messages"]:
                    if getattr(msg, "content", None):
                        print(f"输出内容: {msg.content}")
                    if getattr(msg, "tool_calls", None):
                        print(f"工具调用: {msg.tool_calls}")


if __name__ == "__main__":
    main()
