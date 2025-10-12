from operator import add
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from typing import TypedDict, Literal, Annotated, List
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from agent.tools import manage_candidate, manage_company, manage_job_opening, manage_talent, retrieve_data
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from prompt import HR_ASSISTANT_PROMPT
from langchain_core.prompts import PromptTemplate

load_dotenv()

class InputState(TypedDict):
    selected_agent: str
    agent_command: str
    command: str                             # Text asli dari user

class OutputState(TypedDict):
    agent_output: str

class OverallState(InputState, OutputState):
    messages: Annotated[List[BaseMessage], add]

def hr_manager_agent():
    tools = [manage_candidate, manage_company, manage_job_opening, manage_talent, retrieve_data]
    model = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

    def call_model(state: OverallState):
        local_messages = state.get("messages", [])
        agent_command = state['agent_command']
        if not local_messages:
            human_message = HumanMessage(content=agent_command)
            local_messages.append(human_message)

        system_message = SystemMessage(
            content=PromptTemplate.from_template(HR_ASSISTANT_PROMPT).format(
                agent_command=agent_command,
                user_command=state.get('command')
            )
        )

        response = model.invoke([system_message] + local_messages)

        state['agent_output'] = response.content
        state['messages'] = local_messages + [response]
        return state

    def should_continue(state: OverallState) -> Literal["tools", END]:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END
    
    current_hr_manager = StateGraph(OverallState, input=InputState, output=OutputState)
    current_hr_manager.add_node("call_model", call_model)
    current_hr_manager.add_node("tools", ToolNode(tools))
    current_hr_manager.add_edge(START, "call_model")
    current_hr_manager.add_conditional_edges("call_model", should_continue)
    current_hr_manager.add_edge("tools", "call_model")

    return current_hr_manager.compile()

    

def hr_manager_agent_node(state: InputState):
    response = hr_manager_agent().invoke({"agent_command": state['agent_command']})
    print(response)
    state['agent_output'] = response['agent_output']

    return state