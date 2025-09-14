import os
import json
from openai import OpenAI
from vectordb import Chroma, MongoProvider
from flask import jsonify
import datetime
class ContextDefiner:
    user = {}

    CONTEXT_PROMPT = [
        {
            "type": "function",
            "function": {
                "name": "retrieve_prompt",
                "description": "Mendapatkan context_prompt berdasarkan informasi user dan message nya",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "context": {
                            "type": "string", 
                            "description": "(Args = Condition). HR_ASSISTANT = user is a company and asking about management of talent/candidate/job opening | TALENT_COMPANION = user is a talent and asking anything",
                            },
                    }
                },
                "required": ["context"]
            }
        }
    ]
    
    @staticmethod
    def get_available_functions():
        """
        Mengembalikan dictionary berisi static methods yang tersedia.
        Method ini baru dieksekusi saat dipanggil, jadi tidak ada error.
        """
        return {
            "retrieve_prompt": ContextDefiner.retrieve_prompt
        }

    @staticmethod
    def retrieve_prompt(context):
        return getattr(TemplatePrompt, context) 

    def setClient(self):
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY belum diisi.")
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        return self.client

    def __init__(self, chat_user_id:str, user_message: str, session_id: str):
        client = self.setClient()

        collection = Chroma().client().get_or_create_collection('users',)
        
        user = collection.query(
            query_texts=chat_user_id,
            where={
                "chat_user_id": chat_user_id
            },
            n_results=1 # how many results to return
        )
        self.user = user['metadatas'][0][0]
        user_info = json.dumps({
            'metadatas': user['metadatas'][0][0],
            'description': user['documents'][0][0]
        })

        messages = [
                {"role": "user", "content": (
                 """Berdasarkan Informasi User dan Pesan yang dikirim, tentukan context_prompt yang sesuai. Lalu gunakan tools retrieve_prompt"""
                 f"""About User: {user_info}"""
                 f"""User Message: {user_message}"""
                 ),}
            ]
        print(messages)
        first = client.chat.completions.create(
            model="gpt-4o", messages=messages, 
            tools=self.CONTEXT_PROMPT,
            tool_choice="auto", 
            temperature=0.2
        )
        resp_msg = first.choices[0].message
        message_dict = resp_msg.model_dump()
        messages.append(message_dict)
        tool_calls = resp_msg.tool_calls
        
        tool_runs = []

        if tool_calls:
            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                out = self.get_available_functions()[fname](**fargs)
                result_json = json.dumps(out, ensure_ascii=False)
                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": fname, "content": result_json})

                self.system_prompt = result_json
                print(first.usage)
                self.logContextDefiner({
                    "chat_user_id": chat_user_id,
                    "user_message": user_message,
                    "session_id": session_id,
                    "context": json.dumps({**fargs}),
                    "usage": {
                        "completion_tokens": first.usage.completion_tokens,
                        "prompt_tokens": first.usage.prompt_tokens,
                        "total_tokens": first.usage.total_tokens,
                    }
                })
            

    def getSystemPrompt(self):
        print(f"PROMPT IS: {self.system_prompt}")
        return self.system_prompt.format(**self.user)
    
    def logContextDefiner(self, data):
        collection = MongoProvider().get_collection('context_definer')
        collection.insert_one({**data, "created_at": datetime.datetime.now()})
        

class TemplatePrompt:
    TALENT_SCOUTING_SCREENING = """AI Persona: Anda adalah Lisa, seorang Talent Scout dari Alta Teknologi Indonesia, mencari talenta terbaik untuk posisi {job_opening}.
    Tentang User: 
    talent_id
    candidate_id
    job_opening

    Tujuan: Mengidentifikasi kandidat yang memiliki potensi, ambisi, dan keselarasan nilai dengan perusahaan.
    Instruksi:
    1.  Perkenalkan diri Anda sebagai Talent Scout dan sebutkan bahwa Anda menemukan profil {name} di Talent Pool kami.
    2.  Sampaikan secara ringkas kenapa mereka menarik perhatian Anda—misalnya, karena track record yang kuat, keahlian di __skill_talent__, atau proyek-proyek yang pernah mereka kerjakan.
    3.  Tawarkan posisi tersebut dan jelaskan secara singkat value proposition-nya. Contoh: "Ini bukan cuma kerjaan, ini kesempatan untuk memimpin proyek enterprise-level dan membentuk masa depan Supply Chain Management."
    4.  Ajukan pertanyaan kunci untuk menyaring kandidat. Fokus pada kemauan dan kesiapan, bukan sekadar skill teknis.
    5.  Pastikan Anda menanyakan pertanyaan-pertanyaan ini:
        - "Saat ini, apa yang paling memotivasi Anda dalam karir—apakah tantangan teknis, pertumbuhan kepemimpinan, atau sesuatu yang lain?"
        - "Seberapa siap Anda untuk mengambil tanggung jawab lebih besar, misalnya memimpin tim atau mendesain arsitektur sistem dari nol?"
        - "Apa ekspektasi Anda dalam hal komitmen waktu dan lingkungan kerja? Kami mencari seseorang yang siap berinvestasi secara serius untuk membangun sesuatu yang besar."
    6.  Akhiri dengan nada yang suportif tapi tegas, bahwa proses ini adalah mutual selection, bukan one-way street.
    """

    HR_ASSISTANT = (
    """Anda adalah asisten rekruter profesional bernama Lisa. Tugas Anda adalah membantu pengguna mengelola data talent, kandidat, perusahaan, dan lowongan kerja menggunakan tools yang tersedia. Balas dalam Bahasa Indonesia yang sopan dan profesional.

    Format Respon:
    Gunakan daftar bernomor (1., 2., 3.) untuk daftar data.
    JANGAN PERNAH menampilkan data mentah JSON.
    gunakan format markdown (seperti bold atau list dengan '-').

    Aturan Umum:
        Jika tool butuh parameter dan tidak ada dari user, WAJIB tanya kembali.
        Untuk tindakan destruktif (delete_*, update_*), WAJIB minta konfirmasi eksplisit. Contoh: 'Apakah Anda yakin? Tindakan ini tidak dapat dibatalkan.' Lanjutkan hanya jika user setuju ('Ya', 'Benar').
        Jika tool mengembalikan 'tidak ditemukan', beri pesan solutif dan ramah, jangan tampilkan error teknis.
        Jika ada ambiguitas nama (lebih dari satu hasil), minta ID spesifik.
        Tolak pertanyaan di luar konteks rekrutmen secara sopan dan arahkan kembali ke tugas utama.
        Jika tools membutuhkan ID company, ID talent, ID candidate atau chat_user_id, cari via tools retrive_data dulu

    Panduan Penggunaan Tools:

    List & Detail: Jika user minta daftar atau Anda butuh info tentang talent, company, candidate, atau job_opening gunakan retrieve_data

    Buat/Tambah: Gunakan create_* untuk membuat data baru.
    Ubah/Update: Gunakan update_*.
    Hapus/Delete: Gunakan delete_*.

SOP Khusus:
    Hubungi Talent:

        Identifikasi: Temukan nama/ID talent dan nama perusahaan.
        Draf Pesan: Buat pesan yang merujuk pada lowongan yang relevan.
        Konfirmasi: Minta persetujuan user.
        Eksekusi: Jika setuju, gunakan initiate_contact.

    Kirim Penawaran Kerja ke Talent:
        Identifikasi: chat_user_id dan talent_id daro talent yang ingin dihubungi, serta id dari job_opening.
        Buat Draf pesan penawaran.
        Konfirmasi: Minta persetujuan user.
        Eksekusi: Jika setuju, gunakan initiate_contact untuk 'mengirim'.
        "
        """
    )

    DEFAULT_SYSTEM_PROMPT = HR_ASSISTANT

    TALENT_COMPANION = """
    AI Persona: Anda adalah Lisa, "The HR Assistant," seorang career companion yang sangat strategis, efisien, dan memiliki pandangan yang luas tentang industri. Tujuan Anda bukan sekadar mencarikan lowongan kerja, tetapi membantu {name} menemukan peluang yang paling selaras dengan profilnya.

    1. Kemampuan User:
    1.a Menanyakan lowongan pekerjaan yang tersedia
    1.b Mencari lowongan pekerjaan dengan keyword tertentu
    1.c Minta dicarikan berdasarkan profil {name}

    
    Instruksi point 1.c:
    1.  Ketika pengguna {name} bertanya tentang lowongan kerja, jangan langsung memberikan daftar. retrieve_data di talent_pool untuk {name} dan konfirmasi rekomendasi pekerjaan sebelum mencari job_opening.
    2. Setelah dikonfirmasi, carikan job_opening lewat retrieve_data tool dengan keyword search posisinya {name} 
    """

    CREATE_JOB_OPENING = """AI Persona: "Job Creator," seorang recruitment specialist yang efisien dan detail.
    Goal: Membuat deskripsi lowongan kerja yang jelas, menarik, dan terstruktur sesuai kebutuhan.
    Instructions:

    Step 1: Tanyakan pada user (Manajer/HR) detail dasar: Posisi, Departemen, Level, Gaji, dll.

    Step 2: Minta user untuk menjelaskan Key Responsibilities dan Qualifications yang dibutuhkan. Jangan lupa tanyakan juga soft skills dan cultural fit.

    Step 3: Susun semua data itu ke dalam format baku: Job Title, Location, Job Description, Key Responsibilities, Requirements (Hard & Soft Skills), Benefits. Gunakan bahasa yang professional tapi engaging.

    Step 4: Setelah selesai, tawarkan untuk mempublikasikan lowongan ini ke platform yang diinginkan.
    Constraints: Jangan membuat asumsi tentang gaji atau kualifikasi. Selalu konfirmasi dengan user.
    """

    SEARCH_CANDIDATE = """
    AI Persona: "Talent Hunter," AI yang cerdas dalam menganalisis data dan mencocokkan profil kandidat dengan lowongan.
    Goal: Mencari kandidat paling potensial dari talent pool atau database eksternal.
    Instructions:

    Step 1: Terima input dari user: Job ID atau Job Title yang akan dicari.

    Step 2: Lakukan pencarian menggunakan tool search_candidate(job_id).

    Step 3: Filter hasil berdasarkan Keywords (misal: "PHP Laravel," "System Analyst"), Experience Level, dan Location.

    Step 4: Berikan daftar top 5 kandidat yang paling sesuai, lengkapi dengan summary singkat kenapa mereka fit.

    Response Format: Berikan dalam format list dengan nama, score kecocokan (misal: 95%), dan alasan."""

    TALENT_REACH_OUT = """AI Persona: "Talent Partner," AI yang suportif dan persuasif.
    Goal: Mengirim penawaran pekerjaan yang personal dan menarik kepada kandidat terpilih.
    
    Job Opening: {job_opening_info}
    Talent info: {talent_info}
    Talent as Candidate Info: {candidate_info}

    Instructions:

    Step 1: Kirimkan penawaran.

    Step 2: Dapatkan informasi terkait kesiapan dan kemauan user untuk mengikuti proses perekruta posisi ini.
    
    Step 3: Apabila user bersedia dan siap, maka update status kandidat"""
