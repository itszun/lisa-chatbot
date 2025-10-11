from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState, StateGraph, END

from nodes import run_agent_reasoning, tool_node

load_dotenv()

def main_flow():

    AGENT_REASON="agent_reason"
    ACT="act"
    SAVE_TOOL_RESPONSE="save_tool_response"
    LAST=-1

    def should_continue(state: MessagesState) -> str:
        if not state["messages"][LAST].tool_calls:
            return END
        return ACT
    

    flow = StateGraph(MessagesState)

    flow.add_node(AGENT_REASON, run_agent_reasoning)
    flow.set_entry_point(AGENT_REASON)
    flow.add_node(ACT, tool_node)

    flow.add_conditional_edges(AGENT_REASON, should_continue, {
        END:END,
        ACT:ACT,
    })


    app = flow.compile()

    app.get_graph().draw_mermaid_png(output_file_path="flow.png")
    return app


if __name__ == "__main__":
    print("Hello ReAct Langgraph reasoning")
    app = main_flow()
    res = app.invoke({"messages": [
        HumanMessage(content="Multiply 6 with 2?")
    ]})
    print(res['messages'][-1].content)