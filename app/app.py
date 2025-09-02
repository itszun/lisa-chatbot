# app.py
import os
import json
from datetime import datetime
from pymongo.errors import DuplicateKeyError

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from api_client import ensure_token
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS

# Maksimum pesan histori yang DIKIRIM ke model (riwayat lengkap tetap disimpan di Mongo)
MAX_HISTORY_MESSAGES = 50

# === Inisialisasi ===
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY belum diisi.")

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI belum diisi.")

client = OpenAI(api_key=OPENAI_API_KEY)

# Konfigurasi direktori log
API_LOG_DIR = os.getenv("API_LOG_DIR", "./logs")
os.makedirs(API_LOG_DIR, exist_ok=True)

# Koneksi ke MongoDB
try:
    mongo_client = MongoClient(
        MONGO_URI,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=5000
    )
    mongo_client.admin.command("ping")
    db = mongo_client.chatbot_db
    sessions_collection = db.sessions
    # Unik per user_id + session_id
    sessions_collection.create_index([("user_id", 1), ("session_id", 1)], unique=True)
    print("Berhasil terhubung ke MongoDB!")
except Exception as e:
    print(f"Gagal terhubung ke MongoDB: {e}")
    mongo_client = None

# System prompt default
DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten yang membantu untuk sebuah Admin API. "
    "Gunakan tools yang tersedia untuk melakukan operasi CRUD. "
    "Berikan jawaban yang ringkas, hanya tampilkan field-field kunci. "
    "Jika sebuah operasi gagal, berikan pesan error yang singkat dan jelas. "
    "Selalu balas dalam Bahasa Indonesia. "
    "Saat menjelaskan sesuatu, JANGAN GUNAKAN FORMAT MARKDOWN seperti bintang (`**`) untuk bold atau tanda hubung (`-`) untuk daftar. "
    "Gunakan kalimat lengkap dalam bentuk paragraf atau daftar bernomor (1., 2., 3.) jika diperlukan untuk membuat penjelasan yang rapi dan mudah dibaca."
)

def _log_tool_call(user_id: str, session_id: str, function_name: str, args: dict, result: any):
    """Tulis log setiap pemanggilan tool ke file terpisah."""
    try:
        now = datetime.now()
        timestamp_safe = now.strftime("%Y-%m-%d_%H-%M-%S")
        short_sid = (session_id or "")[:8]
        log_filename = f"{timestamp_safe}__{function_name}_{short_sid}.log"
        log_path = os.path.join(API_LOG_DIR, log_filename)

        args_str = json.dumps(args, ensure_ascii=False)
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        header_line = f"[{now.strftime('%Y/%m/%d %H:%M:%S')}] [User: {user_id}, Session: {session_id}]"

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                f"{header_line}\n"
                f"Fungsi yang dipanggil: {function_name}({args_str})\n"
                f"Hasil: {result_str}\n"
            )
    except Exception as e:
        print(f"!! Gagal menulis log: {e}")

def _extract_bearer_token(req) -> str:
    """Ambil token dari Authorization: Bearer ..., atau X-Api-Token, atau body.token."""
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

def _get_or_create_session(user_id: str, sid: str, system_prompt: str) -> dict:
    """Ambil sesi dari Mongo; jika tidak ada, buat baru dengan system prompt default."""
    if not mongo_client:
        raise RuntimeError("Koneksi MongoDB tidak tersedia.")

    doc = sessions_collection.find_one({"user_id": user_id, "session_id": sid})
    if doc:
        return doc

    new_doc = {
        "user_id": user_id,
        "session_id": sid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "messages": [{"role": "system", "content": system_prompt}],
        "resets_count": 0,
        "checkpoints": []
    }
    try:
        sessions_collection.insert_one(new_doc)
        return new_doc
    except DuplicateKeyError:
        return sessions_collection.find_one({"user_id": user_id, "session_id": sid})

def _trim_for_model(messages: list) -> list:
    """Pertahankan system pertama + potong ke MAX_HISTORY_MESSAGES untuk efisiensi token."""
    if not messages:
        return messages
    if len(messages) > MAX_HISTORY_MESSAGES:
        return [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]
    return messages

@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception:
        return "OK"

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "mongo": bool(mongo_client)}), 200

@app.route("/api/history", methods=["GET"])
def get_history():
    """Ambil riwayat percakapan dari Mongo untuk user_id + session_id."""
    user_id = request.args.get("user_id", "").strip()
    sid = request.args.get("session_id", "").strip()
    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400

    try:
        doc = _get_or_create_session(user_id, sid, DEFAULT_SYSTEM_PROMPT)
        return jsonify({
            "session_id": sid,
            "user_id": user_id,
            "messages": doc.get("messages", []),
            "resets_count": doc.get("resets_count", 0),
            "checkpoints": doc.get("checkpoints", []),
        })
    except Exception as e:
        return jsonify({"error": f"Gagal mengambil riwayat: {str(e)}"}), 500

# === Endpoint baru: GET /api/session/<session_id> ===
@app.route("/api/session/<sid>", methods=["GET"])
def get_session(sid):
    """Ambil dokumen session lengkap berdasarkan session_id + user_id (query)."""
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "user_id harus disediakan."}), 400

    try:
        doc = sessions_collection.find_one({"user_id": user_id, "session_id": sid})
        if not doc:
            return jsonify({"error": "Session tidak ditemukan"}), 404

        # Convert ObjectId agar JSON-serializable
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return jsonify(doc), 200
    except Exception as e:
        return jsonify({"error": f"Gagal mengambil session: {str(e)}"}), 500

@app.route("/api/reset", methods=["POST"])
def logical_reset():
    """
    Reset logis: tidak menghapus riwayat.
    Hanya menambah checkpoint dan menaikkan counter, berguna untuk 'mulai baru' di UI.
    """
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    sid = (data.get("session_id") or "").strip()
    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400

    try:
        doc = _get_or_create_session(user_id, sid, DEFAULT_SYSTEM_PROMPT)
        checkpoint = {"at": datetime.utcnow().isoformat() + "Z", "note": "logical reset"}
        update_res = sessions_collection.update_one(
            {"_id": doc["_id"]},
            {
                "$inc": {"resets_count": 1},
                "$push": {"checkpoints": checkpoint},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return jsonify({
            "ok": True,
            "session_id": sid,
            "checkpoint": checkpoint,
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except Exception as e:
        return jsonify({"error": f"Gagal reset: {str(e)}"}), 500

@app.route("/api/hard_reset", methods=["POST"])
def hard_reset():
    """
    OPSIONAL: hard reset, mengosongkan riwayat dan menyisakan system prompt.
    Pakai hanya bila memang ingin menghapus pesan lama.
    """
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    sid = (data.get("session_id") or "").strip()
    system_prompt = data.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400

    try:
        doc = _get_or_create_session(user_id, sid, system_prompt)
        new_messages = [{"role": "system", "content": system_prompt}]
        update_res = sessions_collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"messages": new_messages, "updated_at": datetime.utcnow()}}
        )
        return jsonify({
            "ok": True,
            "session_id": sid,
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except Exception as e:
        return jsonify({"error": f"Gagal hard reset: {str(e)}"}), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Alur:
    1) Validasi input & auth (jika tools butuh token).
    2) Ambil/buat sesi.
    3) Jika message kosong:
       - Ada riwayat → minta model ringkas 1 kalimat (instruksi ketat + fallback).
       - Tidak ada riwayat → welcome.
    4) Jika message ada:
       - Kirim ke model (tools auto).
       - Jalankan AVAILABLE_FUNCS utk tiap tool call.
       - Simpan semua ke Mongo dan kembalikan metrik update DB.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Permintaan tidak valid. Harap kirimkan JSON."}), 400

    user_id = (data.get("user_id") or "").strip()
    sid = (data.get("session_id") or "").strip()
    user_msg = (data.get("message") or "").strip()
    system_prompt = data.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400

    # Auth Admin API (bila dipakai oleh tools)
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}", "session_id": sid}), 401

    # Ambil/buat sesi
    try:
        session_doc = _get_or_create_session(user_id, sid, system_prompt)
        messages = session_doc.get("messages", [])
    except Exception as e:
        return jsonify({"error": f"Gagal memuat sesi: {str(e)}"}), 500

    # Pesan kosong → ringkasan atau welcome
    if not user_msg:
        if len(messages) > 1:
            # Ada riwayat selain system
            history_for_summary = _trim_for_model(messages[:])
            history_for_summary.append({
                "role": "user",
                "content": (
                    "Ringkas seluruh percakapan sebelumnya dalam 1 kalimat bahasa Indonesia. "
                    "Jangan mengatakan bahwa Anda tidak memiliki akses ke riwayat; Anda SEDANG diberi riwayat di atas."
                )
            })
            try:
                summary_completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=history_for_summary,
                    temperature=0.2,
                )
                summary_text = summary_completion.choices[0].message.content or ""

                # Fallback jika model masih menjawab 'tidak punya akses'
                low = summary_text.lower()
                if ("tidak memiliki akses" in low) or ("tidak dapat mengakses" in low):
                    last_user_msgs = [m["content"] for m in messages if m.get("role") == "user"][-2:]
                    joined = "; ".join(last_user_msgs) if last_user_msgs else "Percakapan singkat tanpa detail khusus."
                    summary_text = f"Ringkasan singkat: {joined}"

                messages.append({"role": "assistant", "content": summary_text})
                update_res = sessions_collection.update_one(
                    {"_id": session_doc["_id"]},
                    {"$set": {"messages": messages, "updated_at": datetime.utcnow()}}
                )
                return jsonify({
                    "session_id": sid,
                    "messages": messages,
                    "answer": summary_text,
                    "db_updated": update_res.acknowledged,
                    "db_match": update_res.matched_count,
                    "db_modified": update_res.modified_count
                })
            except Exception as e:
                return jsonify({"error": f"Gagal merangkum chat: {str(e)}"}), 500
        else:
            # Sesi baru → welcome
            welcome_msg = "Sesi baru dimulai. Silakan ketik pesan Anda untuk memulai percakapan."
            messages.append({"role": "assistant", "content": welcome_msg})
            update_res = sessions_collection.update_one(
                {"_id": session_doc["_id"]},
                {"$set": {"messages": messages, "updated_at": datetime.utcnow()}}
            )
            return jsonify({
                "session_id": sid,
                "messages": messages,
                "answer": welcome_msg,
                "db_updated": update_res.acknowledged,
                "db_match": update_res.matched_count,
                "db_modified": update_res.modified_count
            })

    # === Ada pesan user → proses normal ===
    messages.append({"role": "user", "content": user_msg})
    tool_runs = []

    try:
        first = client.chat.completions.create(
            model="gpt-4o",
            messages=_trim_for_model(messages),
            tools=TOOLS_SPEC,
            tool_choice="auto",
            temperature=0.2,
        )

        resp_msg = first.choices[0].message
        tool_calls = getattr(resp_msg, "tool_calls", None)

        if tool_calls:
            # Simpan rencana tool call (trace)
            assistant_msg = {
                "role": "assistant",
                "content": resp_msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Jalankan tools
            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                try:
                    out = AVAILABLE_FUNCS[fname](**fargs)
                    _log_tool_call(user_id, sid, fname, fargs, out)
                    result_json = json.dumps(out, ensure_ascii=False)
                except Exception as fn_err:
                    err_obj = {"error": str(fn_err)}
                    _log_tool_call(user_id, sid, fname, fargs, err_obj)
                    result_json = json.dumps(err_obj, ensure_ascii=False)

                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fname,
                    "content": result_json,
                })

            # Jawaban final setelah tool
            second = client.chat.completions.create(
                model="gpt-4o",
                messages=_trim_for_model(messages),
                temperature=0.2,
            )
            final_text = second.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": final_text})
        else:
            # Tanpa tool call
            final_text = resp_msg.content or ""
            messages.append({"role": "assistant", "content": final_text})

        # Simpan ke Mongo
        update_res = sessions_collection.update_one(
            {"_id": session_doc["_id"]},
            {"$set": {"messages": messages, "updated_at": datetime.utcnow()}}
        )

        return jsonify({
            "session_id": sid,
            "answer": final_text,
            "tool_runs": tool_runs,
            "messages": messages,
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except Exception as e:
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "session_id": sid}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True)
