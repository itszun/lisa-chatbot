

from langchain_core.tools import tool
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from openai import OpenAI, RateLimitError
import os

_helpers = {
    "get_or_create_chat_doc": None,
    "append_session": None,
    "DEFAULT_SYSTEM_PROMPT": "Anda adalah asisten AI."
}

def set_helpers(get_or_create_chat_doc, append_session, default_system_prompt):
    _helpers["get_or_create_chat_doc"] = get_or_create_chat_doc
    _helpers["append_session"] = append_session
    _helpers["DEFAULT_SYSTEM_PROMPT"] = default_system_prompt

# Import API client functions
from api_client import (
    create_talent, update_talent, delete_talent,
    create_candidate, update_candidate, delete_candidate,
    create_company, update_company, delete_company,
    create_company_property, update_company_property, delete_company_property,
    create_job_opening, update_job_opening, delete_job_opening,
    retrieve_data, relogin_once_on_401
)

# Start new chat is an internal function, not a tool
def start_new_chat(chat_user_id: str, system_prompt: str, initial_message: str) -> dict:
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

# ========== CONVERTED TOOLS (MENGGUNAKAN DEKORATOR @tool) ==========

@tool
def initiate_contact(talent_id: int, talent_name: str, chat_user_id: str, job_opening_id: int, initial_message: str) -> dict:
    """
    Mendaftarkan talent sebagai kandidat untuk sebuah lowongan DAN memulai sesi chat baru.
    Ini adalah tool utama untuk kontak awal.
    
    Args:
        talent_id (int): ID dari talent yang dihubungi.
        talent_name (str): Nama dari talent yang dihubungi.
        chat_user_id (str): ID chat milik talent, misalnya "id@user_name".
        job_opening_id (int): ID dari lowongan pekerjaan yang relevan.
        initial_message (str): Isi pesan pertama yang sudah disetujui pengguna.
    """
    from prompt import TemplatePrompt
    try:
        print(f"Attempt to initiate contact to {chat_user_id} [{talent_id}/{talent_name}] untuk {job_opening_id}")
        
        # Langkah 1: Daftarkan sebagai kandidat
        candidate_result = create_candidate(talent_id=talent_id, job_opening_id=job_opening_id, status=1)
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

@tool
def retrieve_data(collection_name: str, search: str) -> dict:
    """
    Gunakan tool ini untuk mendapatkan data terkait Job Opening, Talent, Company, User, dan Candidate.

    Args:
        collection_name (str): Nama koleksi data yang akan dicari. Pilihan yang tersedia: "talent_pool", "job_openings", "users", "company", atau "candidates".
        search (str): Kata kunci pencarian.
    """
    from vectordb import Chroma
    print(f"Retrieve Data: search for \"{search}\" on \"{collection_name}\"")
    try:
        collection = Chroma().client().get_or_create_collection(name=collection_name)
        results = collection.query(
            query_texts=[search], # Chroma will embed this for you
            n_results=5 # how many results to return
        )
        return results
    except Exception as error:
        print("Error Tools")
        print(error)
    else:
        return "None"

@tool
def create_talent(name: str, position: str, birthdate: str, summary: str, skills: Optional[List[str]] = None, educations: Optional[List[Dict[str, Any]]] = None) -> dict:
    """
    Create a new talent.
    
    Args:
        name (str): Nama talent.
        position (str): Posisi pekerjaan talent.
        birthdate (str): Tanggal lahir talent dalam format YYYY-MM-DD.
        summary (str): Ringkasan profil talent.
        skills (List[str], optional): Daftar skill.
        educations (List[Dict[str, Any]], optional): Daftar riwayat pendidikan.
    """    
    payload: Dict[str, Any] = {}
    if name is not None: payload["name"] = name
    if position is not None: payload["position"] = position
    if birthdate is not None: payload["birthdate"] = birthdate
    if summary is not None: payload["summary"] = summary
    return relogin_once_on_401(_update_resource, "talent", talent_id, payload)


# ... dan seterusnya, untuk semua fungsi create/update/delete lainnya.
# Lu bisa ikutin format di atas untuk semua fungsi di `api_client.py`.
# Pastikan type hints-nya bener dan docstring-nya jelas ya, Jun.


@tool
def update_talent(talent_id: int, name: Optional[str] = None, position: Optional[str] = None, birthdate: Optional[str] = None, summary: Optional[str] = None, skills: Optional[List[str]] = None, educations: Optional[List[Dict[str, Any]]] = None) -> dict:
    """
    Update an existing talent's fields.

    Args:
        talent_id (int): ID unik dari talent yang akan diperbarui.
        name (str, optional): Nama lengkap talent.
        position (str, optional): Posisi atau jabatan talent saat ini.
        birthdate (str, optional): Tanggal lahir talent dalam format YYYY-MM-DD.
        summary (str, optional): Ringkasan singkat profil atau pengalaman talent.
        skills (List[str], optional): Daftar keahlian atau skill yang dimiliki.
        educations (List[Dict[str, Any]], optional): Daftar riwayat pendidikan talent.
    """
    return update_talent(talent_id, name, position, birthdate, summary, skills, educations)

@tool
def delete_talent(talent_id: int) -> dict:
    """
    Delete a talent by their ID.

    Args:
        talent_id (int): ID unik dari talent yang akan dihapus.
    """
    return delete_talent(talent_id)

# ========== CANDIDATE MANAGEMENT ==========

@tool
def create_candidate(talent_id: int, job_opening_id: int, status: Optional[int] = None, regist_at: Optional[str] = None, interview_schedule: Optional[str] = None, notified_at: Optional[str] = None) -> dict:
    """
    Create a new candidate record, linking a talent to a job opening.

    Args:
        talent_id (int): ID unik dari talent.
        job_opening_id (int): ID unik dari lowongan pekerjaan.
        status (int, optional): Status kandidat (misalnya 1=Dihubungi, 2=Interview).
        regist_at (str, optional): Waktu pendaftaran dalam format YYYY-MM-DD HH:MM:SS.
        interview_schedule (str, optional): Jadwal wawancara dalam format YYYY-MM-DD HH:MM:SS.
        notified_at (str, optional): Waktu pemberitahuan dalam format YYYY-MM-DD HH:MM:SS.
    """
    return create_candidate(talent_id, job_opening_id, status, regist_at, interview_schedule, notified_at)

@tool
def update_candidate(candidate_id: int, talent_id: Optional[int] = None, job_opening_id: Optional[int] = None, status: Optional[int] = None, regist_at: Optional[str] = None, interview_schedule: Optional[str] = None, notified_at: Optional[str] = None) -> dict:
    """
    Update an existing candidate record.

    Args:
        candidate_id (int): ID unik dari kandidat yang akan diperbarui.
        talent_id (int, optional): ID unik dari talent.
        job_opening_id (int, optional): ID unik dari lowongan pekerjaan.
        status (int, optional): Status kandidat (misalnya 1=Dihubungi, 2=Interview).
        regist_at (str, optional): Waktu pendaftaran dalam format YYYY-MM-DD HH:MM:SS.
        interview_schedule (str, optional): Jadwal wawancara dalam format YYYY-MM-DD HH:MM:SS.
        notified_at (str, optional): Waktu pemberitahuan dalam format YYYY-MM-DD HH:MM:SS.
    """
    return update_candidate(candidate_id, talent_id, job_opening_id, status, regist_at, interview_schedule, notified_at)

@tool
def delete_candidate(candidate_id: int) -> dict:
    """
    Delete a candidate record by their ID.

    Args:
        candidate_id (int): ID unik dari kandidat yang akan dihapus.
    """
    return delete_candidate(candidate_id)

# ========== COMPANY MANAGEMENT ==========

@tool
def create_company(name: str, description: Optional[str] = None, status: Optional[int] = None) -> dict:
    """
    Create a new company record.

    Args:
        name (str): Nama perusahaan.
        description (str, optional): Deskripsi singkat tentang perusahaan.
        status (int, optional): Status perusahaan.
    """
    return create_company(name, description, status)

@tool
def update_company(company_id: int, name: Optional[str] = None, description: Optional[str] = None, status: Optional[int] = None) -> dict:
    """
    Update an existing company record.

    Args:
        company_id (int): ID unik dari perusahaan yang akan diperbarui.
        name (str, optional): Nama perusahaan.
        description (str, optional): Deskripsi singkat tentang perusahaan.
        status (int, optional): Status perusahaan.
    """
    return update_company(company_id, name, description, status)

@tool
def delete_company(company_id: int) -> dict:
    """
    Delete a company record by its ID.

    Args:
        company_id (int): ID unik dari perusahaan yang akan dihapus.
    """
    return delete_company(company_id)

# ========== COMPANY PROPERTY MANAGEMENT ==========

@tool
def create_company_property(company_id: int, key: str, value: str) -> dict:
    """
    Create a new property for a company.

    Args:
        company_id (int): ID unik dari perusahaan.
        key (str): Kunci properti (misalnya 'lokasi', 'industri').
        value (str): Nilai dari properti tersebut.
    """
    return create_company_property(company_id, key, value)

@tool
def update_company_property(prop_id: int, company_id: Optional[int] = None, key: Optional[str] = None, value: Optional[str] = None) -> dict:
    """
    Update an existing company property.

    Args:
        prop_id (int): ID unik dari properti yang akan diperbarui.
        company_id (int, optional): ID unik dari perusahaan.
        key (str, optional): Kunci properti.
        value (str, optional): Nilai dari properti tersebut.
    """
    return update_company_property(prop_id, company_id, key, value)

@tool
def delete_company_property(prop_id: int) -> dict:
    """
    Delete a company property by its ID.

    Args:
        prop_id (int): ID unik dari properti yang akan dihapus.
    """
    return delete_company_property(prop_id)

# ========== JOB OPENING MANAGEMENT ==========

@tool
def create_job_opening(company_id: int, title: str, body: Optional[str] = None, due_date: Optional[str] = None, status: Optional[int] = None) -> dict:
    """
    Create a new job opening.

    Args:
        company_id (int): ID unik dari perusahaan yang membuka lowongan.
        title (str): Judul lowongan pekerjaan.
        body (str, optional): Deskripsi lengkap lowongan.
        due_date (str, optional): Tanggal tenggat lamaran dalam format YYYY-MM-DD.
        status (int, optional): Status lowongan (misalnya 1=Aktif, 0=Nonaktif).
    """
    return create_job_opening(company_id, title, body, due_date, status)

@tool
def update_job_opening(opening_id: int, company_id: Optional[int] = None, title: Optional[str] = None, body: Optional[str] = None, due_date: Optional[str] = None, status: Optional[int] = None) -> dict:
    """
    Update an existing job opening record.

    Args:
        opening_id (int): ID unik dari lowongan yang akan diperbarui.
        company_id (int, optional): ID unik dari perusahaan yang membuka lowongan.
        title (str, optional): Judul lowongan pekerjaan.
        body (str, optional): Deskripsi lengkap lowongan.
        due_date (str, optional): Tanggal tenggat lamaran dalam format YYYY-MM-DD.
        status (int, optional): Status lowongan (misalnya 1=Aktif, 0=Nonaktif).
    """
    return update_job_opening(opening_id, company_id, title, body, due_date, status)

@tool
def delete_job_opening(opening_id: int) -> dict:
    """
    Delete a job opening by its ID.

    Args:
        opening_id (int): ID unik dari lowongan pekerjaan yang akan dihapus.
    """
    return delete_job_opening(opening_id)

tools = [
    initiate_contact,
    retrieve_data,
    create_talent,
    update_talent,
    delete_talent,
    create_candidate,
    update_candidate,
    delete_candidate,
    create_company,
    update_company,
    delete_company,
    create_company_property,
    update_company_property,
    delete_company_property,
    create_job_opening,
    update_job_opening,
    delete_job_opening,
]