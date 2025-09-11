# tools_registry.py
import json
import requests
from uuid import uuid4
from datetime import datetime, timezone

# ===== Helper injection (tanpa import app.py untuk hindari circular) =====
_helpers = {
    "get_or_create_name_doc": None,
    "append_session": None,
    "DEFAULT_SYSTEM_PROMPT": "Anda adalah asisten AI."
}

def set_helpers(get_or_create_name_doc, append_session, default_system_prompt):
    _helpers["get_or_create_name_doc"] = get_or_create_name_doc
    _helpers["append_session"] = append_session
    _helpers["DEFAULT_SYSTEM_PROMPT"] = default_system_prompt

# ===== Impor fungsi-fungsi API client Anda =====
from api_client import (
    # talent
    list_talent, get_talent_detail, create_talent, update_talent, delete_talent,
    # candidates
    list_candidates, get_candidate_detail, create_candidate, update_candidate, delete_candidate,
    # companies
    list_companies, get_company_detail, create_company, update_company, delete_company,
    # company-properties
    list_company_properties, get_company_property_detail, create_company_property, update_company_property, delete_company_property,
    # job-openings
    list_job_openings, get_job_opening_detail, create_job_opening, update_job_opening, delete_job_opening,
)

# URL API Laravel Anda (Ganti dengan URL yang sebenarnya)
LARAVEL_API_BASE = "http://127.0.0.1:8000/api"

# ========== FUNGSI-FUNGSI BARU UNTUK INTEGRASI LARAVEL ==========
def get_talents():
    try:
        response = requests.get(f"{LARAVEL_API_BASE}/talents", timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Gagal menghubungi API Laravel: {str(e)}"}

def prepare_talent_message(talent_name: str, proposed_message: str):
    """
    Menyiapkan draf pesan untuk dikirim ke talent dan meminta konfirmasi dari user.
    Fungsi ini TIDAK mengirim apapun, hanya memformat pertanyaan konfirmasi.
    """
    return {
        "status": "waiting_confirmation",
        "talent_name": talent_name,
        "message_draft": proposed_message,
        "confirmation_question": (
            f"Baik, saya akan mengirim pesan ke {talent_name}. "
            f"Apakah pesan berikut sudah sesuai: '{proposed_message}'? (Ya/Tidak/Ubah)"
        )
    }

def start_chat_with_talent(talent_id: str, talent_name: str, initial_message: str):
    try:
        if not _helpers["get_or_create_name_doc"] or not _helpers["append_session"]:
            return {"success": False, "error": "helpers belum diinisialisasi dari app.py"}

        _helpers["get_or_create_name_doc"](name=talent_name, userid=talent_id)

        new_session_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        messages = [
            {"role": "system", "content": _helpers["DEFAULT_SYSTEM_PROMPT"], "timestamp": created_at.isoformat()},
            {"role": "assistant", "content": initial_message, "timestamp": created_at.isoformat()},
        ]

        _helpers["append_session"](
            name=talent_name,
            session_id=new_session_id,
            created_at=created_at,
            messages=messages,
            title="Percakapan awal"
        )

        return {
            "success": True,
            "message": f"Sesi chat baru dengan {talent_name} berhasil dibuat.",
            "session_id": new_session_id
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== DEFINISI SEMUA TOOLS (LAMA + BARU) ==========
tools = [
    
    # ===== TOOLS BARU INTEGRASI LARAVEL =====
     {
        "type": "function",
        "function": {
            "name": "prepare_talent_message",
            "description": "Gunakan fungsi ini SEBELUM mengirim pesan ke talent. Fungsi ini menyiapkan draf pesan dan meminta konfirmasi dari pengguna. JANGAN gunakan start_chat_with_talent secara langsung tanpa konfirmasi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "talent_name": {"type": "string", "description": "Nama talent target."},
                    "proposed_message": {"type": "string", "description": "Draf isi pesan yang disarankan oleh AI untuk dikirim."}
                },
                "required": ["talent_name", "proposed_message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_talents",
            "description": "Gunakan fungsi ini untuk mendapatkan daftar semua talent yang tersedia dari database utama (Laravel).",
            "parameters": {"type": "object", "properties": {}}
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_chat_with_talent",
            "description": "Gunakan fungsi ini HANYA SETELAH pengguna memberikan konfirmasi (menjawab 'Ya') untuk mengirim pesan yang sudah disiapkan. Fungsi ini akan membuat sesi chat baru di MongoDB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "talent_id": {"type": "string"},
                    "talent_name": {"type": "string"},
                    "initial_message": {"type": "string"}
                },
                "required": ["talent_id", "talent_name", "initial_message"]
            }
        }
    },
    

    # ===== TALENT =====
    {
        "type": "function",
        "function": {
            "name": "list_talent",
            "description": "Cari/tampilkan daftar talent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "default": 1},
                    "per_page": {"type": "integer", "default": 10},
                    "search": {"type": "string"}
                }
            }
        }
    },
    {"type": "function", "function": { "name": "get_talent_detail", "description": "Detail talent berdasarkan ID.", "parameters": { "type": "object", "properties": {"talent_id": {"type": "integer"}}, "required": ["talent_id"]}}},
    {"type": "function", "function": { "name": "create_talent", "description": "Buat talent baru.", "parameters": { "type": "object", "properties": { "name": {"type": "string"}, "position": {"type": "string"}, "birthdate": {"type": "string"}, "summary": {"type": "string"}, "skills": {"type": "array", "items": {"type": "string"}}, "educations": { "type": "array", "items": { "type": "object", "properties": { "school": {"type": "string"}, "degree": {"type": "string"}, "year": {"type": "integer"} } } } }, "required": ["name","position","birthdate","summary"]}}},
    {"type": "function", "function": { "name": "update_talent", "description": "Perbarui talent.", "parameters": { "type": "object", "properties": { "talent_id": {"type": "integer"}, "name": {"type": "string"}, "position": {"type": "string"}, "birthdate": {"type": "string"}, "summary": {"type": "string"}, "skills": {"type": "array", "items": {"type": "string"}}, "educations": { "type": "array", "items": { "type": "object", "properties": { "school": {"type": "string"}, "degree": {"type": "string"}, "year": {"type": "integer"} } } } }, "required": ["talent_id"]}}},
    {"type": "function", "function": { "name": "delete_talent", "description": "Hapus talent.", "parameters": { "type": "object", "properties": {"talent_id": {"type": "integer"}}, "required": ["talent_id"]}}},

    # ===== CANDIDATES =====
    {"type": "function", "function": { "name": "list_candidates", "description": "Daftar kandidat yang melamar.", "parameters": { "type": "object", "properties": { "page": {"type": "integer", "default": 1}, "per_page": {"type": "integer", "default": 10}, "search": {"type": "string"} }}}},
    {"type": "function", "function": { "name": "get_candidate_detail", "description": "Detail kandidat.", "parameters": { "type": "object", "properties": {"candidate_id": {"type": "integer"}}, "required": ["candidate_id"]}}},
    {"type": "function", "function": { "name": "create_candidate", "description": "Daftarkan talent ke lowongan.", "parameters": { "type": "object", "properties": { "talent_id": {"type": "integer"}, "job_opening_id": {"type": "integer"}, "status": {"type": "integer"}, "regist_at": {"type": "string"}, "interview_schedule": {"type": "string"}, "notified_at": {"type": "string"} }, "required": ["talent_id","job_opening_id"]}}},
    {"type": "function", "function": { "name": "update_candidate", "description": "Perbarui kandidat.", "parameters": { "type": "object", "properties": { "candidate_id": {"type": "integer"}, "talent_id": {"type": "integer"}, "job_opening_id": {"type": "integer"}, "status": {"type": "integer"}, "regist_at": {"type": "string"}, "interview_schedule": {"type": "string"}, "notified_at": {"type": "string"} }, "required": ["candidate_id"]}}},
    {"type": "function", "function": { "name": "delete_candidate", "description": "Hapus kandidat.", "parameters": { "type": "object", "properties": {"candidate_id": {"type": "integer"}}, "required": ["candidate_id"]}}},

    # ===== COMPANIES & PROPERTIES =====
    {"type": "function", "function": { "name": "list_companies", "description": "Daftar perusahaan.", "parameters": { "type": "object", "properties": { "page": {"type": "integer", "default": 1}, "per_page": {"type": "integer", "default": 10}, "search": {"type": "string"} }}}},
    {"type": "function", "function": { "name": "get_company_detail", "description": "Detail perusahaan.", "parameters": { "type": "object", "properties": {"company_id": {"type": "integer"}}, "required": ["company_id"]}}},
    {"type": "function", "function": { "name": "create_company", "description": "Buat perusahaan baru.", "parameters": { "type": "object", "properties": { "name": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "integer"} }, "required": ["name"]}}},
    {"type": "function", "function": { "name": "update_company", "description": "Perbarui perusahaan.", "parameters": { "type": "object", "properties": { "company_id": {"type": "integer"}, "name": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "integer"} }, "required": ["company_id"]}}},
    {"type": "function", "function": { "name": "delete_company", "description": "Hapus perusahaan.", "parameters": { "type": "object", "properties": {"company_id": {"type": "integer"}}, "required": ["company_id"]}}},
    {"type": "function", "function": { "name": "list_company_properties", "description": "Daftar properti perusahaan.", "parameters": { "type": "object", "properties": { "page": {"type": "integer", "default": 1}, "per_page": {"type": "integer", "default": 10}, "search": {"type": "string"} }}}},
    {"type": "function", "function": { "name": "get_company_property_detail", "description": "Detail properti perusahaan.", "parameters": { "type": "object", "properties": {"prop_id": {"type": "integer"}}, "required": ["prop_id"]}}},
    {"type": "function", "function": { "name": "create_company_property", "description": "Buat properti perusahaan.", "parameters": { "type": "object", "properties": { "company_id": {"type": "integer"}, "key": {"type": "string"}, "value": {"type": "string"} }, "required": ["company_id","key","value"]}}},
    {"type": "function", "function": { "name": "update_company_property", "description": "Perbarui properti perusahaan.", "parameters": { "type": "object", "properties": { "prop_id": {"type": "integer"}, "company_id": {"type": "integer"}, "key": {"type": "string"}, "value": {"type": "string"} }, "required": ["prop_id"]}}},
    {"type": "function", "function": { "name": "delete_company_property", "description": "Hapus properti perusahaan.", "parameters": { "type": "object", "properties": {"prop_id": {"type": "integer"}}, "required": ["prop_id"]}}},

    # ===== JOB OPENINGS =====
    {"type": "function", "function": { "name": "list_job_openings", "description": "Daftar lowongan pekerjaan.", "parameters": { "type": "object", "properties": { "page": {"type": "integer", "default": 1}, "per_page": {"type": "integer", "default": 10}, "search": {"type": "string"} }}}},
    {"type": "function", "function": { "name": "get_job_opening_detail", "description": "Detail lowongan berdasarkan ID.", "parameters": { "type": "object", "properties": {"opening_id": {"type": "integer"}}, "required": ["opening_id"]}}},
    {"type": "function", "function": { "name": "create_job_opening", "description": "Buat lowongan pekerjaan baru.", "parameters": { "type": "object", "properties": { "company_id": {"type": "integer"}, "title": {"type": "string"}, "body": {"type": "string"}, "due_date": {"type": "string"}, "status": {"type": "integer"} }, "required": ["company_id","title"]}}},
    {"type": "function", "function": { "name": "update_job_opening", "description": "Perbarui lowongan pekerjaan.", "parameters": { "type": "object", "properties": { "opening_id": {"type": "integer"}, "company_id": {"type": "integer"}, "title": {"type": "string"}, "body": {"type": "string"}, "due_date": {"type": "string"}, "status": {"type": "integer"} }, "required": ["opening_id"]}}},
    {"type": "function", "function": { "name": "delete_job_opening", "description": "Hapus lowongan pekerjaan.", "parameters": { "type": "object", "properties": {"opening_id": {"type": "integer"}}, "required": ["opening_id"]}}}
]

# ========== MAPPING FUNGSI ==========
available_functions = {
    "get_talents": get_talents,
    "prepare_talent_message": prepare_talent_message,
    "start_chat_with_talent": start_chat_with_talent,
    

    "list_talent": list_talent,
    "get_talent_detail": get_talent_detail,
    "create_talent": create_talent,
    "update_talent": update_talent,
    "delete_talent": delete_talent,

    "list_candidates": list_candidates,
    "get_candidate_detail": get_candidate_detail,
    "create_candidate": create_candidate,
    "update_candidate": update_candidate,
    "delete_candidate": delete_candidate,

    "list_companies": list_companies,
    "get_company_detail": get_company_detail,
    "create_company": create_company,
    "update_company": update_company,
    "delete_company": delete_company,

    "list_company_properties": list_company_properties,
    "get_company_property_detail": get_company_property_detail,
    "create_company_property": create_company_property,
    "update_company_property": update_company_property,
    "delete_company_property": delete_company_property,

    "list_job_openings": list_job_openings,
    "get_job_opening_detail": get_job_opening_detail,
    "create_job_opening": create_job_opening,
    "update_job_opening": update_job_opening,
    "delete_job_opening": delete_job_opening,
}
