from operator import add
from typing import Annotated, List, Literal, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from agent.tools import screening_a_talent, manage_candidate, retrieve_data
from prompt import TALENT_HUNTER_PROMPT

class InputState(TypedDict):
    selected_agent: str
    agent_command: str

class OutputState(TypedDict):
    agent_output: str

class OverallState(InputState, OutputState):
    messages: Annotated[List[BaseMessage], add]

def talent_hunter_agent():
    tools = [
        screening_a_talent, 
        manage_candidate, 
        retrieve_data
    ]
    model = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

    def call_model(state: OverallState):
        local_messages = state.get("messages", [])
        if not local_messages:
            local_messages.append(HumanMessage(content=state["agent_command"]))

        system_message = SystemMessage(
            content=TALENT_HUNTER_PROMPT
        )

        response = model.invoke([system_message] + local_messages)
        state["agent_output"] = response.content
        state["messages"] = local_messages + [response]
        return state
    

    
    def should_continue(state: OverallState) -> Literal["tools", END]:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END
    

    graph = StateGraph(OverallState, input=InputState, output=OutputState)
    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("call_model", should_continue)
    graph.add_edge("tools", "call_model")
    graph.add_edge("call_model", END)

    graph = graph.compile()
    # graph.get_graph().draw_mermaid_png(output_file_path="talent-hunter-agent.png")
    return graph


def talent_hunter_agent_node(state: InputState):
    response = talent_hunter_agent().invoke({"agent_command": state['agent_command']})
    print(response)
    state['agent_output'] = response['agent_output']

    return state