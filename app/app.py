# app.py (Versi Final Tanpa Validasi Awal)
# -*- coding: utf-8 -*-
from tools_registry import Helper
from feeder import Feeder
from dataclasses import dataclass
import os
import json
from uuid import uuid4
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from api_client import ensure_token
from prompt import TemplatePrompt
from agent.lisa import Lisa
import json
from agent.tools import tools, retrieve_prompt, fetch_user_data
from logs import setup_logging
# ======================================================================
# KONFIGURASI UMUM
# ======================================================================
MAX_HISTORY_MESSAGES = 100

Helper().register(tools=tools,
                  retrieve_prompt=retrieve_prompt,
                  fetch_user_data=fetch_user_data)

load_dotenv()
setup_logging()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})
app.logger.info("Running Flask")

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI belum diisi.")

API_LOG_DIR = os.getenv("API_LOG_DIR", "./logs")
os.makedirs(API_LOG_DIR, exist_ok=True)

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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat2():
    data = request.get_json(force=True)
    is_new = False

    chat_user_id = (data.get("user") or "").strip()
    user_msg = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    if session_id == "":
        session_id = str(uuid4())
        is_new = True

    try:
        response = Lisa(is_new=is_new).chat(chat_user_id, user_msg, session_id)
    except Exception as e:
        return jsonify({
            "user": chat_user_id,
            "session_id": session_id,
            "answer": "Terjadi Kesalahan",
        })


    response_data = {
        "user": chat_user_id,
        "session_id": session_id,
        "answer": response.text(),
    }

    if is_new:
        response_data["new_session_id"] = session_id

    return jsonify(response_data)


@app.get("/api/sessions")
def get_sessions2():
    from vectordb import MongoProvider
    chat_user_id = (request.args.get("chat_user_id") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    print(session_id)
    result = MongoProvider().get_session({
        "chat_user_id": chat_user_id
    })
    if len(result) < 1:
        return jsonify({
            "chat_user_id": chat_user_id,
            "sessions": []
        })

    return jsonify(result[0])


@app.get("/api/session/messages")
def get_session_messages2():
    from vectordb import MongoProvider
    chat_user_id = (request.args.get("user") or "").strip()
    session_id = (request.args.get("session_id") or "").strip()
    print(session_id)
    result = MongoProvider().get_session_messages({
        "session_id": session_id
    })
    if len(result) < 1:
        return jsonify({
            'chat_user_id': chat_user_id,
            'session_id': session_id,
            'messages': []
        })
    result = result[0]
    result['messages'] = [json.loads(i) for i in result['messages']]
    print("result")
    print(result)
    return jsonify(result)


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
