# app.py
# -*- coding: utf-8 -*-

import os
import re
import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from pymongo.server_api import ServerApi

# ====== API client & Tools (sesuai file Anda) ======
from api_client import ensure_token
from tools_registry import tools as TOOLS_SPEC, available_functions as AVAILABLE_FUNCS

# =========================
# Inisialisasi
# =========================
load_dotenv()

MAX_HISTORY_MESSAGES = 50

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

# =========================
# MongoDB
# =========================
try:
    mongo_client = MongoClient(
        MONGO_URI,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=5000
    )
    mongo_client.admin.command("ping")
    db = mongo_client.chatbot_db
    sessions_collection = db.sessions
    sessions_collection.create_index([("user_id", 1), ("session_id", 1)], unique=True)
    print("Berhasil terhubung ke MongoDB!")
except Exception as e:
    print(f"Gagal terhubung ke MongoDB: {e}")
    mongo_client = None

# =========================
# Prompt Sistem
# =========================
DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten yang membantu untuk sebuah Admin API. "
    "Gunakan tools yang tersedia untuk melakukan operasi CRUD. "
    "Berikan jawaban yang ringkas, hanya tampilkan field-field kunci. "
    "Jika sebuah operasi gagal, berikan pesan error yang singkat dan jelas. "
    "Selalu balas dalam Bahasa Indonesia. "
    "Saat menjelaskan sesuatu, JANGAN GUNAKAN FORMAT MARKDOWN seperti bintang (`**`) untuk bold atau tanda hubung (`-`) untuk daftar. "
    "Gunakan kalimat lengkap dalam bentuk paragraf atau daftar bernomor (1., 2., 3.) jika diperlukan untuk membuat penjelasan yang rapi dan mudah dibaca."
)

# =========================
# Utils Umum
# =========================
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

def _log_tool_call(user_id: str, session_id: str, function_name: str, args: dict, result: Any):
    try:
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d_%H-%M-%S")
        short_sid = (session_id or "")[:8]
        log_filename = f"{ts}__{function_name}_{short_sid}.log"
        log_path = os.path.join(API_LOG_DIR, log_filename)
        args_str = json.dumps(args, ensure_ascii=False)
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        header_line = f"[{now.strftime('%Y/%m/%d %H:%M:%S')}] [User: {user_id}, Session: {session_id}]"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"{header_line}\nFungsi yang dipanggil: {function_name}({args_str})\nHasil: {result_str}\n")
    except Exception as e:
        print(f"!! Gagal menulis log: {e}")

def _trim_for_model(messages: list) -> list:
    if not messages:
        return messages
    if len(messages) > MAX_HISTORY_MESSAGES:
        return [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]
    return messages

def _slug(s: str) -> str:
    if not isinstance(s, str):
        s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    import re as _re
    return _re.sub(r"[^a-z0-9]", "", s)

# =========================
# Identitas via API Admin
# =========================
# Menggunakan fungsi-fungsi dari api_client (yang sudah Anda siapkan di REMOTE_BASE_URL/PANEL)
from api_client import (
    list_talent, get_talent_detail,
    list_companies, get_company_detail,
    list_job_openings,  # untuk rekomendasi
)

def _display_name_from_obj(obj: dict, default_val: str = "") -> str:
    if not isinstance(obj, dict):
        return default_val
    for k in ("name", "full_name", "fullname", "display_name", "company_name", "title"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Nama gabungan (kalau ada)
    first = obj.get("first_name") or obj.get("firstname")
    last  = obj.get("last_name")  or obj.get("lastname")
    combo = " ".join([str(first or "").strip(), str(last or "").strip()]).strip()
    return combo or default_val

def _parse_int(s: str) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None

def _name_match_score(candidate_name: str, query: str) -> float:
    """
    Skor 0..100 berdasarkan kesamaan nama:
      1) equal (case-insensitive) → 100
      2) slug equal (hilangkan non-alnum) → 95
      3) substring (salah satu mengandung yang lain) → 80
      4) token overlap (Jaccard) → 60 * overlap
      5) else → 0
    """
    if not isinstance(candidate_name, str):
        candidate_name = str(candidate_name or "")
    if not isinstance(query, str):
        query = str(query or "")

    a = candidate_name.strip().lower()
    b = query.strip().lower()
    if not a or not b:
        return 0.0

    if a == b:
        return 100.0

    sa = _slug(a)
    sb = _slug(b)
    if sa and sa == sb:
        return 95.0

    if a in b or b in a:
        return 80.0

    # token overlap sederhana
    ta = set([t for t in re.findall(r"[a-z0-9]+", a)])
    tb = set([t for t in re.findall(r"[a-z0-9]+", b)])
    if ta and tb:
        inter = len(ta & tb)
        union = len(ta | tb)
        jacc = inter / union if union else 0.0
        if jacc > 0:
            return 60.0 * jacc

    return 0.0

def _best_match_by_name(objects: List[dict], query: str) -> Optional[dict]:
    """
    Pilih objek dengan nama terbaik terhadap query.
    Nama diambil via _display_name_from_obj().
    """
    best = None
    best_score = -1.0
    for obj in objects or []:
        nm = _display_name_from_obj(obj, "")
        score = _name_match_score(nm, query)
        if score > best_score:
            best_score = score
            best = obj
    return best


def _resolve_identity_via_api_admin(user_id: str) -> Dict[str, Any]:
    """
    Cek user_id pada API Talent/Company (Admin API) dengan pemilihan hasil paling relevan.
    Aturan:
      - Jika user_id integer → cek detail talent, lalu company.
      - Jika string → cari DI KEDUANYA (companies & talents), skor nama, pilih skor tertinggi.
        Tie-break: prefer company.
    """
    uid = (user_id or "").strip()
    if not uid:
        return {"ok": False, "type": None, "name": "", "raw": None}

    # 1) Numeric id → detail langsung
    as_int = _parse_int(uid)
    if as_int is not None:
        try:
            t = get_talent_detail(as_int)
            if isinstance(t, dict) and t:
                return {"ok": True, "type": "talent", "name": _display_name_from_obj(t, uid), "raw": t}
        except Exception:
            pass
        try:
            c = get_company_detail(as_int)
            if isinstance(c, dict) and c:
                return {"ok": True, "type": "company", "name": _display_name_from_obj(c, uid), "raw": c}
        except Exception:
            pass
        return {"ok": False, "type": None, "name": "", "raw": None}

    # 2) String id → cari di companies & talents, lalu pilih yang paling relevan
    companies = []
    talents = []
    try:
        companies = list_companies(page=1, per_page=5, search=uid) or []
        if isinstance(companies, dict) and "data" in companies and isinstance(companies["data"], list):
            companies = companies["data"]
    except Exception:
        companies = []

    try:
        talents = list_talent(page=1, per_page=5, search=uid) or []
        if isinstance(talents, dict) and "data" in talents and isinstance(talents["data"], list):
            talents = talents["data"]
    except Exception:
        talents = []

    best_company = _best_match_by_name(companies, uid) if companies else None
    best_talent  = _best_match_by_name(talents, uid) if talents else None

    # Hitung skor keduanya
    sc_company = _name_match_score(_display_name_from_obj(best_company or {}, ""), uid) if best_company else -1
    sc_talent  = _name_match_score(_display_name_from_obj(best_talent  or {}, ""), uid) if best_talent  else -1

    # Heuristik: jika nama terlihat seperti perusahaan, beri sedikit bobot ke company
    looks_like_company = any(x in uid.lower() for x in ["-", " inc", " llc", " ltd", " pt ", " tbk", " corp", " co ", " gmbh", " s.r.l", " s.a"])
    if looks_like_company and sc_company >= 0:
        sc_company += 3.0  # dorong sedikit

    # Pilih tertinggi; jika seri → prefer company
    if sc_company > sc_talent and best_company:
        return {"ok": True, "type": "company", "name": _display_name_from_obj(best_company, uid), "raw": best_company}
    if sc_talent > sc_company and best_talent:
        return {"ok": True, "type": "talent", "name": _display_name_from_obj(best_talent, uid), "raw": best_talent}
    if sc_company == sc_talent:
        if best_company:
            return {"ok": True, "type": "company", "name": _display_name_from_obj(best_company, uid), "raw": best_company}
        if best_talent:
            return {"ok": True, "type": "talent", "name": _display_name_from_obj(best_talent, uid), "raw": best_talent}

    # Tidak ketemu apa pun
    print(f"[IDENTITY/API-ADMIN] Tidak ditemukan untuk user_id='{uid}'.")
    return {"ok": False, "type": None, "name": "", "raw": None}

def _require_identity(user_id: str) -> dict:
    """
    Pastikan token valid (ensure_token) dulu, baru validasi user_id via API Admin.
    """
    identity = _resolve_identity_via_api_admin(user_id)
    if not identity["ok"]:
        raise ValueError("user_id tidak dikenali pada API Talent/Company.")
    return identity

def _greeting_prefix(name: str) -> str:
    name = (name or "").strip()
    return f"Hii {name}" if name else "Hii"

# =========================
# Session & History (Mongo)
# =========================
def _get_or_create_session(user_id: str, sid: str, system_prompt: str, identity: dict) -> dict:
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
        "checkpoints": [],
        "identity": {"type": identity.get("type"), "name": identity.get("name")},
        "greeted": False
    }
    try:
        sessions_collection.insert_one(new_doc)
        return new_doc
    except DuplicateKeyError:
        return sessions_collection.find_one({"user_id": user_id, "session_id": sid})

# =========================
# LLM: Rekomendasi Jobs
# =========================
def _extract_skills_from_talent(t: dict) -> List[str]:
    if not isinstance(t, dict):
        return []
    skills = t.get("skills")
    # Di API Anda, skills mungkin string JSON yang disimpan.
    if isinstance(skills, str):
        try:
            arr = json.loads(skills)
            if isinstance(arr, list):
                return [str(x) for x in arr if isinstance(x, (str, int, float))]
        except Exception:
            # fallback split koma
            return [s.strip() for s in skills.split(",") if s.strip()]
    if isinstance(skills, list):
        return [str(x) for x in skills if isinstance(x, (str, int, float))]
    # Fallback: cari fields lain
    for alt in ("skill_list", "keahlian", "competencies"):
        v = t.get(alt)
        if isinstance(v, list):
            return [str(x) for x in v if isinstance(x, (str, int, float))]
        if isinstance(v, str) and v.strip():
            return [s.strip() for s in v.split(",") if s.strip()]
    return []

def _simplify_job(job: dict) -> dict:
    return {
        "id": job.get("id") or job.get("_id") or job.get("job_id"),
        "title": job.get("title") or job.get("position") or job.get("role"),
        "company_name": job.get("company_name") or (job.get("company") or {}).get("name"),
        "skills": job.get("skills") or job.get("required_skills") or [],
        "requirements": job.get("requirements") or job.get("body") or "",
        "location": job.get("location") or job.get("city") or job.get("region"),
        "raw": job
    }

def _llm_rank_jobs(talent: dict, jobs: List[dict]) -> List[dict]:
    talent_name = _display_name_from_obj(talent, "talent")
    talent_skills = _extract_skills_from_talent(talent)
    simplified = [_simplify_job(j) for j in jobs][:50]

    system_msg = (
        "Anda adalah asisten matching rekrutmen. "
        "Tugas: nilai kecocokan kandidat terhadap daftar lowongan. "
        "Berikan skor 0-100 dan alasan singkat berbasis skill/requirements. "
        "Jawab dalam JSON valid (array objek). Bahasa Indonesia singkat."
    )
    payload = {"talent": {"name": talent_name, "skills": talent_skills}, "openings": simplified}

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": "Kembalikan JSON array dengan elemen: {id, title, company_name, score, reason}."},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    ]

    try:
        comp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,
        )
        text = comp.choices[0].message.content or "[]"
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                arr.sort(key=lambda a: (a.get("score") or 0), reverse=True)
                return arr
        except Exception:
            import re as _re
            m = _re.search(r"\[.*\]", text, flags=_re.S)
            if m:
                arr = json.loads(m.group(0))
                if isinstance(arr, list):
                    arr.sort(key=lambda a: (a.get("score") or 0), reverse=True)
                    return arr
    except Exception as e:
        print("[LLM rank jobs] error:", e)

    # Fallback skor sederhana
    tset = set([s.lower() for s in talent_skills])
    def _score(j):
        js = [s.lower() for s in (j.get("skills") or []) if isinstance(s, str)]
        inter = len(tset & set(js))
        return 10 * inter

    scored = []
    for j in simplified:
        scored.append({
            "id": j["id"],
            "title": j["title"],
            "company_name": j["company_name"],
            "score": _score(j),
            "reason": "Skor berbasis overlap sederhana skill kandidat dengan requirement."
        })
    scored.sort(key=lambda a: a["score"], reverse=True)
    return scored

# =========================
# Routes
# =========================
@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception:
        return "OK"

@app.route("/api/health", methods=["GET"])
def health():
    cols = []
    try:
        cols = db.list_collection_names()
    except Exception:
        cols = []
    return jsonify({"ok": True, "mongo": bool(mongo_client), "collections": cols}), 200

@app.route("/api/history", methods=["GET"])
def get_history():
    user_id = request.args.get("user_id", "").strip()
    sid = request.args.get("session_id", "").strip()
    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400
    try:
        incoming_token = _extract_bearer_token(request)
        # Pastikan token siap untuk panggil API Admin
        ensure_token(preferred_token=incoming_token if incoming_token else None)
        identity = _require_identity(user_id)
        doc = _get_or_create_session(user_id, sid, DEFAULT_SYSTEM_PROMPT, identity)
        return jsonify({
            "session_id": sid,
            "user_id": user_id,
            "identity": {"type": identity["type"], "name": identity["name"]},
            "messages": doc.get("messages", []),
            "resets_count": doc.get("resets_count", 0),
            "checkpoints": doc.get("checkpoints", []),
            "greeted": doc.get("greeted", False)
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Gagal mengambil riwayat: {str(e)}"}), 500

@app.route("/api/session/<sid>", methods=["GET"])
def get_session(sid):
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "user_id harus disediakan."}), 400
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
        _ = _require_identity(user_id)
        doc = sessions_collection.find_one({"user_id": user_id, "session_id": sid})
        if not doc:
            return jsonify({"error": "Session tidak ditemukan"}), 404
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return jsonify(doc), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Gagal mengambil session: {str(e)}"}), 500

@app.route("/api/reset", methods=["POST"])
def logical_reset():
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    sid = (data.get("session_id") or "").strip()
    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
        identity = _require_identity(user_id)
        doc = _get_or_create_session(user_id, sid, DEFAULT_SYSTEM_PROMPT, identity)
        checkpoint = {"at": datetime.utcnow().isoformat() + "Z", "note": "logical reset"}
        update_res = sessions_collection.update_one(
            {"_id": doc["_id"]},
            {"$inc": {"resets_count": 1},
             "$push": {"checkpoints": checkpoint},
             "$set": {"updated_at": datetime.utcnow(), "greeted": False}}
        )
        return jsonify({
            "ok": True, "session_id": sid, "checkpoint": checkpoint,
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Gagal reset: {str(e)}"}), 500

@app.route("/api/hard_reset", methods=["POST"])
def hard_reset():
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    sid = (data.get("session_id") or "").strip()
    system_prompt = data.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
    if not user_id or not sid:
        return jsonify({"error": "user_id dan session_id harus disediakan."}), 400
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
        identity = _require_identity(user_id)
        doc = _get_or_create_session(user_id, sid, system_prompt, identity)
        new_messages = [{"role": "system", "content": system_prompt}]
        update_res = sessions_collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"messages": new_messages,
                      "updated_at": datetime.utcnow(),
                      "identity": {"type": identity["type"], "name": identity["name"]},
                      "greeted": False}}
        )
        return jsonify({
            "ok": True, "session_id": sid,
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Gagal hard reset: {str(e)}"}), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Alur:
    1) Pastikan token Admin API siap (ensure_token).
    2) Validasi user_id via API Talent/Company.
    3) Simpan/ambil sesi chat di Mongo.
    4) message kosong → ringkasan/welcome + greeting sekali per sesi.
    5) message ada → kirim ke GPT dengan tools (tools_registry), eksekusi tool-calls, simpan hasil.
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

    # 1) Pastikan token Admin API
    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}", "session_id": sid}), 401

    # 2) Validasi identitas via API Admin
    try:
        identity = _require_identity(user_id)
    except ValueError as ve:
        return jsonify({"error": str(ve), "session_id": sid}), 400

    # 3) Ambil/buat sesi
    try:
        session_doc = _get_or_create_session(user_id, sid, system_prompt, identity)
        if session_doc.get("identity", {}) != {"type": identity["type"], "name": identity["name"]}:
            sessions_collection.update_one(
                {"_id": session_doc["_id"]},
                {"$set": {"identity": {"type": identity["type"], "name": identity["name"]}}}
            )
            session_doc["identity"] = {"type": identity["type"], "name": identity["name"]}
        messages = session_doc.get("messages", [])
        greeted = bool(session_doc.get("greeted", False))
        name_for_greet = identity["name"] or user_id
    except Exception as e:
        return jsonify({"error": f"Gagal memuat sesi: {str(e)}"}), 500

    def maybe_prefix_greeting(text: str) -> str:
        nonlocal greeted
        if not greeted:
            text = f"{_greeting_prefix(name_for_greet)}\n\n{text}".strip()
            greeted = True
        return text

    # 4) message kosong → summary/welcome
    if not user_msg:
        if len(messages) > 1:
            history_for_summary = _trim_for_model(messages[:])
            history_for_summary.append({"role": "user", "content": "Ringkas seluruh percakapan sebelumnya dalam 1 kalimat bahasa Indonesia."})
            try:
                summary_completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=history_for_summary,
                    temperature=0.2,
                )
                summary_text = summary_completion.choices[0].message.content or ""
                if not summary_text.strip():
                    last_user_msgs = [m["content"] for m in messages if m.get("role") == "user"][-2:]
                    joined = "; ".join(last_user_msgs) if last_user_msgs else "Percakapan singkat."
                    summary_text = f"Ringkasan singkat: {joined}"
                summary_text = maybe_prefix_greeting(summary_text)
                messages.append({"role": "assistant", "content": summary_text})
                update_res = sessions_collection.update_one(
                    {"_id": session_doc["_id"]},
                    {"$set": {"messages": messages, "updated_at": datetime.utcnow(), "greeted": greeted}}
                )
                return jsonify({
                    "session_id": sid,
                    "messages": messages,
                    "answer": summary_text,
                    "identity": {"type": identity["type"], "name": identity["name"]},
                    "db_updated": update_res.acknowledged,
                    "db_match": update_res.matched_count,
                    "db_modified": update_res.modified_count
                })
            except Exception as e:
                return jsonify({"error": f"Gagal merangkum chat: {str(e)}"}), 500
        else:
            welcome_msg = maybe_prefix_greeting("Sesi baru dimulai. Silakan ketik pesan Anda untuk memulai percakapan.")
            messages.append({"role": "assistant", "content": welcome_msg})
            update_res = sessions_collection.update_one(
                {"_id": session_doc["_id"]},
                {"$set": {"messages": messages, "updated_at": datetime.utcnow(), "greeted": greeted}}
            )
            return jsonify({
                "session_id": sid,
                "messages": messages,
                "answer": welcome_msg,
                "identity": {"type": identity["type"], "name": identity["name"]},
                "db_updated": update_res.acknowledged,
                "db_match": update_res.matched_count,
                "db_modified": update_res.modified_count
            })

    # 5) Ada pesan user → kirim ke LLM + tools
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
            assistant_msg = {
                "role": "assistant",
                "content": resp_msg.content or None,
                "tool_calls": [
                    {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

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
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": fname, "content": result_json})

            second = client.chat.completions.create(
                model="gpt-4o",
                messages=_trim_for_model(messages),
                temperature=0.2,
            )
            final_text = second.choices[0].message.content or ""
        else:
            final_text = resp_msg.content or ""

        if not session_doc.get("greeted"):
            final_text = f"{_greeting_prefix(name_for_greet)}\n\n{final_text}".strip()

        messages.append({"role": "assistant", "content": final_text})
        update_res = sessions_collection.update_one(
            {"_id": session_doc["_id"]},
            {"$set": {"messages": messages, "updated_at": datetime.utcnow(), "greeted": True}}
        )

        return jsonify({
            "session_id": sid,
            "answer": final_text,
            "tool_runs": tool_runs,
            "messages": messages,
            "identity": {"type": identity["type"], "name": identity["name"]},
            "db_updated": update_res.acknowledged,
            "db_match": update_res.matched_count,
            "db_modified": update_res.modified_count
        })
    except Exception as e:
        return jsonify({"error": f"Gagal memproses: {type(e).__name__}", "session_id": sid}), 500

@app.route("/api/info", methods=["GET"])
def info():
    """
    Untuk tombol Information:
    - Validasi user_id via API Admin.
    - Jika type=talent → ambil profil talent (raw) dan job-openings via API.
    - Minta GPT lakukan ranking rekomendasi.
    - Kembalikan messages (string siap tampil) + latest_openings (raw) + model_result (detail skor).
    """
    user_id = request.args.get("user_id", "").strip()
    limit = int(request.args.get("limit", "30"))
    limit = max(1, min(limit, 100))
    if not user_id:
        return jsonify({"error": "user_id harus disediakan."}), 400

    try:
        incoming_token = _extract_bearer_token(request)
        ensure_token(preferred_token=incoming_token if incoming_token else None)
        identity = _require_identity(user_id)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Auth Admin API gagal: {str(e)}"}), 401

    # Ambil profil talent
    talent_data = None
    if identity["type"] == "talent":
        # Kalau raw belum detail, ambil ulang by id kalau ada
        t_raw = identity["raw"] or {}
        tid = t_raw.get("id")
        if tid:
            try:
                talent_data = get_talent_detail(int(tid))
            except Exception:
                talent_data = t_raw
        else:
            talent_data = t_raw
    else:
        # Jika login sebagai company, butuh talent_id eksplisit
        talent_id = request.args.get("talent_id", "").strip()
        if not talent_id:
            return jsonify({"error": "Untuk company, sertakan talent_id pada query untuk rekomendasi."}), 400
        tid = _parse_int(talent_id)
        if tid is None:
            return jsonify({"error": "talent_id harus berupa angka."}), 400
        try:
            talent_data = get_talent_detail(tid)
        except Exception:
            return jsonify({"error": "Talent tidak ditemukan pada API Admin."}), 404

    # Ambil job openings
    try:
        openings = list_job_openings(page=1, per_page=limit, search=None) or []
        # Jika API Anda mengembalikan dict {data: [...]}, normalisasi:
        if isinstance(openings, dict) and "data" in openings and isinstance(openings["data"], list):
            openings = openings["data"]
        if not isinstance(openings, list):
            openings = []
    except Exception:
        return jsonify({"error": "Gagal mengambil job openings dari API Admin."}), 502

    ranking = _llm_rank_jobs(talent_data or {}, openings)
    messages = []
    for rec in ranking[:10]:
        title = rec.get("title") or "(tanpa judul)"
        compn = rec.get("company_name") or "(perusahaan)"
        score = rec.get("score") if isinstance(rec.get("score"), (int, float)) else "-"
        reason = rec.get("reason") or ""
        messages.append(f"Rekomendasi: {title} di {compn} — skor {score}. Alasan: {reason}")

    if not messages:
        messages = ["Informasi umum: tidak ada lowongan yang cocok saat ini."]

    return jsonify({
        "identity": {"type": identity["type"], "name": identity["name"]},
        "talent": {
            "name": _display_name_from_obj(talent_data or {}, "talent"),
            "skills": _extract_skills_from_talent(talent_data or {})
        },
        "messages": messages,
        "latest_openings": openings[:limit],
        "model_result": ranking
    })

# =========================
# Main
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True)
