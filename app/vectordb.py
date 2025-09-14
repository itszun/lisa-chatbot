import chromadb
from chromadb.types import Database, Tenant, Collection as CollectionModel
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

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
    def __init__(self):        
        MONGO_URI = os.getenv("MONGO_URI")
        if not MONGO_URI:
            raise RuntimeError("MONGO_URI belum diisi.")
        self._client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

    def client(self):
        return self._client
    
    
    def get_collection(self, collection_name):
        # Ambil database, kalau belum ada otomatis dibuat
        db = self.client()[self.db_name]
        # Ambil collection, kalau belum ada otomatis dibuat
        return db[collection_name]
    

    