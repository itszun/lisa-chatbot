from flask import Blueprint, jsonify, request
import traceback
# app.py (Versi Final Tanpa Validasi Awal)
# -*- coding: utf-8 -*-
from tools_registry import Helper
from feeder import Feeder
from dataclasses import dataclass
import os
import json
from uuid import uuid4
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template
from agent.lisa import Lisa
import json
# Definisikan Blueprint
api_bp = Blueprint('api', __name__, url_prefix='/')


@api_bp.route("/")
def index():
    return render_template("index.html")


@api_bp.route("/api/chat", methods=["POST"])
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
        print(e)
        tb = e.__traceback__
        # Extract the last frame, which corresponds to the error location
        last_frame = traceback.extract_tb(tb)[-1]
        line_number = last_frame.lineno
        file_name = last_frame.filename
        print(f"File: {file_name}")
        print(f"Error occurred on line: {line_number}")
        print(f"Exception: {e}")
        return jsonify({
            "user": chat_user_id,
            "session_id": session_id,
            "answer": "Terjadi Kesalahan",
            "error_detail": repr(e),
        })


    response_data = {
        "user": chat_user_id,
        "session_id": session_id,
        "answer": response.text(),
    }

    if is_new:
        response_data["new_session_id"] = session_id

    return jsonify(response_data)


@api_bp.get("/api/sessions")
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


@api_bp.get("/api/session/messages")
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


@api_bp.post("/api/feeder/talents")
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


@api_bp.post("/api/feeder/companies")
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


@api_bp.post("/api/feeder/candidates")
def feed_job_candidate():
    payload = request.json
    Feeder().pushCandidate(payload['data'])

    return jsonify({
        "status": "success"
    })


@api_bp.post("/api/feeder/job_openings")
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


@api_bp.post("/api/feeder/users")
def feed_job_user():
    payload = request.json
    Feeder().pushUserInfo(payload['data'])

    return jsonify({
        "status": "success"
    })


@api_bp.post("/api/feeder/clean")
def clean_feeder():
    Feeder().clean()

    return jsonify({
        "status": "success"
    })