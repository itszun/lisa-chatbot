from operator import add
from typing import Annotated, List, Literal, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph

class InputState(TypedDict):
    selected_agent: str
    agent_command: str

class InputState(TypedDict):
    command: str

class OutputState(TypedDict):
    agent_output: str

class OverallState(InputState, OutputState):
    messages: Annotated[List[BaseMessage], add]

def onboarding_agent():
    model = ChatOpenAI(model="gpt-4o-mini")

    def call_model(state: OverallState):
        local_messages = state.get("messages", [])
        if not local_messages:
            local_messages.append(HumanMessage(content=state["agent_command"]))

        system_message = SystemMessage(
            content="You are an Onboarding Specialist agent. You assist with new hire paperwork, orientation, and initial training coordination."
        )

        response = model.invoke([system_message] + local_messages)
        state["agent_output"] = response.content
        state["messages"] = local_messages + [response]
        return state

    graph = StateGraph(OverallState, input=InputState, output=OutputState)
    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", END)

    return graph.compile()



def onboarding_agent_node(state: InputState):
    response = onboarding_agent().invoke({"agent_command": state['agent_command']})
    print(response)
    state['agent_output'] = response['agent_output']

    return state