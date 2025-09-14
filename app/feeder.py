from vectordb import Chroma

class Feeder():
    def clean(self):
        Chroma().clean()
        return "clean"
        

    def pushTalentInfo(self, data):
        def callback(item): 
            return item['document']
        
        self.feed(data, collection_name="talent_pool", callback=callback)

    def pushCompanyInfo(self, data):
        def callback(item): 
            return item['document']

        self.feed(data, collection_name="company", callback=callback)

    def pushCandidate(self, data):
        def callback(item): 
            return item['document']
        
        self.feed(data, collection_name="candidates", callback=callback)

    def pushJobOpening(self, data):
        def callback(item): 
            return item['document']

        
        self.feed(data, collection_name="job_openings", callback=callback)

    def pushUserInfo(self, data):
        def callback(item): 
            return item['document']
        
        self.feed(data, collection_name="users", callback=callback)

    def feed(self, data, collection_name, callback):
        c = Chroma().client().get_or_create_collection(collection_name)
        ids = []
        documents = []
        metadata = []
        for i in data:
            ids.append(str(i['id']))
            documents.append(callback(i))

            if 'document' in i:
                del i['document']

            metadata.append(i)
        
        c.upsert(ids=ids, metadatas=metadata, documents=documents)
 

