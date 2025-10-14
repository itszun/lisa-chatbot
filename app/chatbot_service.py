from prompt import TALENT_HUNTER, HR_ASSISTANT, RECRUITMENT_ASSISTANT
from agent.tools import tools

chatbot_service_dict = {
    'cari_lowongan_kerja': {
        "title": "Cari Lowongan Kerja",
        "system_prompt": TALENT_HUNTER,
        "message_opener": ("Hai! Aku Lisa 👋 Siap bantu kamu cari pekerjaan yang cocok dengan pengalaman dan keahlianmu. Mau mulai dari posisi tertentu?"),
        "tools": tools,
    },
    'buat_lowongan_kerja': {
        "title":"Buat Lowongan Kerja",
        "system_prompt": HR_ASSISTANT,
        "message_opener": "Halo! Aku Lisa 👩‍💼 Siap bantu kamu membuat lowongan baru dan mencari kandidat yang sesuai. Posisi apa yang ingin kamu buka hari ini?",
        "tools": tools,
    },
    'cari_kandidat_dan_screening': {
        "title": "Cari Kandidat dan Screening",
        "system_prompt": RECRUITMENT_ASSISTANT,
        "message_opener": "Hai, ini Lisa! Aku siap bantu kamu mengelola data HR — mau update, hapus, atau cek data tertentu dulu?",
        "tools": tools,
    },
    
}