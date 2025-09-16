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
from agent.tools import tools, retrieve_prompt, fetch_user_data
from vectordb import Chroma, MongoProvider
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.vectorstores import InMemoryVectorStore
from langgraph.runtime import get_runtime
from prompt import ContextDefiner
from dataclasses import dataclass
from datetime import datetime

@dataclass
class UserContext:
    chat_user_id: str
    created_by: str
    # prompt_mode: str

import uuid
class Lisa:
    agent = {}
    def __init__(self):
        print("LISA INITIATE")

    def initiate_chat(self, chat_user_id, prompt):
        session_id = str(uuid.uuid4())
        print("LISA INITIATE CHAT: ", session_id) 

        chat_session = self.get_session(chat_user_id, session_id);
        
        system_message = self.context_definer([HumanMessage(content=prompt)])

        ai_message = self.ai_starter_template(system_message)

        messages = [
            system_message,
            ai_message
        ]
        chat_session.add_messages(messages)

        print(messages)
        return {
            "session_id": session_id,
        }

    def chat(self, chat_user_id, user_message, session_id):
        self.agent = create_agent(
            self.select_model,
            tools=tools,
            context_schema=UserContext,
            prompt=self.dynamic_prompt,
        )

        chat_session = self.get_session(chat_user_id, session_id)
        print(chat_session.messages)

        chat_session.add_user_message(HumanMessage(
            content=user_message, timestamp=str(datetime.now())))
        print("SESSION")
        print(chat_session.messages)

        response = self.agent.invoke({
            "messages": chat_session.messages
        }, context=UserContext(chat_user_id, "user"))
        ai_response = response['messages'][-1]
        chat_session.add_ai_message(ai_response)
        return ai_response
    
    
    def dynamic_prompt(self, state: AgentState, **kwargs):
        isNew = False
        messages = state['messages']
        try:
            messages[1]
            return messages
        except Exception as e:
            isNew = True
            
        runtime = get_runtime(UserContext)
        # Summarize Conversation

        user_info = fetch_user_data.invoke({'chat_user_id':runtime.context.chat_user_id})

        messages = [
                *messages,
                {"role": "user", "content": (
                 """Berdasarkan Informasi User dan Pesan diatas, tentukan context prompt yang sesuai. Lalu gunakan tools retrieve_prompt """
                 f"""About User: {user_info}"""
                 )}
            ]

        system_msg = self.context_definer(messages)
        messages = [system_msg] + state["messages"]
        return messages
    
    def ai_starter_template(self, system_message) -> AIMessage:
        response = ChatOpenAI().invoke([
            system_message,
            HumanMessage(content="Mulai pembicaraan berdasarkan konteks diatas seolah kamu yang memulai percakapan ini")
        ])
        return response

    def invoke(self, messages):
        response = ChatOpenAI().invoke(messages)
        print(messages)

        sess = self.get_session("automated", str(uuid.uuid4()))
        sess.aadd_messages(messages)
        sess.add_ai_message(response)

        return response

    
    def context_definer(self, messages) -> SystemMessage:
        response = ChatOpenAI().bind_tools([retrieve_prompt]).invoke(messages)

        for tc in response.tool_calls:
            print("Tool Calls:", tc)
            fname = tc['name']
            fargs = tc['args'];
            tool_result = globals()[fname].invoke(fargs)
            tool_message = ToolMessage(
                content=tool_result,
                tool_call_id=tc['id']
            )
            print("tool_message")
            print(tool_message)
            tool_message.text()


        return SystemMessage(
            content=tool_message.text()
        )
        
    def select_model(self, state: AgentState, runtime: Runtime) -> ChatOpenAI:
        """Choose model based on conversation complexity."""
        messages = state["messages"]
        message_count = len(messages)

        if message_count < 10:
            return ChatOpenAI(model="gpt-4.1-mini").bind_tools(tools)
        else:
            return ChatOpenAI(model="gpt-5").bind_tools(tools)


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

