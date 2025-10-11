import uuid
import os
import json
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, message_to_dict
from langchain_core.runnables.history import RunnableWithMessageHistory
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
from langgraph.graph import MessagesState, StateGraph, END


from dotenv import load_dotenv

load_dotenv()

class BaseLisa:
    agent = {}
    is_new = False
    tools = []
    llm = None

    def __init__(self, is_new=False):
        print("LISA INITIATE")
        self.is_new = is_new
        self.tools = Helper().get("tools")
        print("GET LLM")
        print(Helper().get("llm"))
        self.llm = Helper().get("llm")

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
        chat_session = self.get_session(chat_user_id, session_id)
        user_message = HumanMessage(content=user_message)
        if (self.is_new):
            system_message = self.context_definer(chat_user_id, context)
            messages = [system_message]
            chat_session.add_messages(messages)
        else:
            messages = chat_session.messages

        chat_session.add_user_message(user_message)
        response = self.main_flow(messages).invoke({"messages": [user_message]})
        ai_response = response['messages'][-1]
        chat_session.add_ai_message(ai_response)

        self.session_titles(chat_user_id, session_id, chat_session.messages)
        return ai_response

    def run_agent_reasoning(self, messages):
        llm = self.llm
        def reason(state: MessagesState) -> MessagesState:
            response = llm.invoke([*messages, *state['messages']])
            return {"messages": [response]}

        return reason

    def tool_node(self):
        return ToolNode(Helper().get('tools'))
    
    def main_flow(self, messages):

        AGENT_REASON="agent_reason"
        ACT="act"
        LAST=-1

        def should_continue(state: MessagesState) -> str:
            if not state["messages"][LAST].tool_calls:
                return END
            return ACT

        flow = StateGraph(MessagesState)

        flow.add_node(AGENT_REASON, self.run_agent_reasoning(messages))
        flow.set_entry_point(AGENT_REASON)
        flow.add_node(ACT, self.tool_node())

        flow.add_conditional_edges(AGENT_REASON, should_continue, {
            END:END,
            ACT:ACT,
        })

        flow.add_edge(ACT, AGENT_REASON)

        app = flow.compile()

        app.get_graph().draw_mermaid_png(output_file_path="flow.png")
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
        response = self.llm.invoke([
            system_message,
            HumanMessage(
                content="Mulai pembicaraan berdasarkan konteks diatas seolah kamu yang memulai percakapan ini")
        ])
        return response

    def invoke(self, messages):
        response = self.llm.invoke(messages)
        print(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.add_messages(messages)
        sess.add_ai_message(response)

        return response

    def context_definer(self, chat_user_id, context = "HR_ASSISTANT") -> SystemMessage:
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
