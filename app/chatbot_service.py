from prompt import TALENT_HUNTER_PROMPT, HR_ASSISTANT_PROMPT
from agent.tools import tools

chatbot_service_dict = {
    'cari_lowongan_kerja': {
        "title": "Cari Lowongan Kerja",
        "system_prompt": TALENT_HUNTER_PROMPT,
        "message_opener": "Hi, Lisa siap membantu pembuatan lowongan kerja baru",
        "tools": tools,
    },
    'buat_lowongan_kerja': {
        "title":"Buat Lowongan Kerja",
        "system_prompt": HR_ASSISTANT_PROMPT,
        "message_opener": "Hi, Lisa siap membantu pembuatan lowongan kerja baru",
        "tools": tools,
    },
    'cari_kandidat_dan_screening': {
        "title": "Cari Kandidat dan Screening",
        "system_prompt": HR_ASSISTANT_PROMPT,
        "message_opener": "Hi, Lisa siap membantu pencarian kandidat dan screening",
        "tools": tools,
    },
}