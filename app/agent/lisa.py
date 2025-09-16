import os
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.agents import create_agent, AgentState
from langgraph.runtime import Runtime
from agent.tools import tools

class Lisa:
    agent = {}
    def __init__(self):
        self.agent = create_agent(
            self.select_model,
            tools=tools,
            prompt=self.dynamic_prompt,
        )

    def chat(self, message, session_id):
        chat_session = self.get_session(session_id)
        print(chat_session.messages)

        chat_session.add_user_message(HumanMessage(content=message))
        print("SESSION")
        print(chat_session.messages)
        response = self.agent.invoke({
            "messages": 
                chat_session.messages,
                
        })
        ai_response = response['messages'][-1]
        chat_session.add_ai_message(ai_response)
        return ai_response
    
    
    def dynamic_prompt(self, state):
        user_type = state.get("user_type", "standard")
        system_msg = SystemMessage(
            content="Provide detailed technical responses."
            if user_type == "expert"
            else "Provide simple, clear explanations."
        )
        return [system_msg] + state["messages"]
        
    def select_model(self, state: AgentState, runtime: Runtime) -> ChatOpenAI:
        """Choose model based on conversation complexity."""
        messages = state["messages"]
        message_count = len(messages)

        if message_count < 10:
            return ChatOpenAI(model="gpt-4.1-mini").bind_tools(tools)
        else:
            return ChatOpenAI(model="gpt-5").bind_tools(tools)


    def get_session(self, session_id):
        return MongoDBChatMessageHistory(
            session_id=session_id,
            connection_string=os.getenv("MONGO_URI"),
            database_name=os.getenv("MONGO_DATABASE"),
            collection_name="chat_histories",
        )

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

