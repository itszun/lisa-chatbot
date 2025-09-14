# app.py (Versi Final Tanpa Validasi Awal)
# -*- coding: utf-8 -*-
import os
import json
import time
import traceback
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI, RateLimitError
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from api_client import ensure_token, get_talent_detail, get_company_detail

# ======================================================================
# KONFIGURASI UMUM
# ======================================================================
MAX_HISTORY_MESSAGES = 50

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY belum diisi.")
client = OpenAI(api_key=OPENAI_API_KEY)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI belum diisi.")

API_LOG_DIR = os.getenv("API_LOG_DIR", "./logs")
os.makedirs(API_LOG_DIR, exist_ok=True)

# ======================================================================
# KONEKSI MONGODB
# ======================================================================
mongo_client = None
users_chats = None
try:
    mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    db = mongo_client.chatbot_db
    users_chats = db.users_chats
    print("Berhasil terhubung ke MongoDB.")
except Exception as e:
    print(f"Gagal terhubung ke MongoDB: {e}")
    mongo_client = None

# ======================================================================
# SYSTEM PROMPT (Tetap kompleks untuk alur kerja AI)
# ======================================================================
DEFAULT_SYSTEM_PROMPT = (
    # --- 1. IDENTITAS DAN ATURAN DASAR ---
    "Anda adalah asisten rekruter (recruiter assistant) profesional. Nama Anda Lisa. "
    "Tugas Anda adalah membantu pengguna mengelola data talent, kandidat, perusahaan, dan lowongan pekerjaan menggunakan tools yang tersedia. "
    "Selalu balas dalam Bahasa Indonesia yang sopan dan profesional."
    "Saat menampilkan daftar (seperti daftar talent), selalu gunakan format daftar bernomor (1., 2., 3., dst) dengan setiap item di baris baru agar rapi dan mudah dibaca."
    "PENTING: JANGAN PERNAH menampilkan data mentah JSON. Selalu interpretasikan dan sajikan dalam kalimat yang mudah dibaca."
    "JANGAN GUNAKAN FORMAT MARKDOWN seperti **bold** atau - untuk list. Gunakan kalimat biasa atau daftar bernomor."

    # --- BARU: ATURAN KEAMANAN DAN KONFIRMASI ---
    "ATURAN KESELAMATAN UTAMA: Untuk semua tindakan yang bersifat merusak atau mengubah data secara permanen (`delete_*`, `update_*`), Anda WAJIB meminta konfirmasi eksplisit dari pengguna sebelum menjalankan tool. "
    "Contoh konfirmasi untuk hapus: 'Apakah Anda yakin ingin menghapus data talent Budi Santoso? Tindakan ini tidak dapat dibatalkan.' "
    "Contoh konfirmasi untuk update: 'Saya akan mengubah posisi Budi menjadi Senior Developer. Apakah sudah benar?' "
    "HANYA lanjutkan eksekusi jika pengguna memberikan jawaban setuju (misal: 'Ya', 'Lanjutkan', 'Benar')."

    # --- BARU: ATURAN PENANGANAN HASIL TIDAK DITEMUKAN DAN AMBIGUITAS ---
    "ATURAN PENANGANAN ERROR: Jika sebuah tool (misalnya `get_talent_detail`) mengembalikan hasil 'tidak ditemukan' atau error, jangan hanya menampilkan pesan error teknis. Berikan jawaban yang ramah dan solutif. "
    "Contoh: 'Maaf, saya tidak dapat menemukan kandidat dengan nama Budi. Mungkin ada salah ketik? Anda bisa menggunakan tool `list_candidates` untuk melihat semua kandidat yang terdaftar.' "
    "ATURAN AMBIGUITAS NAMA: Jika pengguna meminta detail atau ingin mengubah data berdasarkan nama, dan tool menemukan lebih dari satu entitas dengan nama yang sama, beri tahu pengguna tentang ambiguitas ini dan minta ID spesifik untuk melanjutkan."

    # --- BARU: ATURAN UNTUK PERMINTAAN DI LUAR KONTEKS ---
    "ATURAN DI LUAR LINGKUP: Jika pengguna memberikan pertanyaan atau perintah yang sama sekali tidak berhubungan dengan tugas Anda (misal: bertanya tentang cuaca, berita, atau pengetahuan umum), jangan mencoba menjawabnya. Tolak dengan sopan dan arahkan kembali pengguna ke fungsi utama Anda. "
    "Contoh: 'Maaf, saya adalah asisten rekruter dan hanya bisa membantu Anda untuk mengelola data talenta, kandidat, perusahaan, dan lowongan kerja. Adakah yang bisa saya bantu terkait hal tersebut?'"

    # --- 2. PANDUAN PEMETAAN PERINTAH KE TOOLS (SANGAT PENTING) ---
    "Berikut adalah pemetaan pasti dari permintaan pengguna ke tool yang WAJIB Anda gunakan:"

    "A. Manajemen Talent:"
    "- Jika pengguna meminta daftar talent (misal: 'berikan list talent', 'tampilkan semua talent'), GUNAKAN tool `list_talent`."
    "- Jika pengguna ingin membuat talent baru (misal: 'buatkan talent baru', 'tambah talent Budi'), GUNAKAN tool `create_talent`. Tanyakan detail yang kurang jika perlu."
    "- Jika pengguna meminta detail seorang talent (misal: 'lihat detail talent Budi', 'profil talent T001'), GUNAKAN tool `get_talent_detail`."
    "- Jika pengguna ingin mengubah data talent (misal: 'update talent T001', 'ubah role Budi'), GUNAKAN tool `update_talent`."
    "- Jika pengguna ingin menghapus talent (misal: 'hapus talent Budi'), GUNAKAN tool `delete_talent`."

    "B. Manajemen Kandidat:"
    "- Jika pengguna meminta daftar kandidat (misal: 'berikan list kandidat'), GUNAKAN tool `list_candidates`."
    "- Jika pengguna ingin membuat kandidat baru (misal: 'buatkan kandidat', 'daftarkan kandidat baru'), GUNAKAN tool `create_candidate`."
    "- Jika pengguna meminta detail seorang kandidat (misal: 'detail kandidat C001'), GUNAKAN tool `get_candidate_detail`."
    "- Jika pengguna ingin mengubah data kandidat (misal: 'update kandidat C001'), GUNAKAN tool `update_candidate`."
    "- Jika pengguna ingin menghapus kandidat (misal: 'hapus kandidat Citra'), GUNAKAN tool `delete_candidate`."

    "C. Manajemen Perusahaan (Company):"
    "- Jika pengguna meminta daftar perusahaan (misal: 'list company', 'perusahaan apa saja yang terdaftar'), GUNAKAN tool `list_companies`."
    "- Jika pengguna ingin membuat perusahaan baru (misal: 'buatkan data company', 'tambah perusahaan ABC'), GUNAKAN tool `create_company`."
    "- Jika pengguna meminta detail sebuah perusahaan (misal: 'detail perusahaan ABC'), GUNAKAN tool `get_company_detail`."
    "- Jika pengguna ingin mengubah data perusahaan (misal: 'update company P001'), GUNAKAN tool `update_company`."
    "- Jika pengguna ingin menghapus perusahaan (misal: 'hapus perusahaan ABC'), GUNAKAN tool `delete_company`."
    "- Untuk properti perusahaan, gunakan tools `list_company_properties`, `get_company_property_detail`, `create_company_property`, `update_company_property`, `delete_company_property`."

    "D. Manajemen Lowongan Pekerjaan (Job Opening):"
    "- Jika pengguna meminta daftar lowongan (misal: 'berikan list job opening'), SELALU GUNAKAN tool `list_job_openings_enriched` agar nama perusahaan selalu ada."
    "- Jika pengguna ingin membuat lowongan baru (misal: 'buatkan job opening untuk posisi X'), GUNAKAN tool `create_job_opening`."
    "- Jika pengguna meminta detail lowongan (misal: 'detail lowongan J001'), GUNAKAN tool `get_job_opening_detail`."
    "- Jika pengguna ingin mengubah lowongan (misal: 'update job opening J001'), GUNAKAN tool `update_job_opening`."
    "- Jika pengguna ingin menghapus lowongan (misal: 'hapus lowongan J001'), GUNAKAN tool `delete_job_opening`."

    # --- 3. ALUR KERJA SPESIFIK (SOP) ---
    "Selain pemetaan di atas, ikuti SOP berikut untuk tugas yang lebih kompleks."

    "SOP (Standard Operating Procedure) SAAT MENCARI LOWONGAN PERUSAHAAN SPESIFIK: "
    "Ketika pengguna bertanya apakah sebuah perusahaan spesifik membuka lowongan, tugas Anda adalah sebagai berikut: "
    "LANGKAH 1: LANGSUNG gunakan tool `list_job_openings_enriched` dengan nama perusahaan sebagai parameter `search`. "
    "LANGKAH 2: JANGAN mencari ID perusahaan terlebih dahulu. "
    "LANGKAH 3: Jika hasilnya kosong, informasikan bahwa tidak ditemukan lowongan untuk perusahaan tersebut. "

    "SOP (Standard Operating Procedure) SAAT MENGHUBUNGI TALENT: "
    "Saat pengguna meminta untuk mengirim pesan ke seorang talent dari sebuah perusahaan, IKUTI LANGKAH-LANGKAH BERIKUT SECARA BERURUTAN: "
    "LANGKAH 1: IDENTIFIKASI INFORMASI (NAMA TALENT, ID TALENT, NAMA PERUSAHAAN PENGIRIM) manfaatkan retrive_data tools"
    "LANGKAH 2: ANALISIS & BUAT DRAF PESAN yang spesifik merujuk pada lowongan yang ditemukan di Langkah 1. "
    "LANGKAH 3: MINTA KONFIRMASI pengguna (gunakan tool `prepare_talent_message` jika ada, atau tanyakan langsung). "
    "LANGKAH 4: TUNGGU PERSETUJUAN (misal: 'Ya' atau 'Kirim'). "
    "LANGKAH 5: EKSEKUSI. Setelah disetujui, GUNAKAN tool `initiate_contact`. Pastikan Anda menyertakan `user_id`, `talent_id`, `talent_name`, `job_opening_id` yang relevan, dan `initial_message`."

    "SOP (Standard Operating Procedure) SAAT MENGIRIM PENAWARAN KERJA (JOB OFFER): "
    "Saat pengguna meminta untuk 'mengirim penawaran' atau 'memberikan offering letter', IKUTI LANGKAH-LANGKAH BERIKUT: "
    "LANGKAH 1: IDENTIFIKASI KANDIDAT. "
    "LANGKAH 2: KUMPULKAN DETAIL TAWARAN (coba `get_offer_details` dulu, jika gagal tanyakan pengguna). "
    "LANGKAH 3: BUAT DRAF SURAT TAWARAN menggunakan template yang sudah disediakan. "
    "--- TEMPLATE SURAT TAWARAN ---"
    "Selamat pagi, Pak/Bu [Nama Kandidat],\n\n"
    "Terima kasih banyak atas waktu yang telah Anda luangkan untuk wawancara di [Nama Perusahaan] beberapa hari lalu. Kami sangat terkesan dengan pengalaman dan keterampilan Anda yang relevan dengan posisi [Nama Posisi] yang kami tawarkan.\n\n"
    "Setelah melalui proses evaluasi yang seksama, kami senang untuk menawarkan Anda posisi [Nama Posisi] di [Nama Perusahaan]. Berikut adalah detail terkait tawaran kami:\n\n"
    "- Gaji: Rp [Jumlah Gaji] per bulan\n"
    "- Tunjangan: [Sebutkan tunjangan yang diberikan]\n"
    "- Waktu kerja: [Jadwal kerja, misalnya Senin-Jumat, 09.00-17.00]\n"
    "- Benefit lainnya: [Sebutkan benefit lain seperti cuti, dll.]\n\n"
    "Kami percaya bahwa Anda akan menjadi aset berharga bagi tim kami dan kami sangat berharap Anda dapat bergabung dengan kami. Silakan konfirmasi jika Anda menerima tawaran ini.\n\n"
    "Terima kasih sekali lagi atas perhatian Anda.\n\n"
    "Salam,\n"
    "[Nama Pengirim]\n"
    "Tim HR [Nama Perusahaan]\n"
    "[Kontak yang bisa dihubungi]"
    "--- AKHIR TEMPLATE ---"
    "LANGKAH 4: MINTA KONFIRMASI pengguna (gunakan `prepare_talent_message` jika ada, atau tanyakan langsung). "
    "LANGKAH 5: EKSEKUSI. Setelah pengguna setuju, **gunakan tool `initiate_contact`** untuk mendaftarkan kandidat dan 'mengirim' surat."
)

# ======================================================================
# UTILITAS
# ======================================================================
def parse_user(user_field: str) -> Tuple[str, str]:
    if not user_field or "@" not in user_field:
        raise ValueError("Format user harus 'userid@nama'.")
    userid, name = user_field.split("@", 1)
    userid = userid.strip()
    name = name.strip()
    if not userid or not name:
        raise ValueError("userid atau nama tidak boleh kosong.")
    return userid, name

def get_or_create_chat_doc(name: str) -> dict:
    # --- PERBAIKAN DI SINI ---
    # Fungsi ini sekarang HANYA menerima 'name'
    doc = users_chats.find_one({"name": name})
    if doc:
        return doc
    new_doc = {"name": name, "sessions": []}
    users_chats.insert_one(new_doc)
    return users_chats.find_one({"name": name})

def find_session(doc: dict, session_id: str) -> Optional[dict]:
    for s in (doc.get("sessions") or []):
        if s.get("session_id") == session_id:
            return s
    return None

def upsert_session_messages(name: str, session_id: str, messages: List[dict]) -> None:
    users_chats.update_one(
        {"name": name, "sessions.session_id": session_id},
        {"$set": {"sessions.$.messages": messages}}
    )

def append_session(name: str, session_id: str, created_at: datetime, messages: List[dict], title: str) -> None:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    users_chats.update_one(
        {"name": name},
        {"$push": {"sessions": {
            "session_id": session_id, "created_at": created_at,
            "title": title, "messages": messages
        }}}
    )

def _extract_bearer_token(req) -> str:
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""
   
# ======================================================================
# IMPORT TOOLS + INJEKSI HELPER
# ======================================================================
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS, set_helpers
set_helpers(get_or_create_chat_doc, append_session, DEFAULT_SYSTEM_PROMPT)

# ======================================================================
# ROUTES (VALIDASI DIHAPUS)
# ======================================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    try:
        incoming_token = _extract_bearer_token(request)
        if incoming_token: ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (request.args.get("user") or "").strip()
    try:
        name = user_field
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    doc = get_or_create_chat_doc(name=name)
    sessions = []
    for s in doc.get("sessions", []):
        created = s.get("created_at")
        created_str = created.isoformat() if hasattr(created, "isoformat") else created
        sessions.append({
            "session_id": s.get("session_id"),
            "title": s.get("title", "Percakapan Baru"),
            "created_at": created_str,
            "messages_count": len(s.get("messages") or [])
        })
    sessions.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jsonify({"name": name, "sessions": sessions})

@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json(force=True)
    try:
        incoming_token = _extract_bearer_token(request)
        if incoming_token: ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (data.get("user") or "").strip()
    system_prompt = data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    # Sapaan disederhanakan karena tidak ada user_type
    personalized_greeting = f"Hai {name}, adakah yang bisa saya bantu?"
    
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    _ = get_or_create_chat_doc(name=name)
    new_sid = str(uuid4())
    created_at = datetime.now(timezone.utc)
    default_title = "Percakapan Baru"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": personalized_greeting},
    ]
    append_session(
        userid=userid,
        session_id=new_sid,
        created_at=created_at,
        messages=messages,
        title=default_title
    )
    return jsonify({
        "name": name,
        "session_id": new_sid,
        "title": default_title,
        "created_at": created_at.isoformat()
    })
 
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    try:
        incoming_token = _extract_bearer_token(request)
        if incoming_token: ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_name = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    if not user_name or not user_msg:
        return jsonify({"error": "Input tidak lengkap (membutuhkan user dan message)."}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    is_new_session = not session_id
    messages_full: List[dict] = []
    
    if is_new_session:
        session_id = str(uuid4())
        # --- PERBAIKAN DI SINI ---
        # Panggilan ini sekarang cocok dengan definisinya
        get_or_create_chat_doc(name=user_name)
        messages_full = [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ]
    else:
        doc = users_chats.find_one({"name": user_name})
        if not doc:
            return jsonify({"error": f"User '{user_name}' belum memulai percakapan."}), 404
        sess = find_session(doc, session_id)
        if not sess:
            return jsonify({"error": f"session_id '{session_id}' tidak ditemukan."}), 404
        messages_full = sess.get("messages", [])
        messages_full.append({"role": "user", "content": user_msg})

    def _ctx_slice(msgs: List[dict]) -> List[dict]:
        if len(msgs) > MAX_HISTORY_MESSAGES:
            return [msgs[0]] + msgs[-MAX_HISTORY_MESSAGES:]
        return msgs

    tool_runs = []
    final_text = ""
    try:
        ctx_messages = _ctx_slice(messages_full)
        first = client.chat.completions.create(
            model="gpt-4o", messages=ctx_messages, tools=TOOLS_SPEC,
            tool_choice="auto", temperature=0.2
        )
        resp_msg = first.choices[0].message
        message_dict = resp_msg.model_dump()
        messages_full.append(message_dict)
        tool_calls = resp_msg.tool_calls

        if tool_calls:
            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                out = AVAILABLE_FUNCS[fname](**fargs)
                result_json = json.dumps(out, ensure_ascii=False)
                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages_full.append({"role": "tool", "tool_call_id": tc.id, "name": fname, "content": result_json})
            
            second = client.chat.completions.create(model="gpt-4o", messages=_ctx_slice(messages_full), temperature=0.2)
            final_text = second.choices[0].message.content or ""
        else:
            final_text = resp_msg.content or ""
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "detail": str(e)}), 500

    messages_full.append({"role": "assistant", "content": final_text})

    if is_new_session:
        title = (client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": f"Buat judul singkat (maksimal 5 kata) untuk percakapan yang diawali dengan: '{user_msg}'"}],
            temperature=0.2, max_tokens=20
        ).choices[0].message.content or "Percakapan Baru").strip().replace('"', '')
        append_session(name=user_name, session_id=session_id, created_at=datetime.now(timezone.utc), messages=messages_full, title=title)
    else:
        upsert_session_messages(name=user_name, session_id=session_id, messages=messages_full)
    
    response_data = {
        "user": user_name,
        "session_id": session_id,
        "answer": final_text,
        "tool_runs": tool_runs
    }
    if is_new_session:
        response_data["new_session_id"] = session_id

    return jsonify(response_data)

@app.get("/api/session/messages")
def get_session_messages():
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401
    user_field = (request.args.get("user") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    if not user_field or not session_id:
        return jsonify({"error": "Parameter 'user' dan 'session_id' wajib diisi."}), 400
    try:
        name = user_field
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500
    doc = users_chats.find_one({"name": name})
    if not doc:
        return jsonify({"error": f"Nama '{name}' belum terdaftar."}), 404
    sess = find_session(doc, session_id)
    if not sess:
        return jsonify({"error": f"session_id '{session_id}' tidak ditemukan untuk nama '{name}'."}), 404
    msgs = sess.get("messages", []) or []
    return jsonify({
        "name": doc.get("name", name),
        "session_id": session_id,
        "messages": msgs
    })


from feeder import Feeder
@app.post("/api/feeder/talents")
def feed_talent():
    payload = request.json
    Feeder().pushTalentInfo(payload['data'])

    return jsonify({
        "status": "success"
    })

@app.post("/api/feeder/companies")
def feed_job_company():
    payload = request.json
    Feeder().pushCompanyInfo(payload['data'])

    return jsonify({
        "status": "success"
    })

@app.post("/api/feeder/candidates")
def feed_job_candidate():
    payload = request.json
    Feeder().pushCandidate(payload['data'])

    return jsonify({
        "status": "success"
    })

@app.post("/api/feeder/job_openings")
def feed_job_opening():
    payload = request.json
    Feeder().pushJobOpening(payload['data'])

    return jsonify({
        "status": "success"
    })


@app.post("/api/feeder/users")
def feed_job_user():
    payload = request.json
    Feeder().pushUserInfo(payload['data'])

    return jsonify({
        "status": "success"
    })


# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True, use_reloader=False, threaded=True)
