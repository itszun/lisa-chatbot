# Gunakan Python 3.10-slim sebagai parent image, ini efisien.
FROM python:3.10-slim

# Set working directory di dalam container
WORKDIR /usr/src/app

# Copy requirements.txt dulu untuk mengoptimalkan layer cache Docker
COPY ./requirements.txt ./

# Install semua package yang dibutuhkan
RUN pip install -r requirements.txt

# Copy sisa kode aplikasi ke dalam container
COPY . .

# Ini bagian terpenting. Perintah ini akan dijalankan
# saat container dihidupkan oleh Cloud Run.
# Pastikan Gunicorn bind ke port yang diberikan oleh Cloud Run ($PORT)
# dan gunakan 4 workers sesuai dengan preferensi lo.
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:$PORT", "wsgi:app"]