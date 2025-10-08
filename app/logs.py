import logging
import os

# 📄 Definisikan path log file
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

# Pastikan folder logs ada
os.makedirs(LOG_DIR, exist_ok=True)

# Konfigurasi Logging standar Python
def setup_logging():
    # Buat formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    
    # Buat file handler
    file_handler = logging.FileHandler(LOG_FILE, mode='a') # mode='a' untuk append
    file_handler.setFormatter(formatter)
    
    # Ambil root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Set level minimum
    
    # Tambahkan handler ke logger
    if not logger.handlers: # Mencegah duplikasi handler jika dipanggil berkali-kali
        logger.addHandler(file_handler)
