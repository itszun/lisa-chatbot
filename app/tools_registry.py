#tools_registry.py
# Berisi definisi alat (tools) yang dapat digunakan oleh AI,
# serta fungsi-fungsi pembantu untuk mengakses API Laravel.
import json
import requests
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from openai import OpenAI, RateLimitError
import os


# ===== Helper injection (tanpa import app.py untuk hindari circular) =====
# fungsi helper yang akan diisi dari app.py
# get_or_create_chat_doc, append_session, DEFAULT_SYSTEM_PROMPT
# ini untuk mengakses MongoDB dari dalam tools_registry.py
_helpers = {
    "get_or_create_chat_doc": None,
    "append_session": None,
    "DEFAULT_SYSTEM_PROMPT": "Anda adalah asisten AI."
}

# fungsi set_helpers untuk mengisi helper dari app.py
# dipanggil sekali dari app.py saat startup
# digunakan untuk mengakses MongoDB dari dalam tools_registry.py
# tujuan utamanya adalah agar fungsi start_chat_with_talent dapat membuat sesi chat baru
# tanpa membuat dependensi melingkar antara app.py dan tools_registry.py
def set_helpers(get_or_create_chat_doc, append_session, default_system_prompt):
    _helpers["get_or_create_chat_doc"] = get_or_create_chat_doc
    _helpers["append_session"] = append_session
    _helpers["DEFAULT_SYSTEM_PROMPT"] = default_system_prompt

# ===== Impor fungsi-fungsi API client Anda =====
# Pastikan api_client.py ada di direktori yang sama
# dan berisi fungsi-fungsi untuk berinteraksi dengan API Laravel Anda
# Contoh fungsi: list_talent, get_talent_detail, create_talent, dll.
from api_client import (
    # talent
    create_talent, update_talent, delete_talent,
    # candidates
    create_candidate, update_candidate, delete_candidate,
    # companies
    create_company, update_company, delete_company,
    # company-properties
    create_company_property, update_company_property, delete_company_property,
    # job-openings
    create_job_opening, update_job_opening, delete_job_opening,
    retrieve_data
)

def initiate_contact(talent_id: int, talent_name: str, chat_user_id: int, job_opening_id: int, initial_message: str):
    from prompt import TemplatePrompt
    """
    Mendaftarkan talent sebagai kandidat untuk sebuah lowongan DAN memulai sesi chat baru.
    Ini adalah tool utama untuk kontak awal.
    Membutuhkan chat_user_id milik talent dgn format "id@user_name"
    """
    try:
        print(f"Attempt to initiate contact to {chat_user_id} [{talent_id}/{talent_name}] untuk {job_opening_id}")
        # Langkah 1: Daftarkan sebagai kandidat
        candidate_result = create_candidate(talent_id=talent_id, job_opening_id=job_opening_id, status=1) # Status 1 = Dihubungi
        if "error" in (candidate_result or {}):
             return {"success": False, "error": f"Gagal membuat kandidat: {candidate_result['error']}"}

        # Langkah 2: Jika berhasil, mulai sesi chat
        chat_result = start_new_chat(
            chat_user_id=chat_user_id, 
            system_prompt=TemplatePrompt.TALENT_SCOUTING_SCREENING,
            initial_message=initial_message)
        if not chat_result.get("success"):
            return {"success": False, "error": f"Kandidat dibuat, tapi gagal memulai chat: {chat_result['error']}"}

        return {"success": True, "message": f"Talent {chat_user_id} berhasil didaftarkan sebagai kandidat dan pesan pertama telah dikirim."}

    except Exception as e:
        return {"success": False, "error": f"Terjadi kesalahan tak terduga: {str(e)}"}

def start_new_chat(chat_user_id: str, system_prompt: str, initial_message: str):
  try:
    _helpers["get_or_create_chat_doc"](
        userid=chat_user_id, 
        name=chat_user_id
    )

    new_session_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": initial_message},
    ]
    
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY belum diisi.")
    client = OpenAI(api_key=OPENAI_API_KEY)

    title = (client.chat.completions.create(
            model="gpt-4o", messages=[
                  *messages,
                  {"role": "user", "content": f"Buat judul singkat (maksimal 5 kata) untuk percakapan ini"}
                ],
            temperature=0.2, max_tokens=20
        ).choices[0].message.content or "Percakapan Baru").strip().replace('"', '')
    
    _helpers["append_session"](
        name=chat_user_id,
        session_id=new_session_id,
        created_at=created_at,
        messages=messages,
        title=title
    )
  
    return {
        "success": True,
        "message": f"Sesi chat baru dengan {chat_user_id} berhasil dibuat.",
        "session_id": new_session_id
    }
  
  except Exception as e:
      import traceback
      traceback.print_exc() 
      return {"success": False, "error": str(e)}

# ========== DEFINISI SEMUA TOOLS (LAMA + BARU) ==========
tools = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_data",
            "description": "Gunakan tool ini untuk mendapatkan data terkait Job Opening, Talent, Company, User, dan Candidate",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_name": {"type": "string", "description": "either talent_pool, job_openings, users, company, or candidates"},
                    "search": {"type":"string", "description": "Any keyword to search. Using semantic search"}
                }
            },
            "required": ["collection_name", "search"]
        }
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_contact",
            "description": "Gunakan tool ini setelah pengguna menyetujui draf pesan untuk menghubungi talent. Tool ini akan mendaftarkan talent sebagai kandidat DAN memulai sesi chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_user_id": {"type": "string", "description": "chat_user_id dari talent atau bisa ditemukan di user.chat_user_id"},
                    "talent_id": {"type": "integer", "description": "ID dari talent yang dihubungi."},
                    "talent_name": {"type": "string", "description": "Nama dari talent yang dihubungi."},
                    "job_opening_id": {"type": "integer", "description": "ID dari lowongan pekerjaan yang relevan."},
                    "initial_message": {"type": "string", "description": "Isi pesan pertama yang sudah disetujui pengguna."}
                },
                "required": ["talent_id", "talent_name", "job_opening_id", "initial_message"]
            }
        }
    },
    {
      "type": "function",
      "function": {
        "name": "create_talent",
        "description": "Create a new talent.",
        "parameters": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "position": {"type": "string"},
            "birthdate": {"type": "string", "description": "YYYY-MM-DD"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "educations": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "school": {"type": "string"},
                  "degree": {"type": "string"},
                  "year": {"type": "integer"}
                }
              }
            }
          },
          "required": ["name","position","birthdate","summary"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_talent",
        "description": "Update talent fields.",
        "parameters": {
          "type": "object",
          "properties": {
            "talent_id": {"type": "integer"},
            "name": {"type": "string"},
            "position": {"type": "string"},
            "birthdate": {"type": "string"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "educations": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "school": {"type": "string"},
                  "degree": {"type": "string"},
                  "year": {"type": "integer"}
                }
              }
            }
          },
          "required": ["talent_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_talent",
        "description": "Delete a talent by ID.",
        "parameters": {
          "type": "object",
          "properties": {"talent_id": {"type": "integer"}},
          "required": ["talent_id"]
        }
      }
    },

    {
      "type": "function",
      "function": {
        "name": "create_candidate",
        "description": "Create candidate. Needs valid talent_id and job_opening_id.",
        "parameters": {
          "type": "object",
          "properties": {
            "talent_id": {"type": "integer"},
            "job_opening_id": {"type": "integer"},
            "status": {"type": "integer"},
            "regist_at": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
            "interview_schedule": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
            "notified_at": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}
          },
          "required": ["talent_id","job_opening_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_candidate",
        "description": "Update candidate fields.",
        "parameters": {
          "type": "object",
          "properties": {
            "candidate_id": {"type": "integer"},
            "talent_id": {"type": "integer"},
            "job_opening_id": {"type": "integer"},
            "status": {"type": "integer"},
            "regist_at": {"type": "string"},
            "interview_schedule": {"type": "string"},
            "notified_at": {"type": "string"}
          },
          "required": ["candidate_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_candidate",
        "description": "Delete candidate.",
        "parameters": {
          "type": "object",
          "properties": {"candidate_id": {"type": "integer"}},
          "required": ["candidate_id"]
        }
      }
    },

    {
      "type": "function",
      "function": {
        "name": "create_company",
        "description": "Create company.",
        "parameters": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["name"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_company",
        "description": "Update company.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["company_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_company",
        "description": "Delete company.",
        "parameters": {
          "type": "object",
          "properties": {"company_id": {"type": "integer"}},
          "required": ["company_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_company_property",
        "description": "Create company property.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "key": {"type": "string"},
            "value": {"type": "string"}
          },
          "required": ["company_id","key","value"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_company_property",
        "description": "Update company property.",
        "parameters": {
          "type": "object",
          "properties": {
            "prop_id": {"type": "integer"},
            "company_id": {"type": "integer"},
            "key": {"type": "string"},
            "value": {"type": "string"}
          },
          "required": ["prop_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_company_property",
        "description": "Delete company property.",
        "parameters": {
          "type": "object",
          "properties": {"prop_id": {"type": "integer"}},
          "required": ["prop_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_job_opening",
        "description": "Create job opening.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            "status": {"type": "integer"}
          },
          "required": ["company_id","title"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_job_opening",
        "description": "Update job opening.",
        "parameters": {
          "type": "object",
          "properties": {
            "opening_id": {"type": "integer"},
            "company_id": {"type": "integer"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "due_date": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["opening_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_job_opening",
        "description": "Delete job opening.",
        "parameters": {
          "type": "object",
          "properties": {"opening_id": {"type": "integer"}},
          "required": ["opening_id"]
        }
      }
    }
]

# ========== MAPPING FUNGSI ==========
available_functions = {
    "initiate_contact": initiate_contact,
    "create_talent": create_talent,
    "update_talent": update_talent,
    "delete_talent": delete_talent,
    "create_candidate": create_candidate,
    "update_candidate": update_candidate,
    "delete_candidate": delete_candidate,
    "create_company": create_company,
    "update_company": update_company,
    "delete_company": delete_company,
    "create_company_property": create_company_property,
    "update_company_property": update_company_property,
    "delete_company_property": delete_company_property,
    "create_job_opening": create_job_opening,
    "update_job_opening": update_job_opening,
    "delete_job_opening": delete_job_opening,
    "retrieve_data": retrieve_data,
}
