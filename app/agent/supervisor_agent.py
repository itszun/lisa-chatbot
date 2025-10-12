from langgraph.graph.message import add_messages
from typing import Annotated, List, Literal, TypedDict, Optional, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import START, END, StateGraph
from agent.hr_manager_agent import hr_manager_agent_node
from agent.talent_hunter_agent import talent_hunter_agent_node
from agent.onboarding_agent import onboarding_agent_node
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from pydantic import BaseModel, Field
from prompt import SUPERVISOR_PROMPT, FALLBACK_PROMPT, SUMMARIZE_PROMPT
from langchain_core.prompts import PromptTemplate
from vectordb import mongodb_memory
    
class InputState(TypedDict):
    """Input mentah dari user yang masuk ke Supervisor."""
    user_chat_content: HumanMessage          # Pesan dari user (dibungkus LangChain)
    chat_user_id: str                        # ID user (unique identifier)
    session_id: str                          # ID sesi (thread)
    chat_session: MongoDBChatMessageHistory  # Objek history LangChain
    command: str                             # Text asli dari user
    messages: Annotated[List[BaseMessage], add_messages]

class AgentState(TypedDict, total=False):
    """State yang diproduksi oleh agent-agent anak (HR Manager, Talent Hunter, dll)."""
    current_agent: Optional[str]             # Nama agent yang sedang aktif
    agent_output: Optional[str]              # Output teks dari agent terakhir
    tool_outputs: Optional[List[ToolMessage]]# Pesan hasil tool call (jika ada)


class OutputState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

class OverallState(InputState, OutputState):
    selected_agent: str
    agent_command: str
    agent_output: Any
    messages: Annotated[List[BaseMessage], add_messages]

class RouteDecision(BaseModel):
    content: str = Field(description="Textual response")
    agent: str = Field(description="Choosen Agent name: either hr_manager, talent_hunter, onboarding, fallback_prompt, direct")
    command: str = Field(description="System Message Prompt for agent to start working")

def supervisor_agent():
    model = ChatOpenAI(model="gpt-4o-mini")

    hr = hr_manager_agent_node
    hunter = talent_hunter_agent_node
    onboarding = onboarding_agent_node
    

    def supervisor_node(state: OverallState) -> OverallState:
        """
        Use the LLM to interpret the human request and decide which agent should handle it.
        """
        messages = state.get("messages", [])
        print("====== SUPERVISOR NODE State ======")
        print(state)
        human = state["user_chat_content"]
        system = SystemMessage(
            content=PromptTemplate.from_template(SUPERVISOR_PROMPT).format(
                user_chat_content=human.content
            )
        )
        structured = model.with_structured_output(RouteDecision)
        res: RouteDecision = structured.invoke([system] + messages)
        state['selected_agent'] = res.agent.lower()
        state['agent_command'] = res.command

        return state

    def route_agent(state: OverallState) -> Literal["hr_manager", "talent_hunter", "onboarding", "fallback_response"]:
        selected_agent = state.get('selected_agent', 'UNKNOWN') # Ambil hasil keputusan Supervisor

        # Logika routing berdasarkan key yang dikembalikan LLM (res.agent)
        if "hunter" in selected_agent:
            return "talent_hunter"
        elif "onboard" in selected_agent:
            return "onboarding"
        elif "hr" in selected_agent or "manager" in selected_agent:
            return "hr_manager"
        elif "direct" in selected_agent:
            return END
        else:
            # Jika hasil LLM tidak sesuai, arahkan ke fallback_response
            return "fallback_response"

    def summarize(state: OverallState):
        agent_command = state.get('agent_command')
        system_msg = SystemMessage(
            content=PromptTemplate.from_template(SUMMARIZE_PROMPT).format(
                agent_command=agent_command
            )
        )
        response = model.invoke([system_msg])
        state["final_output"] = response.content
        state["messages"].append(response)
        return state

    def fallback_response(state: OverallState):
        messages = state.get("messages", [])
        human = state["user_chat_content"]
        system_msg = SystemMessage(
            content=PromptTemplate.from_template(FALLBACK_PROMPT).format(
                user_chat_content=human.content,
                supervisor_instruction=state.get('agent_command')
            )
        )
        response = model.invoke([system_msg] + messages + [human])

        state["final_output"] = response.content
        state["messages"].append(response)
        return state

    graph = StateGraph(OverallState, input=InputState, output=OutputState)
    graph.add_node("summarize", summarize)
    graph.add_node("hr_manager", hr)
    graph.add_node("talent_hunter", hunter)
    graph.add_node("onboarding", onboarding)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("fallback_response", fallback_response)

    graph.set_entry_point('supervisor')
    graph.add_conditional_edges('supervisor', route_agent, {
        "hr_manager": "hr_manager",
        "talent_hunter": "talent_hunter",
        "onboarding": "onboarding",
        "fallback_response": "fallback_response"
    })
    graph.add_edge("hr_manager", "summarize")
    graph.add_edge("talent_hunter", "summarize")
    graph.add_edge("onboarding", "summarize")
    graph.add_edge("fallback_response", END)
    graph.add_edge("summarize", END)

    graph = graph.compile()
    # graph.get_graph().draw_mermaid_png(output_file_path="multi-agent-supervisor.png")

    return graph
