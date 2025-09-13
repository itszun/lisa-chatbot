from vectordb import Chroma

class Feeder():

    def pushTalentInfo(self, data):
        def callback(item): 
            return f"Lowongan Kerja {item['title']}\n Job Description: {item['body']}"
        
        self.feed(data, collection_name="talent_pool", callback=callback)

    def pushCompanyInfo(self, data):
        def callback(item): 
            return f"Nama Company {item['name']}\n Job Description: {item['body']}"
        
        self.feed(data, collection_name="company", callback=callback)

    def pushCandidate(self, data):
        def callback(item): 
            return f"Lowongan Kerja {item['-']}\n Job Description: {item['body']}"
        
        self.feed(data, collection_name="candidate", callback=callback)

    def pushJobOpening(self, data):
        def callback(item): 
            return f"Lowongan Kerja {item['title']}\n Job Description: {item['body']}"
        
        self.feed(data, collection_name="job_openings", callback=callback)

    def feed(self, data, collection_name, callback):
        c = Chroma().client().get_or_create_collection(collection_name)
        ids = []
        documents = []
        metadata = []
        for i in data:
            ids.append(str(i['id']))
            documents.append(callback(i))
            metadata.append(i)
        
        c.upsert(ids=ids, metadatas=metadata, documents=documents)
 

