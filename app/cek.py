import os
from dotenv import load_dotenv

# Coba muat file .env
is_loaded = load_dotenv()

if is_loaded:
    print("✅ File .env berhasil ditemukan dan dimuat.")
else:
    print("🔴 PENTING: File .env TIDAK ditemukan di folder ini.")

# Ambil dan cetak variabel database
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT")

print("-" * 30)
print(f"Host dari .env: [{db_host}]")
print(f"User dari .env: [{db_user}]")
print(f"Database dari .env: [{db_name}]")
print(f"Port dari .env: [{db_port}]")
print("-" * 30)