from pydantic import BaseModel
import uuid
import os
import json
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, message_to_dict, AnyMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.agents import create_agent, AgentState
from langgraph.runtime import Runtime
from vectordb import Chroma, MongoProvider
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.vectorstores import InMemoryVectorStore
from langgraph.runtime import get_runtime
from dataclasses import dataclass
from datetime import datetime
from tools_registry import Helper
from prompt import TemplatePrompt

from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState, add_messages, StateGraph, END
import langgraph.checkpoint
from typing import (
    Annotated
)


from dotenv import load_dotenv

load_dotenv()


class InputState(BaseModel):
    user_chat_content: HumanMessage
    chat_user_id: str
    messages: Annotated[list[AnyMessage], add_messages]


class OutputState(BaseModel):
    answer: str


class OverallState(InputState, OutputState):
    pass


class BaseLisa:
    agent = {}
    is_new = False
    tools = []
    stream = False
    session = None

    def __init__(self, is_new=False, stream=False):
        print("LISA INITIATE")
        self.is_new = is_new
        self.tools = Helper().get("tools")
        self.stream = stream

    def initiate_chat(self, chat_user_id, prompt, ai_message=None, context="HR_ASSISTANT"):
        session_id = str(uuid.uuid4())
        print("LISA INITIATE CHAT: ", session_id)

        chat_session = self.get_session(chat_user_id, session_id)

        if (context):
            system_message = self.context_definer(
                chat_user_id, context)
            ai_message = self.ai_starter_template(system_message)
        else:
            system_message = SystemMessage(prompt)
            ai_message = AIMessage(ai_message)

        messages = [
            system_message,
            ai_message
        ]
        chat_session.add_messages(messages)

        self.session_titles(chat_user_id, session_id, messages)
        return {
            "session_id": session_id,
        }

    def chat(self, chat_user_id, user_message, session_id, context="HR_ASSISTANT"):
        self.session = self.get_session(chat_user_id, session_id)
        user_message = HumanMessage(content=user_message)
        if (self.is_new):
            system_message = self.context_definer(chat_user_id, context)
            messages = [system_message]
            self.session.add_messages(messages)
        else:
            messages = self.session.messages

        self.session.add_user_message(user_message)
        response = self.main_flow().invoke({
            "user_chat_content": user_message,
            "chat_user_id": chat_user_id,
            "messages": self.session.messages,
        }, config={"configurable": {"thread": session_id, "session": self.session}})

        ai_response = response['messages'][-1]

        self.session_titles(chat_user_id, session_id, self.session.messages)
        return ai_response

    def run_agent_reasoning(self):
        llm = Helper().get('llm')

        def reason(state: MessagesState) -> MessagesState:
            print("=================== STATE ===================")
            print(state)
            response = llm.invoke(state['messages'])
            print("=================== REASONING RESPONSE ===================")
            print(response)
            self.session.add_message(response)
            return {"messages": [response]}

        return reason

    def tool_node(self):
        return ToolNode(Helper().get('tools'))

    def main_flow(self):

        AGENT_REASON = "agent_reason"
        ACT = "act"
        LAST = -1
        SAVE_TOOL_RESPONSE = "save_tool_response"

        def should_continue(state: OverallState) -> str:
            if not state["messages"][LAST].tool_calls:
                return END
            return ACT

        def save_tool_response(state: OverallState) -> str:
            try:
                self.session.add_message(state["messages"][-1])
                return state
            except Exception as e:
                return state

        flow = StateGraph(OverallState, input=InputState, output=OutputState)

        flow.add_node(AGENT_REASON, self.run_agent_reasoning())
        flow.set_entry_point(AGENT_REASON)
        flow.add_node(ACT, self.tool_node())

        flow.add_conditional_edges(AGENT_REASON, should_continue, {
            END: END,
            ACT: ACT,
        })

        flow.add_node(SAVE_TOOL_RESPONSE, save_tool_response)

        flow.add_edge(ACT, SAVE_TOOL_RESPONSE)
        flow.add_edge(SAVE_TOOL_RESPONSE, AGENT_REASON)

        app = flow.compile()

        # app.get_graph().draw_mermaid_png(output_file_path="flow2.png")
        return app

    def session_titles(self, chat_user_id, session_id, messages):
        if self.is_new is False:
            return
        print("MESSAGES", messages)
        db = MongoProvider().getDB()
        collection = db.get_collection('user_session')
        messages = [message_to_dict(message) for message in messages]
        # Summarize Title
        prompt = f"""Buat judul singkat (maksimal 5 kata) untuk percakapan ini:
            {messages}
hiraukan programming literal
respon dengan plain text"""
        print(messages, prompt)
        response = self.invoke([
            HumanMessage(content=prompt)
        ])
        self.title = response.text()
        collection.insert_one({
            'chat_user_id': chat_user_id,
            'session_id': session_id,
            'SessionId': f"{chat_user_id}:{session_id}",
            'title': self.title,
            'created_at': str(datetime.now())
        })

    def ai_starter_template(self, system_message) -> AIMessage:
        response = Helper().get('llm').invoke([
            system_message,
            HumanMessage(
                content="Mulai pembicaraan berdasarkan konteks diatas seolah kamu yang memulai percakapan ini")
        ])
        return response

    def invoke(self, messages):
        response = Helper().get('llm').invoke(messages)
        print(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response

    def context_definer(self, chat_user_id, context="HR_ASSISTANT") -> SystemMessage:
        message = getattr(TemplatePrompt, context)

        return SystemMessage(
            content=message
        )

    def get_session(self, chat_user_id, session_id):
        session = MongoDBChatMessageHistory(
            session_id=chat_user_id + ":" + session_id,
            connection_string=os.getenv("MONGO_URI"),
            database_name=os.getenv("MONGO_DATABASE"),
            collection_name="chat_histories",
        )
        return session
