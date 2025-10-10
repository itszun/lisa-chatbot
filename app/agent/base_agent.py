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

@dataclass
class UserContext:
    chat_user_id: str
    created_by: str
    # prompt_mode: str


class BaseLisa:
    agent = {}
    is_new = False
    tools = []

    def __init__(self, is_new=False):
        print("LISA INITIATE")
        self.is_new = is_new
        self.tools = Helper().get("tools")

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

        if (self.is_new):
            messages = [HumanMessage(
                content=user_message, timestamp=str(datetime.now()))]
            system_message = self.context_definer(chat_user_id, context)
            messages = [system_message, *messages]
            chat_session.add_messages(messages)
        else:
            chat_session.add_user_message(HumanMessage(
                content=user_message, timestamp=str(datetime.now())))
            messages = chat_session.messages

        self.agent = create_agent(
            self.select_model,
            tools=Helper().get('tools'),
            context_schema=UserContext,
        )
        print(":: AGENT INVOKE START")
        response = self.agent.invoke({
            "messages": messages
        }, context=UserContext(chat_user_id, "user"))
        print(":: AGENT INVOKE END")
        print(":: Response")
        print(response)
        ai_response = response['messages'][-1]
        chat_session.add_ai_message(ai_response)

        self.session_titles(chat_user_id, session_id, chat_session.messages)
        return ai_response

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
        response = ChatOpenAI().invoke([
            system_message,
            HumanMessage(
                content="Mulai pembicaraan berdasarkan konteks diatas seolah kamu yang memulai percakapan ini")
        ])
        return response

    def invoke(self, messages):
        response = ChatOpenAI().invoke(messages)
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

    def select_model(self, state: AgentState, runtime: Runtime) -> ChatOpenAI:
        """Choose model based on conversation complexity."""
        messages = state["messages"]
        message_count = len(messages)

        if message_count < 10:
            return ChatOpenAI(model="gpt-4.1-mini").bind_tools(Helper().get('tools'))
        else:
            return ChatOpenAI(model="gpt-5").bind_tools(Helper().get('tools'))

    def get_session(self, chat_user_id, session_id):
        session = MongoDBChatMessageHistory(
            session_id=chat_user_id + ":" + session_id,
            connection_string=os.getenv("MONGO_URI"),
            database_name=os.getenv("MONGO_DATABASE"),
            collection_name="chat_histories",
        )
        return session

    def prompt_template(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a helpful assistant."),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{question}"),
            ]
        )

        chain = prompt | ChatOpenAI()
        return chain

    def vector_store(self, collection):
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        return Chroma(
            collection_name=collection,
            embedding_function=embeddings,
        )

    def chain_with_history(self):
        chain = self.prompt_template()
        return RunnableWithMessageHistory(
            chain,
            lambda session_id: self.get_session(session_id),
            input_messages_key="question",
            history_messages_key="history",
        )

    # This is where we configure the session id
