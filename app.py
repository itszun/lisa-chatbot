# app.py
import os
import json
import requests
from uuid import uuid4
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# === Inisialisasi ===
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")

# Gunakan environment variable, JANGAN hardcode API key
# Windows (PowerShell):  $env:OPENAI_API_KEY="sk-xxxx"
# Linux/Mac:             export OPENAI_API_KEY="sk-xxxx"
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Simpan histori per sesi di memori (untuk demo lokal)
SESSIONS = {}

# === FUNGSI (TOOLS) ===
def get_pokemon_info(name: str):
    """Mengambil informasi umum tentang Pokémon seperti ID, tinggi, dan berat."""
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        info = {
            "name": data["name"],
            "id": data["id"],
            "height": f"{data['height'] / 10} m",
            "weight": f"{data['weight'] / 10} kg",
        }
        return json.dumps(info)
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Masalah koneksi: {e}"})

def get_pokemon_abilities(name: str):
    """Mendapatkan daftar kemampuan (abilities) dari Pokémon tertentu."""
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        abilities = [ability["ability"]["name"] for ability in data["abilities"]]
        return json.dumps({"name": data["name"], "abilities": abilities})
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Masalah koneksi: {e}"})

def get_pokemon_types(name: str):
    """Mendapatkan daftar tipe (misalnya fire, water, grass) dari Pokémon tertentu."""
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        types = [t["type"]["name"] for t in data["types"]]
        return json.dumps({"name": data["name"], "types": types})
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Masalah koneksi: {e}"})

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_info",
            "description": "Dapatkan data umum (ID, tinggi, berat) dari Pokémon berdasarkan namanya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Pikachu"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_abilities",
            "description": "Dapatkan daftar semua kemampuan (ability) dari Pokémon tertentu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Snorlax"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_types",
            "description": "Dapatkan tipe elemen dari Pokémon tertentu (misal: fire, water, electric).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Bulbasaur"}
                },
                "required": ["name"],
            },
        },
    },
]

AVAILABLE_FUNCS = {
    "get_pokemon_info": get_pokemon_info,
    "get_pokemon_abilities": get_pokemon_abilities,
    "get_pokemon_types": get_pokemon_types,
}

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful Pokémon assistant. "
    "Answer the user's questions based on the function results. "
    "If a Pokémon tidak ditemukan, jelaskan dengan ramah."
)

# === ROUTES ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/session", methods=["POST"])
def create_session():
    body = request.get_json(silent=True) or {}
    system_prompt = body.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

    sid = str(uuid4())
    SESSIONS[sid] = [
        {"role": "system", "content": system_prompt}
    ]
    return jsonify({"session_id": sid})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    sid = data.get("session_id")
    user_msg = data.get("message", "").strip()

    if not sid or sid not in SESSIONS:
        return jsonify({"error": "session_id tidak valid. Buat sesi baru."}), 400
    if not user_msg:
        return jsonify({"error": "Pesan kosong."}), 400

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
                result = AVAILABLE_FUNCS[fname](fargs.get("name"))
                tool_runs.append(
                    {"name": fname, "args": fargs, "result": json.loads(result)}
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": result,  # JSON string
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
                    "answer": final_text,
                    "tool_runs": tool_runs,
                }
            )

        # Tanpa tool call, langsung jawab
        final_text = resp_msg.content or ""
        messages.append({"role": "assistant", "content": final_text})
        return jsonify({"answer": final_text, "tool_runs": []})

    except Exception as e:
        # Tangani error dengan aman (tanpa membocorkan key / stack detail)
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}"}), 500

if __name__ == "__main__":
    # Jalankan server lokal
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
