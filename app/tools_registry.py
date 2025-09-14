#tools_registry.py
import json
import requests
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

# ===== Helper injection (tanpa import app.py untuk hindari circular) =====
_helpers = {
    "get_or_create_chat_doc": None,
    "append_session": None,
    "DEFAULT_SYSTEM_PROMPT": "Anda adalah asisten AI."
}

def set_helpers(get_or_create_chat_doc, append_session, default_system_prompt):
    _helpers["get_or_create_chat_doc"] = get_or_create_chat_doc
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
    # PEMBARUAN: Impor fungsi baru
    get_offer_details, retrieve_data
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

def prepare_talent_message(talent_id: int, talent_name: str, sender_name: str, proposed_message: str):
    """
    Menyiapkan draf pesan untuk dikirim ke talent.
    Fungsi ini sekarang bisa mengambil detail talent untuk konteks tambahan.
    """
    talent_details = get_talent_detail(talent_id=talent_id)
    skills = talent_details.get("skills", [])
    
    return {
        "status": "waiting_confirmation",
        "talent_id": talent_id,
        "talent_name": talent_name,
        "sender_name": sender_name,
        "message_draft": proposed_message,
        "confirmation_question": (
            f"Baik, saya akan mengirim pesan ke {talent_name} dari {sender_name}. "
            f"Apakah pesan berikut sudah sesuai: '{proposed_message}'? (Ya/Tidak/Ubah)"
        )
    }

def start_chat_with_talent(user_id: str, initial_message: str):
    """
    Membuat sesi chat baru di MongoDB untuk seorang talent spesifik.
    Format nama dokumen akan menjadi 'id@nama_dengan_underscore'.
    """
    try:
        if not _helpers["get_or_create_chat_doc"] or not _helpers["append_session"]:
            return {"success": False, "error": "helpers belum diinisialisasi dari app.py"}

        document_name = user_id

        _helpers["get_or_create_chat_doc"](name=document_name)

        new_session_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        messages = [
            {"role": "system", "content": _helpers["DEFAULT_SYSTEM_PROMPT"], "timestamp": created_at.isoformat()},
            {"role": "assistant", "content": initial_message, "timestamp": created_at.isoformat()},
        ]

        _helpers["append_session"](
            name=document_name,
            session_id=new_session_id,
            created_at=created_at,
            messages=messages,
            title="Percakapan Awal"
        )

        return {
            "success": True,
            "message": f"Sesi chat baru dengan {document_name} berhasil dibuat.",
            "session_id": new_session_id
        }
    except Exception as e:
        print(f"!!! ERROR di dalam TOOL start_chat_with_talent: {e}")
        return {"success": False, "error": str(e)}

def list_job_openings_enriched(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    """
    Ambil daftar lowongan lalu lengkapi dengan company_name berdasarkan company_id.
    Selalu mengembalikan struktur { "data": [ ... ], "pagination": ...? } agar konsisten.
    """
    try:
        raw_openings = list_job_openings(page=page, per_page=per_page, search=search)
    except Exception as e:
        return {"error": f"Gagal memuat lowongan: {str(e)}"}

    items = []
    # Cek jika outputnya dictionary dengan pagination
    if isinstance(raw_openings, dict) and 'data' in raw_openings:
        items = raw_openings.get("data", [])
    # Cek jika outputnya hanya list
    elif isinstance(raw_openings, list):
        items = raw_openings
    else:
        return {"error": "Format data lowongan tidak dikenali."}

    company_cache = {}
    enriched_data = []
    for job in items:
        company_id = job.get('company_id')
        company_name = "Perusahaan tidak diketahui"
        if company_id:
            if company_id in company_cache:
                company_name = company_cache[company_id]
            else:
                try:
                    company_details = get_company_detail(company_id=company_id)
                    if company_details and 'name' in company_details:
                        company_name = company_details['name']
                        company_cache[company_id] = company_name
                except Exception:
                    pass # Biarkan nama default jika gagal fetch
        
        job['company_name'] = company_name
        enriched_data.append(job)

    # Menyesuaikan kembali format output jika ada pagination
    if isinstance(raw_openings, dict):
        raw_openings['data'] = enriched_data
        return raw_openings
    else:
        return enriched_data
    
def initiate_contact(talent_id: int, user_id: int, talent_name: str, job_opening_id: int, initial_message: str):
    """
    Mendaftarkan talent sebagai kandidat untuk sebuah lowongan DAN memulai sesi chat baru.
    Ini adalah tool utama untuk kontak awal.
    Membutuhkan user_id milik talent dgn format "id@user_name"
    """
    try:
        # Langkah 1: Daftarkan sebagai kandidat
        candidate_result = create_candidate(talent_id=talent_id, job_opening_id=job_opening_id, status=1) # Status 1 = Dihubungi
        if "error" in (candidate_result or {}):
             return {"success": False, "error": f"Gagal membuat kandidat: {candidate_result['error']}"}

        # Langkah 2: Jika berhasil, mulai sesi chat
        chat_result = start_chat_with_talent(user_id=user_id, initial_message=initial_message)
        if not chat_result.get("success"):
            return {"success": False, "error": f"Kandidat dibuat, tapi gagal memulai chat: {chat_result['error']}"}

        return {"success": True, "message": f"Talent {user_id} berhasil didaftarkan sebagai kandidat dan pesan pertama telah dikirim."}

    except Exception as e:
        return {"success": False, "error": f"Terjadi kesalahan tak terduga: {str(e)}"}


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
                    "user_id": {"type": "integer", "description": "User ID dari talent."},
                    "talent_id": {"type": "integer", "description": "ID dari talent yang dihubungi."},
                    "talent_name": {"type": "string", "description": "Nama dari talent yang dihubungi."},
                    "job_opening_id": {"type": "integer", "description": "ID dari lowongan pekerjaan yang relevan."},
                    "initial_message": {"type": "string", "description": "Isi pesan pertama yang sudah disetujui pengguna."}
                },
                "required": ["talent_id", "talent_name", "job_opening_id", "initial_message"]
            }
        }
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "list_job_openings_enriched",
    #         "description": "Mencari dan menampilkan daftar lowongan pekerjaan, lengkap dengan nama perusahaan.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "page": {"type": "integer", "default": 1, "description": "Nomor halaman."},
    #                 "per_page": {"type": "integer", "default": 10, "description": "Jumlah item per halaman."},
    #                 "search": {"type": "string", "description": "Kata kunci pencarian untuk judul lowongan."}
    #             }
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_offer_details",
    #         "description": "Mengambil detail penawaran kerja (gaji, tunjangan, dll) untuk seorang kandidat berdasarkan ID kandidat.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "candidate_id": {"type": "integer", "description": "ID dari kandidat yang akan diperiksa penawarannya."}
    #             },
    #             "required": ["candidate_id"]
    #         }
    #     }
    # },
    # ===== TALENT =====
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "list_talent",
    #     "description": "List talents with optional search & pagination.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "page": {"type": "integer", "default": 1},
    #         "per_page": {"type": "integer", "default": 10},
    #         "search": {"type": "string"}
    #       }
    #     }
    #   }
    # },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "get_talent_detail",
    #     "description": "Get a talent by ID.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"talent_id": {"type": "integer"}},
    #       "required": ["talent_id"]
    #     }
    #   }
    # },
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

    # ===== CANDIDATES =====
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "list_candidates",
    #     "description": "List candidates.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "page": {"type": "integer", "default": 1},
    #         "per_page": {"type": "integer", "default": 10},
    #         "search": {"type": "string"}
    #       }
    #     }
    #   }
    # },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "get_candidate_detail",
    #     "description": "Get candidate by ID.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"candidate_id": {"type": "integer"}},
    #       "required": ["candidate_id"]
    #     }
    #   }
    # },
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

    # ===== COMPANIES =====
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "list_companies",
    #     "description": "List companies.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "page": {"type": "integer", "default": 1},
    #         "per_page": {"type": "integer", "default": 10},
    #         "search": {"type": "string"}
    #       }
    #     }
    #   }
    # },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "get_company_detail",
    #     "description": "Get company by ID.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"company_id": {"type": "integer"}},
    #       "required": ["company_id"]
    #     }
    #   }
    # },
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

    # ===== COMPANY PROPERTIES =====
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "list_company_properties",
    #     "description": "List company properties.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "page": {"type": "integer", "default": 1},
    #         "per_page": {"type": "integer", "default": 10},
    #         "search": {"type": "string"}
    #       }
    #     }
    #   }
    # },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "get_company_property_detail",
    #     "description": "Get company property by ID.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"prop_id": {"type": "integer"}},
    #       "required": ["prop_id"]
    #     }
    #   }
    # },
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

    # ===== JOB OPENINGS =====
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "list_job_openings",
    #     "description": "List job openings.",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {
    #         "search": {"type": "string"}
    #       }
    #     }
    #   }
    # },
    {
      "type": "function",
      "function": {
        "name": "get_job_opening_detail",
        "description": "Get job opening by ID.",
        "parameters": {
          "type": "object",
          "properties": {"opening_id": {"type": "integer"}},
          "required": ["opening_id"]
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
    # "get_offer_details": get_offer_details,
    # "list_job_openings_enriched": list_job_openings_enriched, 
    # "list_talent": list_talent,
    # "get_talent_detail": get_talent_detail,
    "create_talent": create_talent,
    "update_talent": update_talent,
    "delete_talent": delete_talent,
    # "list_candidates": list_candidates,
    # "get_candidate_detail": get_candidate_detail,
    "create_candidate": create_candidate,
    "update_candidate": update_candidate,
    "delete_candidate": delete_candidate,
    # "list_companies": list_companies,
    # "get_company_detail": get_company_detail,
    "create_company": create_company,
    "update_company": update_company,
    "delete_company": delete_company,
    # "list_company_properties": list_company_properties,
    # "get_company_property_detail": get_company_property_detail,
    "create_company_property": create_company_property,
    "update_company_property": update_company_property,
    "delete_company_property": delete_company_property,
    # "list_job_openings": list_job_openings,
    # "get_job_opening_detail": get_job_opening_detail,
    "create_job_opening": create_job_opening,
    "update_job_opening": update_job_opening,
    "delete_job_opening": delete_job_opening,
    "retrieve_data": retrieve_data,
}
