# Asumsi: Lu install mongoengine

class ChatHistory(Document):
    # Field _id tidak perlu didefinisikan secara eksplisit di MongoEngine, dia otomatis.
    
    # 1. SessionId
    # Ini jelas adalah String unik.
    SessionId = StringField(required=True, unique=True)
    
    # 2. History
    # Karena isinya JSON (walau stringified), kita pakai StringField, 
    # TAPI kita harus modifikasi cara tampil di Flask-Admin.
    History = StringField(required=True) 
    
    # 3. Meta Data (Penting buat Query/Filter)
    # Penting: Tambahkan field `meta` untuk konfigurasi collection
    meta = {
        'collection': 'ChatHistory', # Pastikan nama collection-nya benar
        'indexes': [
            'SessionId' # Bikin index di SessionId biar query cepat (efisiensi!)
        ]
    }