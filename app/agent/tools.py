

import tiktoken
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.runnables import RunnableConfig
from api_client import (
    retrieve_data, relogin_once_on_401,
    _update_resource, _delete_resource, _create_resource
)
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
                {"role": "user",
                 "content": f"Buat judul singkat (maksimal 5 kata) untuk percakapan ini"}
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
        print(
            f"Attempt to initiate contact to {chat_user_id} [{talent_id}/{talent_name}] untuk {job_opening_id}")

        # Langkah 1: Daftarkan sebagai kandidat
        candidate_result = create_candidate(
            talent_id=talent_id, job_opening_id=job_opening_id, status=1)
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
            query_texts=[search],  # Chroma will embed this for you
            n_results=5  # how many results to return
        )
        return results
    except Exception as error:
        print("Error Tools")
        print(error)


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
    if name is not None:
        payload["name"] = name
    if position is not None:
        payload["position"] = position
    if birthdate is not None:
        payload["birthdate"] = birthdate
    if summary is not None:
        payload["summary"] = summary
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
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if position is not None:
        payload["position"] = position
    if birthdate is not None:
        payload["birthdate"] = birthdate
    if summary is not None:
        payload["summary"] = summary
    return relogin_once_on_401(_update_resource, "talent", talent_id, payload)


@tool
def delete_talent(talent_id: int) -> dict:
    """
    Delete a talent by their ID.

    Args:
        talent_id (int): ID unik dari talent yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "talent", talent_id)

# ========== CANDIDATE MANAGEMENT ==========


@tool
def create_candidate(talent_id: int, job_opening_id: int, status: Optional[int] = None, **kwargs) -> dict:
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
    payload = {"talent_id": talent_id,
               "job_opening_id": job_opening_id, "status": status, **kwargs}
    return relogin_once_on_401(_create_resource, "candidates", payload)


@tool
def update_candidate(candidate_id: int, talent_id: Optional[int] = None, job_opening_id: Optional[int] = None, **kwargs) -> dict:
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
    payload = {k: v for k, v in kwargs.items() if v is not None}
    if not payload:
        return {"message": "Tidak ada data untuk diupdate."}
    return relogin_once_on_401(_update_resource, "candidates", candidate_id, payload)


@tool
def delete_candidate(candidate_id: int) -> dict:
    """
    Delete a candidate record by their ID.

    Args:
        candidate_id (int): ID unik dari kandidat yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "candidates", candidate_id)

# ========== COMPANY MANAGEMENT ==========


@tool
def create_company(name: str, description: Optional[str] = None, **kwargs) -> dict:
    """
    Create a new company record.

    Args:
        name (str): Nama perusahaan.
        description (str, optional): Deskripsi singkat tentang perusahaan.
        status (int, optional): Status perusahaan.
    """
    payload = {"name": name, **kwargs}
    return relogin_once_on_401(_create_resource, "companies", payload)


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
    payload = {
        "company_id": company_id,
        "name": name,
        "description": description,
        "status": status
    }
    return relogin_once_on_401(_update_resource, "companies", company_id, payload)


@tool
def delete_company(company_id: int) -> dict:
    """
    Delete a company record by its ID.

    Args:
        company_id (int): ID unik dari perusahaan yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "companies", company_id)

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
    payload = {"company_id": company_id, "key": key, "value": value}
    return relogin_once_on_401(_create_resource, "company-properties", payload)


# ========== JOB OPENING MANAGEMENT ==========

@tool
def create_job_opening(company_id: int, title: str, body: Optional[str] = None, due_date: Optional[str] = None, status: Optional[int] = None, **kwargs) -> dict:
    """
    Create a new job opening.

    Args:
        company_id (int): ID unik dari perusahaan yang membuka lowongan.
        title (str): Judul lowongan pekerjaan.
        body (str, optional): Deskripsi lengkap lowongan.
        due_date (str, optional): Tanggal tenggat lamaran dalam format YYYY-MM-DD.
        status (int, optional): Status lowongan (misalnya 1=Aktif, 0=Nonaktif).
    """

    payload = {"company_id": company_id, "title": title}
    payload["body"] = body if body is not None else ""
    payload["status"] = status  # <-- Menambahkan status default (1 = aktif)
    payload.update(kwargs)
    return relogin_once_on_401(_create_resource, "job-openings", payload)


@tool
def update_job_opening(opening_id: int, company_id: Optional[int] = None, title: Optional[str] = None, body: Optional[str] = None, due_date: Optional[str] = None, status: Optional[int] = None, **kwargs) -> dict:
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
    payload = {k: v for k, v in kwargs.items() if v is not None}
    if not payload:
        return {"message": "Tidak ada data untuk diupdate."}
    return relogin_once_on_401(_update_resource, "job-openings", opening_id, payload)


@tool
def delete_job_opening(opening_id: int) -> dict:
    """
    Delete a job opening by its ID.

    Args:
        opening_id (int): ID unik dari lowongan pekerjaan yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "job-openings", opening_id)


recall_vector_store = InMemoryVectorStore(OpenAIEmbeddings())


def get_user_id(config: RunnableConfig) -> str:
    user_id = config["configurable"].get("user_id")
    if user_id is None:
        raise ValueError("User ID needs to be provided to save a memory.")

    return user_id


@tool
def save_recall_memory(memory: str, config: RunnableConfig) -> str:
    """Save memory to vectorstore for later semantic retrieval."""
    user_id = get_user_id(config)
    document = Document(
        page_content=memory, id=str(uuid.uuid4()), metadata={"user_id": user_id}
    )
    recall_vector_store.add_documents([document])
    return memory


@tool
def search_recall_memories(query: str, config: RunnableConfig) -> List[str]:
    """Search for relevant memories."""
    user_id = get_user_id(config)

    def _filter_function(doc: Document) -> bool:
        return doc.metadata.get("user_id") == user_id

    documents = recall_vector_store.similarity_search(
        query, k=3, filter=_filter_function
    )
    return [document.page_content for document in documents]


@tool
def fetch_user_data(chat_user_id: str) -> str:
    """Get User Information by chat_user_id. 

    Untuk pertanyaan "Siapa nama ku"
    """
    from vectordb import Chroma
    import json

    print(f":: Fetch User Data\n {chat_user_id}")

    collection = Chroma().client().get_or_create_collection('users',)

    user = collection.query(
        query_texts=chat_user_id,
        where={
            "chat_user_id": chat_user_id
        },
        n_results=1  # how many results to return
    )
    print(f":: Get User Info\n")
    print(user)
    if len(user['metadatas'][0]) < 1:
        return None
    user_info = json.dumps({
        'metadatas': user['metadatas'][0][0],
        'description': user['documents'][0][0]
    })

    print(f":: Get User Info\n {chat_user_id}")

    return user_info


@tool
def retrieve_prompt(context):
    """
    Mendapatkan context_prompt berdasarkan informasi user dan message nya

    context: 
        HR_ASSISTANT for user is a company and asking about management of talent/candidate/job opening 
        TALENT_COMPANION for user is a talent and asking anything
        CHAT_INITIATOR for ai self-initiate chat without known context
    """
    from prompt import TemplatePrompt
    print(context)
    return getattr(TemplatePrompt, context)


@tool
def initiate_new_chat(recipient, trigger_prompt):
    """
    Initiate a chat to reach out a user.
    Case:
        - offering and screening talent for a job opening
        - inform candidate/talent about interview process
        - inform company user about the condition of current job opening
        - diminta menghubungi user tertentu menyertakan chat_user_id
        - etc.

    Args:
        recipient: str - chat_user_id of the recipient
        trigger_prompt: str - prompt to initiate to define context and session topic/prompt
    """
    from agent.lisa import Lisa

    Lisa().initiate_chat(recipient, trigger_prompt)
    pass


@tool
def generate_screening_question(job_description):
    """Generate Screening Question for Candidate

    Required for crafting context prompt for TALENT_REACH_OUT
    Args:
        job_description: str - job description detail
    """
    from agent.lisa import Lisa
    from langchain_core.messages import HumanMessage

    response = Lisa().invoke([
        HumanMessage(content=("""> Given a job description:"""
          f"{job_description}"
          """> Based on above job description, craft 4 question for screening candidate.
            """))
    ])
    return response


tools = [
    save_recall_memory,
    search_recall_memories,
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
    create_job_opening,
    update_job_opening,
    delete_job_opening,
    fetch_user_data,
    initiate_new_chat,
    generate_screening_question
]
