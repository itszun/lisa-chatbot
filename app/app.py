# app.py
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
    users_chats.create_index("name", unique=True)
    print("Berhasil terhubung ke MongoDB dan memastikan index unik pada 'name'.")
except Exception as e:
    print(f"Gagal terhubung ke MongoDB: {e}")
    mongo_client = None

# ======================================================================
# SYSTEM PROMPT FINAL
# ======================================================================

DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten rekruter (recruiter assistant) profesional. Nama Anda Lisa. "
    "Tugas Anda adalah membantu pengguna mengelola data talent, kandidat, dan perusahaan. "
    "Gunakan tools yang tersedia untuk melakukan operasi CRUD. "
    "Selalu balas dalam Bahasa Indonesia yang sopan dan profesional."
    "Saat menampilkan daftar (seperti daftar talent), selalu gunakan format daftar bernomor (1., 2., 3., dst) dengan setiap item di baris baru agar rapi dan mudah dibaca."

    # SOP untuk MENCARI LOWONGAN
    "SOP (Standard Operating Procedure) SAAT MENCARI LOWONGAN PERUSAHAAN SPESIFIK: "
    "Ketika pengguna bertanya apakah sebuah perusahaan spesifik membuka lowongan, tugas Anda adalah sebagai berikut: "
    "LANGKAH 1: LANGSUNG gunakan tool `list_job_openings_enriched` dengan nama perusahaan sebagai parameter `search`. "
    "LANGKAH 2: JANGAN mencari ID perusahaan terlebih dahulu. "
    "LANGKAH 3: Jika hasilnya kosong, informasikan bahwa tidak ditemukan lowongan untuk perusahaan tersebut. "

    # SOP untuk MENGHUBUNGI TALENT
    "SOP (Standard Operating Procedure) SAAT MENGHUBUNGI TALENT: "
    "Saat pengguna meminta untuk mengirim pesan ke seorang talent dari sebuah perusahaan, IKUTI LANGKAH-LANGKAH BERIKUT SECARA BERURUTAN: "
    "LANGKAH 1: IDENTIFIKASI INFORMASI (NAMA TALENT, ID TALENT, NAMA PERUSAHAAN PENGIRIM). "
    "LANGKAH 2: CARI LOWONGAN RELEVAN menggunakan `list_job_openings_enriched`. Sangat penting untuk mendapatkan `job_opening_id` dari langkah ini. Jika ada beberapa pilihan, tanyakan kepada pengguna mana yang akan digunakan. "
    "LANGKAH 3: CARI KEAHLIAN TALENT menggunakan `get_talent_detail`. "
    "LANGKAH 4: ANALISIS & BUAT DRAF PESAN yang spesifik merujuk pada lowongan yang ditemukan di Langkah 2. "
    "LANGKAH 5: MINTA KONFIRMASI pengguna menggunakan `prepare_talent_message`. "
    "LANGKAH 6: TUNGGU PERSETUJUAN (misal: 'Ya' atau 'Kirim'). "
    "LANGKAH 7: EKSEKUSI. Setelah disetujui, gunakan tool `initiate_contact`. **SEBELUM MEMANGGIL TOOL INI, WAJIB PASTIKAN ANDA SUDAH MEMILIKI `job_opening_id` DARI LANGKAH 2.** Jika Anda belum memilikinya, Anda harus menjalankan Langkah 2 terlebih dahulu. Sertakan `talent_id`, `talent_name`, `job_opening_id`, dan `initial_message` dalam panggilan tool."

    # SOP untuk JOB OFFER
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
    "LANGKAH 4: MINTA KONFIRMASI pengguna menggunakan `prepare_talent_message`. "
    "LANGKAH 5: EKSEKUSI. Setelah pengguna setuju, **gunakan tool `initiate_contact`** untuk mendaftarkan kandidat dan 'mengirim' surat."

    # ATURAN PENTING LAINNYA
    "ATURAN PENTING: "
    "1. JANGAN PERNAH menampilkan data mentah JSON. Selalu interpretasikan dan sajikan dalam kalimat yang mudah dibaca. "
    "2. JANGAN GUNAKAN FORMAT MARKDOWN. Gunakan kalimat lengkap atau daftar bernomor. "
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

def validate_user_identity(userid: str, name: str) -> Tuple[Optional[str], Optional[Dict]]:
    try:
        talent_id = int(userid)
        talent_data = get_talent_detail(talent_id=talent_id)
        if talent_data and (talent_data.get("name") or "").lower() == name.lower():
            return "talent", talent_data
    except (ValueError, RuntimeError, PermissionError):
        pass
    try:
        company_id = int(userid)
        company_data = get_company_detail(company_id=company_id)
        if company_data and (company_data.get("name") or "").lower() == name.lower():
            return "company", company_data
    except (ValueError, RuntimeError, PermissionError):
        pass
    return None, None

def get_or_create_name_doc(name: str, userid: Optional[str] = None) -> dict:
    doc = users_chats.find_one({"name": name})
    if doc:
        if userid and userid not in (doc.get("users") or []):
            users_chats.update_one({"_id": doc["_id"]}, {"$addToSet": {"users": userid}})
            doc = users_chats.find_one({"_id": doc["_id"]})
        return doc
    new_doc = {"name": name, "users": [userid] if userid else [], "sessions": []}
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

def update_session_title(name: str, session_id: str, new_title: str) -> None:
    users_chats.update_one(
        {"name": name, "sessions.session_id": session_id},
        {"$set": {"sessions.$.title": new_title}}
    )

def append_session(name: str, session_id: str, created_at: datetime, messages: List[dict], title: str) -> None:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    users_chats.update_one(
        {"name": name},
        {"$push": {"sessions": {
            "session_id": session_id,
            "created_at": created_at,
            "title": title,
            "messages": messages
        }}}
    )

def _log_tool_call(userid: str, name: str, session_id: str, function_name: str, args: dict, result: Any):
    try:
        now = datetime.now()
        timestamp_safe = now.strftime("%Y-%m-%d_%H-%M-%S")
        short_sid = session_id[:8]
        log_filename = f"{timestamp_safe}__{function_name}_{short_sid}.log"
        log_path = os.path.join(API_LOG_DIR, log_filename)
        args_str = json.dumps(args, ensure_ascii=False)
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        header_line = f"[{now.strftime('%Y/%m/%d %H:%M:%S')}] [UserID: {userid}, Name: {name}, Session: {session_id}]"
        log_entry = (
            f"{header_line}\n"
            f"Fungsi yang dipanggil: {function_name}({args_str})\n"
            f"Hasil: {result_str}\n"
        )
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"!! Gagal menulis log: {e}")

def _extract_bearer_token(req) -> str:
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    x = (req.headers.get("X-Api-Token") or "").strip()
    if x:
        return x
    try:
        data = req.get_json(silent=True) or {}
        if isinstance(data, dict):
            t = (data.get("token") or "").strip()
            if t:
                return t
    except Exception:
        pass
    return ""

# ======================================================================
# IMPORT TOOLS + INJEKSI HELPER
# ======================================================================
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS, set_helpers
set_helpers(get_or_create_name_doc, append_session, DEFAULT_SYSTEM_PROMPT)

# ======================================================================
# ROUTES
# ======================================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401
    user_field = (request.args.get("user") or "").strip()
    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    user_type, _ = validate_user_identity(userid, name)
    if not user_type:
        return jsonify({"error": "AKSES DITOLAK: Pengguna tidak terdaftar di database."}), 404
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500
    doc = get_or_create_name_doc(name=name, userid=userid)
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
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401
    user_field = (data.get("user") or "").strip()
    system_prompt = data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    user_type, _ = validate_user_identity(userid, name)
    if not user_type:
        return jsonify({"error": "AKSES DITOLAK: Pengguna tidak terdaftar di database."}), 404
    personalized_greeting = f"Hai {user_type.capitalize()} {name}, adakah yang bisa saya bantu?"
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500
    _ = get_or_create_name_doc(name=name, userid=userid)
    new_sid = str(uuid4())
    created_at = datetime.now(timezone.utc)
    default_title = "Percakapan Baru"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": personalized_greeting},
    ]
    append_session(
        name=name,
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
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401
    user_field = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    if not user_field or not user_msg or not session_id:
        return jsonify({"error": "Input tidak lengkap (membutuhkan user, message, session_id)."}), 400
    try:
        userid, name = parse_user(user_field)
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
    messages_full = sess.get("messages", [])
    messages_full.append({"role": "user", "content": user_msg, "timestamp": datetime.now(timezone.utc).isoformat()})

    def _ctx_slice(msgs: List[dict]) -> List[dict]:
        if len(msgs) > MAX_HISTORY_MESSAGES:
            return [msgs[0]] + msgs[-MAX_HISTORY_MESSAGES:]
        return msgs

    tool_runs = []
    final_text = ""
    for attempt in range(3):
        try:
            ctx_messages = _ctx_slice(messages_full)
            first = client.chat.completions.create(
                model="gpt-4o",
                messages=ctx_messages,
                tools=TOOLS_SPEC,
                tool_choice="auto",
                temperature=0.2
            )
            resp_msg = first.choices[0].message
            message_dict = resp_msg.model_dump()
            messages_full.append(message_dict)
            tool_calls = resp_msg.tool_calls

            if tool_calls:
                for tc in tool_calls:
                    fname = tc.function.name
                    try:
                        fargs = json.loads(tc.function.arguments or "{}")
                        out = AVAILABLE_FUNCS[fname](**fargs)
                        _log_tool_call(userid, name, session_id, fname, fargs, out)
                        result_json = json.dumps(out, ensure_ascii=False)
                    except Exception as fn_err:
                        err_obj = {"error": str(fn_err)}
                        _log_tool_call(userid, name, session_id, fname, fargs, err_obj)
                        result_json = json.dumps(err_obj, ensure_ascii=False)
                    tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                    messages_full.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": result_json,
                    })
                
                ctx_messages_2 = _ctx_slice(messages_full)
                second = client.chat.completions.create(
                    model="gpt-4o",
                    messages=ctx_messages_2,
                    temperature=0.2
                )
                final_text = second.choices[0].message.content or ""
            else:
                final_text = resp_msg.content or ""
            break
        except RateLimitError as e:
            if attempt + 1 == 3: return jsonify({"error": "Server sibuk, coba lagi nanti.", "detail": str(e)}), 429
            time.sleep(5)
        except Exception as e:
            print("\n\n--- TRACEBACK ERROR ---")
            traceback.print_exc()
            print("--- END TRACEBACK ---\n\n")
            return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "detail": str(e)}), 500

    messages_full.append({"role": "assistant", "content": final_text, "timestamp": datetime.now(timezone.utc).isoformat()})
    upsert_session_messages(name=name, session_id=session_id, messages=messages_full)
    return jsonify({
        "name": name,
        "session_id": session_id,
        "answer": final_text,
        "tool_runs": tool_runs
    })

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
        userid, name = parse_user(user_field)
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

# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True, use_reloader=False, threaded=True)
