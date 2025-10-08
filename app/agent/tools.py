from api_client import (
    retrieve_data, relogin_once_on_401,
    _update_resource, _delete_resource, _create_resource
)
from langchain_core.tools import tool
from typing import Optional, List, Dict, Any

from vectordb import Chroma
import json
from pydantic import BaseModel, Field
from agent.screening_agent import ScreeningQuestionAgent
from api_client import _get, _post, BASE_URL, PANEL, _safe_json
from agent.sub_agent import SubAgent
from prompt import TemplatePrompt

from langchain_core.messages.ai import AIMessage

class RetrieveDataInput(BaseModel):
    """Schema input untuk pencarian data menggunakan Vector Database."""
    collection_name: str = Field(
        ..., 
        description='Nama koleksi data: "talent_pool", "job_openings", "users", "company", atau "candidates".'
    )
    search: str = Field(..., description="Kata kunci/query untuk pencarian (dapat berupa kalimat lengkap).")
    max_result: int = Field(5, description="Jumlah hasil yang ingin dikembalikan (maksimum 5).")

@tool(args_schema=RetrieveDataInput)
def retrieve_data(input: RetrieveDataInput) -> dict:
    """
    Mencari data terkait Job Opening, Talent, Company, User, dan Candidate menggunakan Vector DB (Chroma).
    Gunakan untuk mendapatkan detail objek berdasarkan deskripsi atau ID yang tidak diketahui.
    """
    if input.max_result > 5:
        raise RuntimeError("Can't retrieve more than 5 results.")
    
    try:
        collection = Chroma().client().get_or_create_collection(name=input.collection_name)
        results = collection.query(
            query_texts=[input.search],  # Chroma will embed this for you
            n_results=input.max_result  # how many results to return
        )
        return results
    except Exception as error:
        print("Error Tools")
        print(error)


class TalentUpsertInput(BaseModel):
    """
    Schema input untuk membuat atau memperbarui record talent (UPSERT).
    
    Jika talent_id diisi, akan melakukan UPDATE. 
    Jika talent_id tidak diisi, akan melakukan CREATE.
    Semua field wajib diisi saat CREATE, dan opsional saat UPDATE.
    """
    
    # Kunci utama: Opsional untuk CREATE, wajib untuk UPDATE
    talent_id: Optional[int] = Field(None, description="ID unik Talent. Jika diisi, lakukan UPDATE. Jika kosong, lakukan CREATE.")
    
    # Field Wajib/Opsional
    name: Optional[str] = Field(None, description="Nama lengkap talent.")
    position: Optional[str] = Field(None, description="Posisi pekerjaan talent saat ini.")
    birthdate: Optional[str] = Field(None, description="Tanggal lahir talent. Format: YYYY-MM-DD.")
    summary: Optional[str] = Field(None, description="Ringkasan singkat profil atau pengalaman talent.")
    
    # Complex fields
    skills: Optional[List[str]] = Field(None, description="Daftar keahlian (skill).")
    educations: Optional[List[Dict[str, Any]]] = Field(None, description="Daftar riwayat pendidikan.")

@tool(args_schema=TalentUpsertInput)
def manage_talent(input: TalentUpsertInput) -> dict:
    """
    Membuat record talent baru (CREATE) atau memperbarui yang sudah ada (UPDATE).
    Jika talent_id diisi, lakukan UPDATE. Jika talent_id kosong, lakukan CREATE.
    """
    
    payload = input.model_dump(exclude_none=True, exclude={'talent_id'})
    
    if input.talent_id:
        talent_id = input.talent_id
        
        if not payload:
            return {"message": f"Tidak ada data untuk diupdate di Talent ID {talent_id}."}
            
        print(f"Mengupdate Talent ID: {talent_id}")
        
        return relogin_once_on_401(_update_resource, "talent", talent_id, payload)
        
    else:
        
        required_fields = ["name", "position", "birthdate", "summary"]
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Untuk CREATE talent baru, field '{field}' wajib diisi.")

        print("Menciptakan Talent Baru")
        
        return relogin_once_on_401(_create_resource, "talent", payload)
    

@tool
def delete_talent(talent_id: int) -> dict:
    """
    Delete a talent by their ID.

    Args:
        talent_id (int): ID unik dari talent yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "talent", talent_id)

# ========== CANDIDATE MANAGEMENT ==========

class CandidateUpsertInput(BaseModel):
    """
    Schema input untuk membuat atau memperbarui record kandidat. 
    
    API akan menentukan apakah ini CREATE atau UPDATE (UPSERT)
    berdasarkan kombinasi unik talent_id dan job_opening_id.
    """
    
    talent_id: int = Field(..., description="ID Talent (Wajib).")
    job_opening_id: int = Field(..., description="ID Job Opening (Wajib).")
    
    status: Optional[int] = Field(
        None, 
        description=(
            "Kode status kandidat. Opsional, default status 1 (Draft). "
            "Contoh: 2=Scouting, 100=Screening, 202=Offering, 902=Eliminated."
        )
    )
    
    # Field opsional lainnya (untuk update/create)
    regist_at: Optional[str] = Field(None, description="Waktu pendaftaran. Format: YYYY-MM-DD HH:MM:SS.")
    interview_schedule: Optional[str] = Field(None, description="Jadwal wawancara. Format: YYYY-MM-DD HH:MM:SS.")
    notified_at: Optional[str] = Field(None, description="Waktu pemberitahuan. Format: YYYY-MM-DD HH:MM:SS.")

@tool(args_schema=CandidateUpsertInput)
def manage_candidate(input: CandidateUpsertInput) -> dict:
    """
    Membuat (CREATE) record kandidat baru atau memperbarui (UPDATE) yang sudah ada (UPSERT).
    Sistem API yang menentukan operasi berdasarkan kombinasi talent_id dan job_opening_id.
    """
    
    # 1. Ambil payload bersih (hanya yang non-None)
    # Karena API lo yang handle UPSERT, kita kirim semua data yang ada
    payload = input.model_dump(exclude_none=True)
    
    print(f"Mengirim payload UPSERT Candidate: {payload}")
    
    # 2. Selalu panggil fungsi CREATE (_create_resource), 
    # karena kita asumsikan API POST /candidates/ yang handle UPSERT
    return relogin_once_on_401(_create_resource, "candidates", payload)

@tool
def delete_candidate(candidate_id: int) -> dict:
    """
    Delete a candidate record by their ID.

    Args:
        candidate_id (int): ID unik dari kandidat yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "candidates", candidate_id)

# ========== COMPANY MANAGEMENT ==========

class CompanyUpsertInput(BaseModel):
    """
    Schema input untuk membuat atau memperbarui record Perusahaan (UPSERT).
    
    Jika company_id diisi, akan melakukan UPDATE. 
    Jika company_id tidak diisi, akan melakukan CREATE.
    """
    
    # Kunci utama: Opsional untuk CREATE, wajib untuk UPDATE
    company_id: Optional[int] = Field(None, description="ID unik Perusahaan. Jika diisi, lakukan UPDATE. Jika kosong, lakukan CREATE.")
    
    # Field Wajib/Opsional
    name: Optional[str] = Field(None, description="Nama perusahaan.")
    description: Optional[str] = Field(None, description="Deskripsi singkat tentang perusahaan.")
    status: Optional[int] = Field(None, description="Status perusahaan (misal: 1=Aktif, 0=Nonaktif).")

    
@tool(args_schema=CompanyUpsertInput)
def manage_company(input: CompanyUpsertInput) -> dict:
    """
    Membuat record perusahaan baru (CREATE) atau memperbarui yang sudah ada (UPDATE).
    Jika company_id diisi, lakukan UPDATE. Jika company_id kosong, lakukan CREATE.
    """
    
    # 1. Ambil payload bersih (semua yang non-None, kecuali company_id)
    payload = input.model_dump(exclude_none=True, exclude={'company_id'})
    
    # 2. Tentukan Mode Operasi
    if input.company_id:
        # ** MODE: UPDATE (company_id ADA) **
        company_id = input.company_id
        
        if not payload:
            return {"message": f"Tidak ada data untuk diupdate di Company ID {company_id}."}
            
        print(f"Mengupdate Company ID: {company_id}")
        
        # Panggil helper UPDATE
        return relogin_once_on_401(_update_resource, "companies", company_id, payload)
        
    else:
        # ** MODE: CREATE (company_id KOSONG) **
        
        # Logika Validasi Wajib untuk CREATE
        if not payload.get("name"):
            raise ValueError("Untuk CREATE perusahaan baru, 'name' wajib diisi.")

        print("Menciptakan Company Baru")
        
        # Panggil helper CREATE
        return relogin_once_on_401(_create_resource, "companies", payload)
    
@tool
def delete_company(company_id: int) -> dict:
    """
    Delete a company record by its ID.

    Args:
        company_id (int): ID unik dari perusahaan yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "companies", company_id)

# ========== JOB OPENING MANAGEMENT ==========

class JobOpeningUpsertInput(BaseModel):
    """
    Schema input untuk membuat atau memperbarui record Job Opening (UPSERT).
    
    Jika job_opening_id diisi, akan melakukan UPDATE. 
    Jika job_opening_id tidak diisi, akan melakukan CREATE.
    """
    
    # Kunci utama: Opsional untuk CREATE, wajib untuk UPDATE
    job_opening_id: Optional[int] = Field(None, description="ID unik Job Opening. Jika diisi, lakukan UPDATE. Jika kosong, lakukan CREATE.")
    
    # Field Wajib/Opsional
    company_id: Optional[int] = Field(None, description="ID unik perusahaan yang membuka lowongan.")
    title: Optional[str] = Field(None, description="Judul lowongan pekerjaan.")
    body: Optional[str] = Field(None, description="Deskripsi lengkap lowongan.")
    due_date: Optional[str] = Field(None, description="Tanggal tenggat lamaran. Format: YYYY-MM-DD.")
    status: Optional[int] = Field(None, description="Status lowongan (misalnya 1=Aktif, 0=Nonaktif).")


@tool(args_schema=JobOpeningUpsertInput)
def manage_job_opening(input: JobOpeningUpsertInput) -> dict:
    """
    Membuat record lowongan baru (CREATE) atau memperbarui yang sudah ada (UPDATE).
    Jika job_opening_id diisi, lakukan UPDATE. Jika job_opening_id kosong, lakukan CREATE.
    """
    
    # 1. Ambil payload bersih (semua yang non-None, kecuali job_opening_id)
    payload = input.model_dump(exclude_none=True, exclude={'job_opening_id'})
    
    # 2. Tentukan Mode Operasi
    if input.job_opening_id:
        # ** MODE: UPDATE (job_opening_id ADA) **
        opening_id = input.job_opening_id
        
        if not payload:
            return {"message": f"Tidak ada data untuk diupdate di Job Opening ID {opening_id}."}
            
        print(f"Mengupdate Job Opening ID: {opening_id}")
        
        # Panggil helper UPDATE
        return relogin_once_on_401(_update_resource, "job-openings", opening_id, payload)
        
    else:
        # ** MODE: CREATE (job_opening_id KOSONG) **
        
        # Logika Validasi Wajib untuk CREATE
        required_fields = ["company_id", "title"]
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Untuk CREATE job opening baru, field '{field}' wajib diisi.")

        # Set body default jika kosong (sesuai logic asli lo)
        payload.setdefault("body", "") 
        # Set status default jika kosong (sesuai logic asli lo)
        payload.setdefault("status", 1) 

        print("Menciptakan Job Opening Baru")
        
        # Panggil helper CREATE
        return relogin_once_on_401(_create_resource, "job-openings", payload)


@tool
def delete_job_opening(opening_id: int) -> dict:
    """
    Delete a job opening by its ID.

    Args:
        opening_id (int): ID unik dari lowongan pekerjaan yang akan dihapus.
    """
    return relogin_once_on_401(_delete_resource, "job-openings", opening_id)



@tool
def fetch_user_data(chat_user_id: str) -> str:
    """Get User Information by chat_user_id. 

    Untuk pertanyaan "Siapa nama ku"
    """

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

    context options: 
    
        HR_ASSISTANT for user is a company and asking about management of talent/candidate/job opening 
        TALENT_COMPANION for user is a talent and asking anything
        CHAT_INITIATOR for ai self-initiate chat without known context

        DEFAULT_SYSTEM_PROMPT is equals HR_ASSISTANT

    !! You can't choose outside the options
    """
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
    SubAgent().initiate_chat(recipient, trigger_prompt)
    pass

class ScreeningTalentInput(BaseModel):
    """
    Schema input untuk memulai proses Screening/Penawaran Kerja kepada Talent.
    Tool ini WAJIB dijalankan setelah record kandidat dibuat/di-update (UPSERT).
    """
    
    candidate_id: int = Field(..., description="ID unik Kandidat yang akan diproses Screening. ID ini didapat dari hasil tool 'manage_candidate'.")
    chat_user_id: str = Field(..., description="ID chat milik Talent (misalnya 'id@user_name').")
    job_opening_detail: str = Field(..., description="Detail Job Opening (termasuk info perusahaan, posisi, dan deskripsi) yang relevan.")
    talent_information: str = Field(..., description="Deskripsi atau ringkasan profil tentang Talent tersebut.")
    candidate_information: str = Field(..., description="Informasi tambahan tentang kandidat (jika ada).")
    chat_starter: Optional[str] = Field("Hello", description="Draft pesan pembuka/penawaran yang akan dikirim (gunakan Markdown).")
    # Talent ID tidak diperlukan di sini karena sudah terasosiasi di Candidate ID

@tool(args_schema=ScreeningTalentInput)
def screening_a_talent(input: ScreeningTalentInput) -> dict:
    """
    Memulai proses Penawaran Job Opening dan Inisiasi Chat Screening kepada Talent.
    Tool ini hanya dapat dipanggil setelah record kandidat (candidate_id) berhasil dibuat/di-update.
    """

    print(("Screening Talent"
           f"""chat_user_id: {input.chat_user_id}
           candidate_id: {input.candidate_id} 
           job_opening_detail: {input.job_opening_detail}
           talent_information: {input.talent_information}"""))
    
    steps = {
        "intiate_chat": 0,
        "candidate_id": input.candidate_id # Masukkan ID kandidat ke hasil
    }
    
    # 💡 Perhatian: Logic create_candidate dihapus!
    
    try:
        print(":: REACH OUT TALENT")
        
        # Panggil Agen Screening
        ScreeningQuestionAgent(is_new=True).reachOutTalent(
            input.chat_user_id, 
            input.job_opening_detail, 
            input.talent_information, 
            input.candidate_information, 
            AIMessage(input.chat_starter)
        )
        steps["intiate_chat"] = 1
        
    except Exception as e:
        raise RuntimeError(f"Gagal memulai chat screening: {str(e)}")
        
    return {"success": True, "steps": steps, "message": f"Screening untuk Candidate ID {input.candidate_id} berhasil diinisiasi."}


@tool
def evaluate_job_opening_progress(job_opening_id):
    """
    evaluate_job_opening_progress()

    To know current state of job opening and continue process
    """
    url = f"{BASE_URL}/api/{PANEL}/job-openings/{job_opening_id}/evaluate"
    r = _get(url)
    data = _safe_json(r)
    return data["data"] if isinstance(data, dict) and "data" in data else data

@tool
def get_assessment_link(job_opening_id):
    """
    get_assessment_link()

    Get Assessment Link
    """
    return f"assessment.altateknologi.com/{job_opening_id}";


@tool
def initiate_a_new_chat(chat_user_id, system_prompt, chat_starter):
    """
    Memulai sesi chat baru dengan chat_user_id. setelah ini harus call push_notification

    Args:
        chat_user_id (str): ID user chat tujuan.
        system_prompt (str): User prompt untuk memerintah konteks. Jelaskan detail asumsi, objective, persona, behaviour nya.
        chat_starter (str): Message pertama.
    """
    print("=======================================================")
    print("=======================================================")
    print(f":: INITIATE A NEW CHAT for \"{chat_user_id}\"")
    print("=======================================================")
    print("=======================================================")
    SubAgent(True).initiate_chat(
        chat_user_id, 
        prompt=system_prompt, 
        ai_message=chat_starter,
        use_context_definer=False)
    
@tool
def push_notification(chat_user_id, subject, body):
    """
    Push a notification to user. 

    Args:
        chat_user_id (str): Chat ID for target user
        subject (str): max 50 char. short title text or short message for the notification
        body (str): max 200 char. actual message/description about the notification. 
    """
    
    print("=======================================================")
    print("=======================================================")
    print(f":: NOTIFICATION for \"{chat_user_id}\" with {subject} \n {body}")
    print("=======================================================")
    print("=======================================================")
    url = f"{BASE_URL}/api/{PANEL}/notifications/push"
    r = _post(url, json={
        "chat_user_id": chat_user_id,
        "subject": subject,
        "body": body,
    })
    data = _safe_json(r)
    result= data["data"] if isinstance(data, dict) and "data" in data else data
    print("DATA", data)
    print("RESULT", result)


tools = [
    retrieve_data,
    manage_talent,
    delete_talent,
    manage_candidate,
    delete_candidate,
    manage_company,
    delete_company,
    manage_job_opening,
    delete_job_opening,
    fetch_user_data,
    screening_a_talent,
    evaluate_job_opening_progress,
    get_assessment_link,
    initiate_a_new_chat,
    push_notification
]
