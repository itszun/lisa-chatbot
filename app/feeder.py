from vectordb import Chroma

class Feeder():

    def pushTalentInfo(self, data):
        def callback(item): 
            print(item)
            return f"Nama Talent: {item['name']}\nPosition: {item['position']}\nDeskripsi: {item['summary']} \nSkills: {item['skills']} \nEducations: {item['educations']}"
        
        self.feed(data, collection_name="talent_pool", callback=callback)

    def pushCompanyInfo(self, data):
        def callback(item): 
            return f"Nama Company: {item['name']}\nAbout Company: {item['description']}"
        
        self.feed(data, collection_name="company", callback=callback)

    def pushCandidate(self, data):
        def callback(item): 
            return f"Lowongan Kerja: {item['job_opening.title']}\nTalent Name: {item['talent.name']}"
        
        self.feed(data, collection_name="candidates", callback=callback)

    def pushJobOpening(self, data):
        def callback(item): 
            return f"Lowongan Kerja {item['title']}\n Job Description: {item['body']}"
        
        self.feed(data, collection_name="job_openings", callback=callback)

    def pushUserInfo(self, data):
        def callback(item): 
            return f"User ID {item['id']}\n User Name: {item['name']} \n "
        
        self.feed(data, collection_name="users", callback=callback)

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
 

