import os, uuid
from agent.base_agent import BaseLisa
from agent.supervisor_agent import supervisor_agent
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, message_to_dict, AnyMessage
from vectordb import MongoProvider
from datetime import datetime
from agent.react_agent import react_agent
from chatbot_service import chatbot_service_dict

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
    
    def chat2(self, chat_user_id, user_msg, session_id):
        chat_session = self.get_session(chat_user_id, session_id)
        header_session = self.get_header_session(session_id)

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

        cs = chatbot_service_dict[header_session['chatbot_service']]
        response = react_agent(cs['system_prompt'], cs['tools']).invoke(state, {"configurable": {"thread_id": session_id}})

        ai_msg = response["messages"][-1]
        chat_session.add_message(ai_msg)

        self.session_titles(chat_user_id, session_id, chat_session.messages)
        return ai_msg

    def get_header_session(self, session_id): 
        db = MongoProvider().getDB()
        collection = db.get_collection('user_session')

        result = collection.find_one({
            'session_id': session_id,
        })
        return result
    
    def new_session(self, chat_user_id, session_id, chatbot_service):
        db = MongoProvider().getDB()
        collection = db.get_collection('user_session')

        title = "chatbot_service"
        
        insert_result = collection.insert_one({
            'chat_user_id': chat_user_id,
            'session_id': session_id,
            'SessionId': f"{chat_user_id}:{session_id}",
            'title': title,
            'created_at': str(datetime.now()),
            'chatbot_service': chatbot_service
        })
        # new_document_id = insert_result.inserted_id

        session = MongoDBChatMessageHistory(
            session_id=chat_user_id + ":" + session_id,
            connection_string=os.getenv("MONGO_URI"),
            database_name=os.getenv("MONGO_DATABASE"),
            collection_name="chat_histories",
        )

        cs = chatbot_service_dict[chatbot_service]

        session.add_message(AIMessage(content=cs['message_opener']))
        return session

    