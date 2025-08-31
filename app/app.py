# app.py
import os
import json
from uuid import uuid4
import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

from api_client import ensure_token
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS

# Batas maksimal pesan dalam histori untuk dikirim ke AI
# (selain pesan sistem)
MAX_HISTORY_MESSAGES = 50

# === Inisialisasi ===
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY belum diisi.")
client = OpenAI(api_key=OPENAI_API_KEY)

# === Konfigurasi dan pembuatan direktori log ===
API_LOG_DIR = os.getenv("API_LOG_DIR", "./logs")
os.makedirs(API_LOG_DIR, exist_ok=True)
# ==========================================================

# Simpan histori per sesi di memori (untuk demo lokal)
SESSIONS = {}

DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten yang membantu untuk sebuah Admin API. "
    "Gunakan tools yang tersedia untuk melakukan operasi CRUD. "
    "Berikan jawaban yang ringkas, hanya tampilkan field-field kunci. "
    "Jika sebuah operasi gagal, berikan pesan error yang singkat dan jelas. "
    "Selalu balas dalam Bahasa Indonesia. "
    "Saat menjelaskan sesuatu, JANGAN GUNAKAN FORMAT MARKDOWN seperti bintang (`**`) untuk bold atau tanda hubung (`-`) untuk daftar. "
    "Gunakan kalimat lengkap dalam bentuk paragraf atau daftar bernomor (1., 2., 3.) jika diperlukan untuk membuat penjelasan yang rapi dan mudah dibaca."
)

def _log_tool_call(session_id: str, function_name: str, args: dict, result: any):
    """Mencatat pemanggilan tool ke file log yang unik per panggilan."""
    try:
        now = datetime.datetime.now()
        
        # <-- KODE DIPERBAIKI: Format nama file menyertakan jam agar tidak saling menimpa -->
        timestamp_safe = now.strftime("%Y-%m-%d_%H-%M-%S")
        short_sid = session_id[:8]
        log_filename = f"{timestamp_safe}__{function_name}_{short_sid}.log"
        log_path = os.path.join(API_LOG_DIR, log_filename)

        # Format argumen dan hasil
        args_str = json.dumps(args, ensure_ascii=False)
        result_str = json.dumps(result, ensure_ascii=False, indent=2)

        # Format header untuk konten file
        header_line = f"[{now.strftime('%Y/%m/%d %H:%M:%S')}] [{session_id}]"

        # Buat entri log
        log_entry = (
            f"{header_line}\n"
            f"{function_name}({args_str})\n"
            f"{result_str}\n"
        )

        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"!! Gagal menulis log: {e}")

@app.route("/")
def index():
    return render_template("index.html") if os.path.exists("lisa-chatbot/app/templates/index.html") else "OK"

@app.route("/api/session", methods=["POST"])
def create_session():
    body = request.get_json(silent=True) or {}
    system_prompt = body.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

    sid = str(uuid4())
    SESSIONS[sid] = [{"role": "system", "content": system_prompt}]
    return jsonify({"session_id": sid})

def _extract_bearer_token(req) -> str:
    # Prioritas: Authorization header
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # Alternatif: X-Api-Token header
    x = (req.headers.get("X-Api-Token") or "").strip()
    if x:
        return x
    # Alternatif: body.token (tidak disarankan, tapi kadang berguna)
    try:
        data = req.get_json(silent=True) or {}
        if isinstance(data, dict):
            t = (data.get("token") or "").strip()
            if t:
                return t
    except Exception:
        pass
    return ""

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    sid = data.get("session_id")
    user_msg = (data.get("message") or "").strip()

    if not sid or sid not in SESSIONS:
        sid = str(uuid4())
        SESSIONS[sid] = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]

    if not user_msg:
        return jsonify({"error": "Pesan kosong.", "session_id": sid}), 400

    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}", "session_id": sid}), 401

    messages = SESSIONS[sid]

    # <-- KODE DIPERBAIKI: Logika Sliding Window ditempatkan di sini -->
    # Jika histori lebih panjang dari batas, potong histori lama.
    if len(messages) > MAX_HISTORY_MESSAGES:
        # Selalu simpan pesan pertama (system prompt) dan X pesan terakhir.
        messages = [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]
        SESSIONS[sid] = messages # Simpan kembali histori yang sudah dipotong
    # -------------------------------------------------------------

    messages.append({"role": "user", "content": user_msg})

    try:
        first = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice="auto",
            temperature=0.2,
        )

        resp_msg = first.choices[0].message
        tool_calls = getattr(resp_msg, "tool_calls", None)
        tool_runs = []

        if tool_calls:
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

            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                try:
                    out = AVAILABLE_FUNCS[fname](**fargs)
                    _log_tool_call(sid, fname, fargs, out)
                    result_json = json.dumps(out, ensure_ascii=False)
                except Exception as fn_err:
                    err_obj = {"error": str(fn_err)}
                    _log_tool_call(sid, fname, fargs, err_obj)
                    result_json = json.dumps(err_obj, ensure_ascii=False)

                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": result_json,
                    }
                )

            second = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.2,
            )
            final_text = second.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": final_text})

            return jsonify(
                {
                    "session_id": sid,
                    "answer": final_text,
                    "tool_runs": tool_runs,
                }
            )

        final_text = resp_msg.content or ""
        messages.append({"role": "assistant", "content": final_text})
        return jsonify({"session_id": sid, "answer": final_text, "tool_runs": []})

    except Exception as e:
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "session_id": sid}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=True)