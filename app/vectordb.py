import chromadb
from chromadb.types import Database, Tenant, Collection as CollectionModel
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from pattern_decorator import singleton

@singleton
class Chroma:
    _client = {}

    def __init__(self):
        self._client = chromadb.CloudClient(
            api_key=os.getenv("CHROMADB_API_KEY"),
            tenant='39d106f4-0829-4e38-beed-1e8627fe7afb',
            database=os.getenv("CHROMADB_DB")
        )

    def client(self):
        return self._client

    def clean(self):
        """
        Deletes all existing collections in the ChromaDB database.
        """
        print("Starting to delete all collections...")
        try:
            # Mengambil daftar semua koleksi
            collections = self._client.list_collections()

            if not collections:
                print("No collections found to delete.")
                return True

            for collection in collections:
                collection_name = collection.name
                print(f"Deleting collection: '{collection_name}'...")
                self._client.delete_collection(collection_name)

            print("All collections have been successfully deleted.")
            return True
        except Exception as e:
            print(f"An error occurred while deleting collections: {e}")
            return False


@singleton
class MongoProvider:

    _client = {}
    db_name = "chatbot_db"
    database_name = ""

    def __init__(self):
        MONGO_URI = os.getenv("MONGO_URI")
        if not MONGO_URI:
            raise RuntimeError("MONGO_URI belum diisi.")
        self._client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        self.database_name = os.getenv('MONGO_DATABASE')

    def client(self):
        return self._client
    
    def getDB(self):
        return self.client()[self.database_name]

    def get_collection(self, collection_name):
        # Ambil database, kalau belum ada otomatis dibuat
        db = self.client()[self.db_name]
        # Ambil collection, kalau belum ada otomatis dibuat
        return db[collection_name]

    def get_session(self, match_criteria):
        PIPELINE = [
            {
                '$sort': { "created_at": -1 } 
            },
            {
                '$group': {
                    "_id": '$chat_user_id',
                    "sessions": {
                        '$push': {
                            "session_id": "$session_id",
                            "SessionId": "$SessionId", 
                            "title": "$title",
                            "created_at": "$created_at"
                        }
                    }
                }
            }
            ,
            {
                '$project': {
                    "chat_user_id": "$_id",
                    "sessions": 1,
                }
            },
            {
                '$match': match_criteria
            },
        ]

        db = self.getDB()
        collection = db.get_collection('user_session')
        result = list(collection.aggregate(PIPELINE))
        return result

    def get_session_messages(self, match_criteria):
        SESSION_PIPELINE = [
            {
                '$group': {
                    '_id': '$SessionId',
                    'messages': {
                        '$push': '$History'
                    }
                }
            },
            {
                '$addFields': {
                    'chat_user_id': {
                        '$arrayElemAt': [
                            {
                                '$split': ['$_id', ':']
                            },
                            0
                        ]
                    },
                    'session_id': {
                        '$arrayElemAt': [
                            {
                                '$split': ['$_id', ':']
                            },
                            1
                        ]
                    }
                }
            },
            {
                '$project': {
                    '_id': 0,
                    'chat_user_id': 1,
                    'session_id': 1,
                    'messages': 1
                }
            },
            {
                '$match': match_criteria
            }
        ]
        db = self.getDB()
        collection = db.get_collection('chat_histories')
        print("COLLECTION")
        print(collection)
        result = list(collection.aggregate(SESSION_PIPELINE))
        return result
