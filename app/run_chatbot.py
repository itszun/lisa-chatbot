# app.py
import os
import json
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

from api_client import ensure_token, set_token
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS

# === Inisialisasi ===
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY belum diisi.")
client = OpenAI(api_key=OPENAI_API_KEY)

# Simpan histori per sesi di memori (untuk demo lokal)
SESSIONS = {}

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant for a remote Admin API. "
    "Use the tools to perform CRUD on resources under /api/{panel}/... "
    "Prefer concise answers, show key fields only. "
    "If an operation fails, return a short, actionable error message."
)

@app.route("/")
def index():
    return render_template("index.html") if os.path.exists("app/templates") else "OK"

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

    # Pastikan sesi
    if not sid or sid not in SESSIONS:
        # Buat sesi minimal bila klien tidak create dulu
        sid = str(uuid4())
        SESSIONS[sid] = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]

    if not user_msg:
        return jsonify({"error": "Pesan kosong.", "session_id": sid}), 400

    # === Pastikan token Admin API tersedia ===
    try:
        incoming_token = _extract_bearer_token(request)
        # Akan:
        # - pakai token dari header kalau ada (validasi singkat)
        # - kalau tidak ada, coba cache atau LOGIN_EMAIL/PASSWORD (lihat api_client.ensure_token)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        # Balikkan pesan yang jelas untuk frontend
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}", "session_id": sid}), 401

    messages = SESSIONS[sid]
    messages.append({"role": "user", "content": user_msg})

    try:
        # --- Panggilan pertama: putuskan perlu tool atau tidak ---
        first = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice="auto",
            temperature=0.2,
        )

        resp_msg = first.choices[0].message
        tool_calls = getattr(resp_msg, "tool_calls", None)

        tool_runs = []  # untuk dikirim ke frontend sebagai jejak (trace)

        if tool_calls:
            # Tambahkan pesan assistant yang berisi instruksi tool_calls
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

            # Jalankan setiap tool yang diminta
            for tc in tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments or "{}")
                try:
                    # Catatan: fungsi-fungsi Admin API punya parameter beragam.
                    # Kita panggil dengan **fargs agar fleksibel (tidak hanya 'name').
                    out = AVAILABLE_FUNCS[fname](**fargs)
                    result_json = json.dumps(out, ensure_ascii=False)
                except Exception as fn_err:
                    result_json = json.dumps({"error": str(fn_err)}, ensure_ascii=False)

                tool_runs.append({"name": fname, "args": fargs, "result": json.loads(result_json)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": result_json,
                    }
                )

            # --- Panggilan kedua: susun jawaban akhir ---
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

        # Tanpa tool call, langsung jawab
        final_text = resp_msg.content or ""
        messages.append({"role": "assistant", "content": final_text})
        return jsonify({"session_id": sid, "answer": final_text, "tool_runs": []})

    except Exception as e:
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "session_id": sid}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    # Gunakan 0.0.0.0 kalau mau diakses dari luar host
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=True)
