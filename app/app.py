# app.py
# -*- coding: utf-8 -*-
import os
import json
from uuid import uuid4
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from api_client import ensure_token
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS

# ======================================================================
# KONFIGURASI UMUM
# ======================================================================
MAX_HISTORY_MESSAGES = 50  # jumlah pesan (di luar system pertama) yang dikirim ke model

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

# Sapaan default utk sesi baru
DEFAULT_GREETING = os.getenv("DEFAULT_GREETING", "Halo! Ada yang bisa saya bantu?")

# ======================================================================
# KONEKSI MONGODB (Skema: satu dokumen per NAMA)
#   Koleksi: users_chats
#   Dokumen:
#     {
#       _id,
#       name: "Nama Lengkap",
#       users: ["userid1", "userid2", ...],
#       sessions: [
#         { session_id, created_at, messages: [ {role, content, ...}, ... ] },
#         ...
#       ]
#     }
#   Index unik: name
# ======================================================================
mongo_client = None
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
# SYSTEM PROMPT DEFAULT
# ======================================================================
DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten yang membantu untuk sebuah Admin API. "
    "Gunakan tools yang tersedia untuk melakukan operasi CRUD. "
    "Berikan jawaban yang ringkas, hanya tampilkan field-field kunci. "
    "Jika sebuah operasi gagal, berikan pesan error yang singkat dan jelas. "
    "Selalu balas dalam Bahasa Indonesia. "
    
    # --- 🔥 TAMBAHKAN INSTRUKSI BARU DI SINI 🔥 ---
    "PENTING: Ketika Anda menerima hasil dari sebuah pemanggilan tool (function call), JANGAN PERNAH menampilkan data mentah JSON kepada pengguna. "
    "Tugas Anda adalah menginterpretasikan data tersebut dan menyajikannya dalam format yang mudah dibaca, seperti kalimat lengkap, daftar bernomor, atau ringkasan. "
    "Misalnya, jika Anda menerima daftar talent dalam format JSON, ubah itu menjadi daftar nama dan posisi yang rapi."
    # --- Batas instruksi baru ---

    "Saat menjelaskan sesuatu, JANGAN GUNAKAN FORMAT MARKDOWN seperti bintang (**) untuk bold atau tanda hubung (-) untuk daftar. "
    "Gunakan kalimat lengkap dalam bentuk paragraf atau daftar bernomor (1., 2., 3.) jika diperlukan untuk membuat penjelasan yang rapi dan mudah dibaca."
)

# ======================================================================
# UTILITAS
# ======================================================================
def parse_user(user_field: str) -> Tuple[str, str]:
    """
    Mem-parse 'user' dengan format 'userid@nama' → (userid, nama).
    Contoh: 'u123@Budi Santoso' → ('u123', 'Budi Santoso')
    """
    if not user_field or "@" not in user_field:
        raise ValueError("Format user harus 'userid@nama'.")
    userid, name = user_field.split("@", 1)
    userid = userid.strip()
    name = name.strip()
    if not userid or not name:
        raise ValueError("userid atau nama tidak boleh kosong.")
    return userid, name

def get_or_create_name_doc(name: str, userid: Optional[str] = None) -> dict:
    """
    Ambil dokumen berdasarkan 'name'. Jika belum ada dan userid diberikan, buat dokumen baru.
    Skema: { name, users:[], sessions:[] }
    """
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

def append_session(name: str, session_id: str, created_at: datetime, messages: List[dict]) -> None:
    users_chats.update_one(
        {"name": name},
        {"$push": {"sessions": {"session_id": session_id, "created_at": created_at, "messages": messages}}}
    )
def update_session_title(name: str, session_id: str, new_title: str) -> None:
    """Memperbarui field 'title' untuk sebuah sesi spesifik."""
    users_chats.update_one(
        {"name": name, "sessions.session_id": session_id},
        {"$set": {"sessions.$.title": new_title}}
    )

def append_session(name: str, session_id: str, created_at: datetime, messages: List[dict], title: str) -> None:
    """Fungsi ini sekarang menerima parameter 'title'."""
    users_chats.update_one(
        {"name": name},
        {"$push": {"sessions": {
            "session_id": session_id,
            "created_at": created_at,
            "title": title,  # <-- TAMBAHKAN INI
            "messages": messages
        }}}
    )

def create_session_with_initial_message(name: str, system_prompt: str, initial_message: str) -> Tuple[str, datetime]:
    """
    Membuat session baru pada dokumen 'name' dengan pesan awal dari assistant.
    Mengembalikan (session_id, created_at).
    """
    sid = str(uuid4())
    created_at = datetime.utcnow()
    messages = [
        {"role": "system", "content": system_prompt, "timestamp": created_at.isoformat()},
        {"role": "assistant", "content": initial_message, "timestamp": created_at.isoformat()},
    ]
    append_session(name=name, session_id=sid, created_at=created_at, messages=messages, title="Percakapan Awal")
    return sid, created_at

def _log_tool_call(userid: str, name: str, session_id: str, function_name: str, args: dict, result: Any):
    """Mencatat pemanggilan tool ke file log yang unik per panggilan."""
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
    # Prioritas: Authorization header
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # Alternatif: X-Api-Token header
    x = (req.headers.get("X-Api-Token") or "").strip()
    if x:
        return x
    # Alternatif: body.token
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
# ROUTES
# ======================================================================
@app.route("/")
def index():
    return render_template("index.html")

# ---------- SESSION DISCOVERY ----------
@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    """
    GET /api/sessions?user=userid@nama
    Mengembalikan daftar sesi untuk seorang pengguna, termasuk judulnya.
    """
    # 1. Autentikasi: Memastikan token valid
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    # 2. Validasi Input: Mengambil dan mem-parse parameter 'user'
    user_field = (request.args.get("user") or "").strip()
    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    # 3. Pengecekan Koneksi DB
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    # 4. Pengambilan Data: Ambil atau buat dokumen untuk 'name'
    doc = get_or_create_name_doc(name=name, userid=userid)
    
    # 5. Pemrosesan & Pemformatan Respons
    sessions = []
    # Iterasi melalui setiap sesi yang tersimpan di dokumen
    for s in doc.get("sessions", []):
        sessions.append({
            "session_id": s.get("session_id"),
            # Mengambil judul sesi, dengan fallback "Percakapan Baru" jika tidak ada
            "title": s.get("title", "Percakapan Baru"),
            # Mengonversi datetime ke format string ISO
            "created_at": s.get("created_at").isoformat() if isinstance(s.get("created_at"), datetime) else s.get("created_at"),
            # Menghitung jumlah pesan dalam sesi
            "messages_count": len(s.get("messages") or [])
        })
        
    # 6. Mengurutkan sesi dari yang terbaru ke yang terlama
    sessions.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    
    # 7. Mengembalikan hasil dalam format JSON
    return jsonify({"name": name, "sessions": sessions})

@app.route("/api/sessions", methods=["POST"])
def create_session():
    """
    POST /api/sessions
    Body: { "user": "userid@nama", "system_prompt": "...(opsional)" }
    Membuat session baru untuk 'nama' dengan pesan sapaan awal dan judul default.
    """
    # 1. Mengambil data dari body request
    data = request.get_json(force=True)
    
    # 2. Autentikasi: Memastikan token yang dikirim valid
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    # 3. Validasi Input: Mem-parse field dari body JSON
    user_field = (data.get("user") or "").strip()
    system_prompt = data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    # 4. Pengecekan Koneksi DB
    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    # 5. Logika Inti: Membuat sesi baru
    # Pastikan dokumen untuk 'name' sudah ada di database
    _ = get_or_create_name_doc(name=name, userid=userid)

    new_sid = str(uuid4())
    created_at = datetime.utcnow()
    default_title = "Percakapan Baru"  # Judul default untuk sesi baru

    # Siapkan pesan awal (system prompt dan sapaan)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": DEFAULT_GREETING},
    ]
    
    # Panggil fungsi utilitas untuk menambahkan sesi baru ke dokumen user
    append_session(
        name=name,
        session_id=new_sid,
        created_at=created_at,
        messages=messages,
        title=default_title  # Sertakan judul default saat menyimpan
    )

    # 6. Mengembalikan respons JSON yang sukses
    return jsonify({
        "name": name,
        "session_id": new_sid,
        "title": default_title,  # Kembalikan judul di respons
        "created_at": created_at.isoformat()
    })

# ---------- CHAT ----------
# app.py

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    POST /api/chat
    Endpoint ini sekarang menangani DUA kasus:
    1. Jika `session_id` diberikan: Melanjutkan chat di sesi yang ada.
    2. Jika `session_id` TIDAK diberikan: Membuat sesi baru dengan pesan pertama.
    """
    data = request.get_json(force=True)

    # Auth
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    # Validasi
    user_field = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = data.get("session_id") # Ambil session_id, bisa jadi None

    if not user_field:
        return jsonify({"error": "Field 'user' wajib diisi dengan format 'userid@nama'."}), 400
    if not user_msg:
        return jsonify({"error": "Pesan kosong."}), 400

    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    # Tentukan apakah ini sesi baru atau sesi yang sudah ada
    is_new_session = not session_id

    # Siapkan variabel
    messages_full: List[dict] = []
    
    # --- LOGIKA UNTUK MENANGANI DUA KASUS ---
    if is_new_session:
        # KASUS 1: Sesi baru
        session_id = str(uuid4()) # Buat ID baru di sini
        get_or_create_name_doc(name=name, userid=userid)
        messages_full = [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT, "timestamp": datetime.utcnow().isoformat()},
            {"role": "user", "content": user_msg, "timestamp": datetime.utcnow().isoformat()}
        ]
    else:
        # KASUS 2: Sesi yang sudah ada
        doc = users_chats.find_one({"name": name})
        if not doc:
            return jsonify({"error": f"Nama '{name}' belum terdaftar."}), 404
        sess = find_session(doc, session_id)
        if not sess:
            return jsonify({"error": f"session_id '{session_id}' tidak ditemukan untuk nama '{name}'."}), 404
        
        messages_full = sess.get("messages", [])
        messages_full.append({"role": "user", "content": user_msg, "timestamp": datetime.utcnow().isoformat()})

    # --- LOGIKA PEMBUATAN JUDUL ---
    user_message_count = sum(1 for m in messages_full if m.get("role") == "user")
    if user_message_count == 1 and user_msg:
        try:
            title_prompt = (
                "Anda adalah AI yang ahli membuat judul singkat. "
                "Berdasarkan pesan pertama dari pengguna ini, buatlah sebuah judul percakapan yang ringkas, jelas, dan relevan. "
                "Judul harus maksimal 5 kata. Jangan tambahkan tanda kutip atau kata 'Judul:'. "
                f"Pesan pengguna: '{user_msg}'"
            )
            title_comp = client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": title_prompt}],
                temperature=0.2, max_tokens=20
            )
            generated_title = title_comp.choices[0].message.content.strip().replace('"', '') or "Percakapan"
        except Exception as title_e:
            generated_title = "Percakapan Baru"
            print(f"!! Gagal membuat judul untuk sesi {session_id}: {title_e}")
    else:
        generated_title = None

    # Helper pangkas konteks
    def _ctx_slice(msgs: List[dict]) -> List[dict]:
        if len(msgs) > MAX_HISTORY_MESSAGES:
            return [msgs[0]] + msgs[-MAX_HISTORY_MESSAGES:]
        return msgs

    tool_runs = []
    final_text = ""

    try:
        # --- Panggilan pertama: deteksi tool ---
        ctx_messages = _ctx_slice(messages_full)
        first = client.chat.completions.create(
            model="gpt-4o", messages=ctx_messages, tools=TOOLS_SPEC,
            tool_choice="auto", temperature=0.2
        )
        resp_msg = first.choices[0].message
        tool_calls = getattr(resp_msg, "tool_calls", None)

        if tool_calls:
            messages_full.append({
                "role": "assistant",
                "content": resp_msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id, "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
                "timestamp": datetime.utcnow().isoformat()
            })

            for tc in tool_calls:
                fname = tc.function.name
                try: fargs = json.loads(tc.function.arguments or "{}")
                except Exception: fargs = {}
                try:
                    out = AVAILABLE_FUNCS[fname](**fargs)
                    _log_tool_call(userid, name, session_id, fname, fargs, out)
                    result_json = json.dumps(out, ensure_ascii=False)
                except Exception as fn_err:
                    err_obj = {"error": str(fn_err)}
                    _log_tool_call(userid, name, session_id, fname, fargs, err_obj)
                    result_json = json.dumps(err_obj, ensure_ascii=False)
                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages_full.append({
                    "role": "tool", "tool_call_id": tc.id, "name": fname, "content": result_json,
                    "timestamp": datetime.utcnow().isoformat()
                })

            # --- Panggilan kedua: susun jawaban final ---
            ctx_messages_2 = _ctx_slice(messages_full)
            second = client.chat.completions.create(model="gpt-4o", messages=ctx_messages_2, temperature=0.2)
            final_text = second.choices[0].message.content or ""
        else:
            final_text = resp_msg.content or ""

        messages_full.append({"role": "assistant", "content": final_text, "timestamp": datetime.utcnow().isoformat()})
        
        # --- LOGIKA PENYIMPANAN KE DB ---
        if is_new_session:
            append_session(
                name=name, session_id=session_id, created_at=datetime.utcnow(),
                messages=messages_full, title=generated_title or "Percakapan Baru"
            )
        else:
            upsert_session_messages(name=name, session_id=session_id, messages=messages_full)
            if generated_title:
                update_session_title(name, session_id, generated_title)

        # --- LOGIKA RESPONSE ---
        response_data = {
            "name": name, "session_id": session_id,
            "answer": final_text, "tool_runs": tool_runs
        }
        if is_new_session:
            response_data["new_session_id"] = session_id
            response_data["title"] = generated_title or "Percakapan Baru" 

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "detail": str(e)}), 500
               
    # ---------- NOTIFY INVITE ----------
@app.route("/api/notify/invite", methods=["POST"])
def notify_invite():
    """
    POST /api/notify/invite
    Body:
    {
      "sender": "userCompany@Nama Perusahaan",  # WAJIB
      "target": "userTalent@Nama Talent",       # WAJIB
      "message": "opsional pesan kustom",
      "system_prompt": "opsional system prompt untuk sesi talent"
    }
    """
    # Auth
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    data = request.get_json(force=True)
    sender_field = (data.get("sender") or "").strip()
    target_field = (data.get("target") or "").strip()
    custom_msg = (data.get("message") or "").strip()
    sys_prompt = data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    # Validasi input
    if not sender_field or "@" not in sender_field:
        return jsonify({"error": "Field 'sender' wajib format 'userid@Nama Perusahaan'."}), 400
    if not target_field or "@" not in target_field:
        return jsonify({"error": "Field 'target' wajib format 'userid@Nama Talent'."}), 400

    try:
        sender_userid, sender_name = parse_user(sender_field)
        target_userid, target_name = parse_user(target_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    # Pastikan dokumen target ada (kalau belum, buat baru)
    target_before = users_chats.find_one({"name": target_name})
    get_or_create_name_doc(name=target_name, userid=target_userid)

    # Pesan undangan
    default_text = f"PT {sender_name} mengundang Anda untuk mengikuti seleksi. Silakan konfirmasi kehadiran atau ajukan pertanyaan di sini."
    invite_text = custom_msg or default_text

    # Buat session baru di dokumen target dengan pesan awal
    sid, created_at = create_session_with_initial_message(
        name=target_name,
        system_prompt=sys_prompt,
        initial_message=invite_text
    )

    return jsonify({
        "ok": True,
        "target_name": target_name,
        "created_new_user": target_before is None,
        "session_id": sid,
        "created_at": created_at.isoformat(),
        "message": invite_text
    }), 201

# ---------- SESSION SUMMARY ----------
@app.route("/api/session/summary", methods=["GET"])
def session_summary():
    """
    GET /api/session/summary?user=userid@nama&session_id=...&max_words=40
    Mengembalikan ringkasan SANGAT SINGKAT (5 kalimat, <= max_words kata total).
    Jika sesi baru (hanya 1 bubble assistant/sapaan), ringkasan di-skip.
    """
    # Auth
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (request.args.get("user") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    max_words = (request.args.get("max_words") or "40").strip()
    try:
        max_words = max(10, min(80, int(max_words)))
    except Exception:
        max_words = 40

    if not user_field or "@" not in user_field:
        return jsonify({"error": "Param 'user' wajib format id@nama"}), 400
    if not session_id:
        return jsonify({"error": "Param 'session_id' wajib diisi"}), 400

    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    doc = users_chats.find_one({"name": name})
    if not doc:
        return jsonify({"error": f"Nama '{name}' belum terdaftar"}), 404

    sess = find_session(doc, session_id)
    if not sess:
        return jsonify({"error": f"session_id '{session_id}' tidak ditemukan untuk '{name}'"}), 404

    # Ambil pesan untuk ringkasan
    msgs = sess.get("messages", [])
    if len(msgs) > 81:
        msgs = [msgs[0]] + msgs[-80:]

    # Deteksi sesi baru (hanya sapaan)
    non_system = [m for m in msgs if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    just_greeting = (len(non_system) == 1 and non_system[0].get("role") == "assistant")

    if just_greeting:
        return jsonify({
            "name": name,
            "session_id": session_id,
            "summary": "",
            "kind": "summary_preview",
            "skip": True,
            "reason": "just_greeting"
        })

    # System prompt ringkasan
    summarize_system = (
        "Ringkas percakapan berikut dengan SANGAT SINGKAT untuk log internal. "
        "Output wajib 5 kalimat saja, maksimum {MAX_WORDS} kata total. "
        "Fokus pada: topik utama yang sedang dibahas dan keputusan/aksi berikutnya (jika ada). "
        "JANGAN pakai bullet/nomor, JANGAN menyalin daftar panjang, "
        "JANGAN mencantumkan ID/tanggal/angka serial yang tidak penting. "
        "Jangan tulis kata 'Ringkasan:' atau sapaan; langsung isi. "
    ).replace("{MAX_WORDS}", str(max_words))

    summary_messages = [{"role": "system", "content": summarize_system}]
    for m in msgs:
        r = m.get("role")
        if r in ("user", "assistant"):
            c = (m.get("content") or "").strip()
            if c:
                summary_messages.append({"role": r, "content": c})

    def _limit_words(text: str, limit: int) -> str:
        words = text.split()
        return " ".join(words[:limit]) + ("" if len(words) <= limit else "…")

    try:
        comp = client.chat.completions.create(
            model="gpt-4o",
            messages=summary_messages,
            temperature=0.1,
            max_tokens=160,
        )
        summary_text = (comp.choices[0].message.content or "").strip()
        summary_text = _limit_words(summary_text, max_words)
    except Exception as e:
        return jsonify({"error": f"Gagal merangkum: {type(e).__name__}", "detail": str(e)}), 500

    return jsonify({
        "name": name,
        "session_id": session_id,
        "summary": summary_text,
        "kind": "summary_preview",
        "skip": False
    })

# ---------- SESSION MESSAGES ----------
@app.get("/api/session/messages")
def get_session_messages():
    """
    GET /api/session/messages?user=userid@nama&session_id=...
    Mengembalikan daftar messages (tanpa memodifikasi apa pun).
    """
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (request.args.get("user") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    if not user_field or "@" not in user_field:
        return jsonify({"error": "Param 'user' wajib format id@nama"}), 400
    if not session_id:
        return jsonify({"error": "Param 'session_id' wajib diisi"}), 400

    try:
        userid, name = parse_user(user_field)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not mongo_client:
        return jsonify({"error": "MongoDB tidak tersedia"}), 500

    doc = users_chats.find_one({"name": name})
    if not doc:
        return jsonify({"error": f"Nama '{name}' belum terdaftar"}), 404

    sess = find_session(doc, session_id)
    if not sess:
        return jsonify({"error": f"session_id '{session_id}' tidak ditemukan untuk '{name}'"}), 404

    msgs = sess.get("messages", []) or []
    return jsonify({
        "name": name,
        "session_id": session_id,
        "messages": msgs
    })

# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True)
