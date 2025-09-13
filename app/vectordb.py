import chromadb
from chromadb.types import Database, Tenant, Collection as CollectionModel
import os

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
            database='lisa-chat'
        )
    
    def client(self):
        return self._client