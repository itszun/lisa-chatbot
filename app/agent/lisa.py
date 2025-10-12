import os, uuid
from agent.base_agent import BaseLisa
from agent.supervisor_agent import supervisor_agent
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, message_to_dict, AnyMessage

class Lisa(BaseLisa):
    def __init__(self, is_new=False):
        self.history = None
        self.supervisor = supervisor_agent()
        self.is_new = is_new


    def get_session(self, chat_user_id, session_id):
        session = MongoDBChatMessageHistory(
            session_id=chat_user_id + ":" + session_id,
            connection_string=os.getenv("MONGO_URI"),
            database_name=os.getenv("MONGO_DATABASE"),
            collection_name="chat_histories",
        )
        return session
    
    
    def chat(self, chat_user_id, user_msg, session_id):
        chat_session = self.get_session(chat_user_id, session_id)
        
        human_message = HumanMessage(content=user_msg)
        chat_session.add_message(human_message)
        state = {
            "command": user_msg,
            "user_chat_content": HumanMessage(content=user_msg),
            "chat_user_id": chat_user_id,
            "session_id": session_id,
            "chat_session": chat_session,
            "messages": chat_session.messages,
        }

        print("======= STATE ======")
        print(state)

        response = self.supervisor.invoke(state, {"configurable": {"thread_id": session_id}})

        ai_msg = response["messages"][-1]
        chat_session.add_message(ai_msg)

        self.session_titles(chat_user_id, session_id, chat_session.messages)
        return ai_msg