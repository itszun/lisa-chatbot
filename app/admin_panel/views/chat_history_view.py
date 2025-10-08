from flask_admin.contrib.pymongo import ModelView

class ChatHistoryView(ModelView):
    # --- 1. Konfigurasi Tampilan List (Tabel) ---
    # Kita hanya perlu menampilkan _id dan SessionId di tabel utama biar gak lemot
    column_list = ('SessionId', '_id') 
    
    # Teks yang ditampilkan di header kolom
    column_labels = {
        'SessionId': 'ID Sesi Chat',
        '_id': 'MongoDB OID'
    }
    
    # --- 2. Konfigurasi Tampilan Detail/Form Edit ---
    
    # Field mana saja yang boleh diedit. 
    # Sebaiknya HINDARI mengedit 'History' langsung.
    form_columns = ('SessionId', 'History')
    
    # Optional: Kustomisasi Form Field untuk History
    # Kalau lu mau tampilan yang lebih lebar, lu bisa custom widget-nya.
    # form_args = dict(
    #     History=dict(widget=TextArea(rows=20, cols=80)) 
    # )

    # --- 3. Override Template (Solusi Paling Cerdas) ---
    # Paling baik: Disable 'History' di view EDIT. 
    # Kalau mau lihat History, user harus VIEW detail, BUKAN EDIT.
    # Editing field History secara manual itu RENTAN ERROR!
    
    # form_excluded_columns = ['History'] # Uncomment ini jika lu mutlak melarang edit History.
    
    # Contoh kolom yang bisa dicari (searchable)
    column_searchable_list = ('SessionId',)