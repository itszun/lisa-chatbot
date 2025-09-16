# app.py (Versi Final Tanpa Validasi Awal)
# -*- coding: utf-8 -*-
from feeder import Feeder
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS, set_helpers
from dataclasses import dataclass
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
from prompt import TemplatePrompt

# ======================================================================
# KONFIGURASI UMUM
# ======================================================================
MAX_HISTORY_MESSAGES = 100

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

# ======================================================================
# UTILITAS
# ======================================================================

# Struktur data untuk menyimpan info user


@dataclass
class User:
    userid: str
    name: str

# Fungsi untuk mengurai field user


def parse_user(user_field: str) -> User:
    """Mengurai 'userid@name' dan mengembalikan objek User yang rapi."""
    if not user_field or "@" not in user_field:
        raise ValueError("Format user harus 'userid@nama'.")
    userid, name = user_field.split("@", 1)
    userid = userid.strip()
    name = name.strip()
    if not userid or not name:
        raise ValueError("userid atau nama tidak boleh kosong.")
    return User(userid=user_field, name=user_field)


def get_or_create_chat_doc(name: str, **kwargs) -> dict:
    doc = users_chats.find_one({"name": name})
    if doc:
        user_exists = users_chats.find_one({"name": name})
        if not user_exists:
            # Jika userid belum ada, tambahkan ke array 'users'
            users_chats.update_one(
                {"name": name},
            )
        return users_chats.find_one({"name": name})

    else:
        # Dokumen tidak ditemukan, buat yang baru
        new_doc = {
            "name": name,
            "sessions": []
        }
        users_chats.insert_one(new_doc)
        return users_chats.find_one({"name": name})

# Mencari sesi dalam dokumen berdasarkan session_id
# Kembalikan sesi yang ditemukan atau None.


def find_session(doc: dict, session_id: str) -> Optional[dict]:
    for s in (doc.get("sessions") or []):
        if s.get("session_id") == session_id:
            return s
    return None

# Memperbarui pesan dalam sesi yang ada di mongo berdasarkan name dan session_id
# Gunakan 'name' sebagai kunci utama.


def upsert_session_messages(name: str, session_id: str, messages: List[dict]) -> None:
    users_chats.update_one(
        {"name": name, "sessions.session_id": session_id},
        {"$set": {"sessions.$.messages": messages}}
    )

# Menambahkan sesi baru
# Gunakan 'name' sebagai kunci utama.


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

# Ekstrak token Bearer dari header Authorization


def _extract_bearer_token(req) -> str:
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


# ======================================================================
# IMPORT TOOLS + INJEKSI HELPER
# ======================================================================
# Injeksi helper dari app.py ke tools_registry.py
# untuk mengakses fungsi get_or_create_chat_doc dan append_session
# tanpa membuat dependensi melingkar.
# kenapa? Karena tools_registry.py perlu mengakses MongoDB
set_helpers(get_or_create_chat_doc, append_session,
            TemplatePrompt.DEFAULT_SYSTEM_PROMPT)

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
        if incoming_token:
            ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (request.args.get("user") or "").strip()

    # PANGGIL DENGAN DUA PARAMETER
    doc = get_or_create_chat_doc(name=user_field)

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

    return jsonify({"name": user_field, "sessions": sessions})


@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json(force=True)
    try:
        incoming_token = _extract_bearer_token(request)
        if incoming_token:
            ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (data.get("user") or "").strip()
    system_prompt = data.get(
        "system_prompt") or TemplatePrompt.DEFAULT_SYSTEM_PROMPT

    personalized_greeting = f"Hai {user_field}, adakah yang bisa saya bantu?"

    # PANGGIL DENGAN DUA PARAMETER
    _ = get_or_create_chat_doc(name=user_field)

    new_sid = str(uuid4())
    created_at = datetime.now(timezone.utc)
    default_title = "Percakapan Baru"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": personalized_greeting},
    ]

    # PANGGIL DENGAN NAME
    append_session(
        name=user_field,
        session_id=new_sid,
        created_at=created_at,
        messages=messages,
        title=default_title
    )
    return jsonify({
        "name": user_field,
        "session_id": new_sid,
        "title": default_title,
        "created_at": created_at.isoformat()
    })

from agent.lisa import Lisa
import json
@app.route("/api/chat2", methods=["POST"])
def chat2():
    data = request.get_json(force=True)
    
    user_field = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = data.get("session_id").strip()
    if session_id == "":
        session_id = str(uuid4()) 

    response = Lisa().chat(user_msg, session_id)
    print("RESPONSE ======")
    return jsonify({
            "session_id": session_id,
            "answer": response.text()
        })


@app.route("/api/chat", methods=["POST"])
def chat():
    from prompt import ContextDefiner
    data = request.get_json(force=True)
    try:
        incoming_token = _extract_bearer_token(request)
        if incoming_token:
            ensure_token(preferred_token=incoming_token)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    if not user_field or not user_msg:
        return jsonify({"error": "Input tidak lengkap (membutuhkan user dan message)."}), 400

    doc = get_or_create_chat_doc(name=user_field)

    is_new_session = not session_id
    messages_full: List[dict] = []

    if is_new_session:
        session_id = str(uuid4())
        prompt = ContextDefiner(
            chat_user_id=user_field,
            user_message=user_msg,
            session_id=session_id,
        ).getSystemPrompt()
        messages_full = [
            {"role": "system", "content": prompt,
                "timestamp": str(datetime.now())},
            {"role": "user", "content": user_msg,
                "timestamp": str(datetime.now())}
        ]
    else:
        sess = find_session(doc, session_id)
        if not sess:
            return jsonify({"error": f"session_id '{session_id}' tidak ditemukan."}), 404
        messages_full = sess.get("messages", [])
        messages_full.append(
            {"role": "user", "content": user_msg, "timestamp": str(datetime.now())})

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
        timestamp = str(datetime.now())
        messages_full.append({
            **message_dict,
            "timestamp": timestamp
        })
        final_text = message_dict["content"]
        tool_calls = resp_msg.tool_calls

        if tool_calls:
            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                out = AVAILABLE_FUNCS[fname](**fargs)
                result_json = json.dumps(out, ensure_ascii=False)
                tool_runs.append(
                    {"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages_full.append({"role": "tool", "tool_call_id": tc.id, "name": fname,
                                     "content": result_json, "timestamp": str(datetime.now())})

            second = client.chat.completions.create(
                model="gpt-4o", messages=_ctx_slice(messages_full), temperature=0.2)
            final_text = second.choices[0].message.content or ""
            timestamp = str(datetime.now())
            messages_full.append(
                {"role": "assistant", "content": final_text, "timestamp": timestamp})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "detail": str(e)}), 500

    if is_new_session:
        history = json.dumps(messages_full)
        title = (client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": f"Buat judul singkat (maksimal 5 kata) untuk percakapan yang diawali dengan: '{history}'"}],
            temperature=0.2, max_tokens=20
        ).choices[0].message.content or "Percakapan Baru").strip().replace('"', '')
        append_session(name=user_field, session_id=session_id, created_at=datetime.now(
            timezone.utc), messages=messages_full, title=title),
    else:
        upsert_session_messages(
            name=user_field, session_id=session_id, messages=messages_full)

    response_data = {
        "user": user_field,
        "session_id": session_id,
        "answer": final_text,
        "tool_runs": tool_runs,
        "timestamp": timestamp
    }

    if is_new_session:
        response_data["new_session_id"] = session_id

    return jsonify(response_data)


@app.get("/api/session/messages")
def get_session_messages():
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(
            preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    user_field = (request.args.get("user") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    if not user_field or not session_id:
        return jsonify({"error": "Parameter 'user' dan 'session_id' wajib diisi."}), 400

    # CARI DENGAN NAME
    doc = users_chats.find_one({"name": user_field})
    if not doc:
        return jsonify({"error": f"Nama '{user_field}' belum terdaftar."}), 404

    sess = find_session(doc, session_id)
    if not sess:
        return jsonify({"error": f"session_id '{session_id}' tidak ditemukan untuk nama '{user_field}'."}), 404

    msgs = sess.get("messages", []) or []
    return jsonify({
        "name": doc.get("name", user_field),
        "session_id": session_id,
        "messages": msgs
    })


@app.post("/api/feeder/talents")
def feed_talent():
    payload = request.json
    try:
        Feeder().pushTalentInfo(payload['data'])
    except Exception as e:
        print(payload['data'])
        raise e

    return jsonify({
        "status": "success"
    })


@app.post("/api/feeder/companies")
def feed_job_company():
    payload = request.json
    try:
        Feeder().pushCompanyInfo(payload['data'])
    except Exception as e:
        print(payload['data'])
        raise e

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
    try:
        Feeder().pushJobOpening(payload['data'])
    except Exception as e:
        print(payload['data'])
        raise e
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


@app.post("/api/feeder/clean")
def clean_feeder():
    Feeder().clean()

    return jsonify({
        "status": "success"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True,
            use_reloader=False, threaded=True)
