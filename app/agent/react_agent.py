from operator import add
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from typing import TypedDict, Literal, Annotated, List
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from agent.tools import manage_candidate, manage_company, manage_job_opening, manage_talent, retrieve_data
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from prompt import HR_ASSISTANT_PROMPT
from langchain_core.prompts import PromptTemplate
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from typing import Annotated, List, Literal, TypedDict, Optional, Any
from langgraph.graph.message import add_messages

load_dotenv()

class InputState(TypedDict):
    """Input mentah dari user yang masuk ke Supervisor."""
    user_chat_content: HumanMessage          # Pesan dari user (dibungkus LangChain)
    chat_user_id: str                        # ID user (unique identifier)
    session_id: str                          # ID sesi (thread)
    chat_session: MongoDBChatMessageHistory  # Objek history LangChain
    command: str                             # Text asli dari user
    messages: Annotated[List[BaseMessage], add_messages]

class OutputState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class OverallState(InputState, OutputState):
    selected_agent: str
    messages: Annotated[List[BaseMessage], add_messages]

def react_agent(system_prompt, tools):
    model = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

    def call_model(state: OverallState):
        local_messages = state.get("messages", [])
        human_message = state['user_chat_content']
        system_message = SystemMessage(content=system_prompt)

        response = model.invoke([system_message] + local_messages + [human_message])

        state['messages'] = local_messages + [response]
        return state

    def should_continue(state: OverallState) -> Literal["tools", END]:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END
    
    flow = StateGraph(OverallState, input=InputState, output=OutputState)
    flow.add_node("call_model", call_model)
    flow.add_node("tools", ToolNode(tools))
    flow.add_edge(START, "call_model")
    flow.add_conditional_edges("call_model", should_continue)
    flow.add_edge("tools", "call_model")

    return flow.compile()