import os
import json
import requests
from openai import OpenAI

# --- PENGATURAN PENTING ---
# Ganti dengan kunci API OpenAI Anda. Sangat disarankan menggunakan environment variable.
# contoh: client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# === LANGKAH 1: DEFINISIKAN FUNGSI / ALAT YANG BISA DIGUNAKAN ===

def get_pokemon_info(name: str):
    """Mengambil informasi umum tentang Pokémon seperti ID, tinggi, dan berat."""
    print(f"🔧 Menjalankan fungsi: get_pokemon_info(name='{name}')")
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        info = {
            "name": data['name'],
            "id": data['id'],
            "height": f"{data['height'] / 10} m",
            "weight": f"{data['weight'] / 10} kg",
        }
        return json.dumps(info)
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Masalah koneksi: {e}"})

def get_pokemon_abilities(name: str):
    """Mendapatkan daftar kemampuan (abilities) dari Pokémon tertentu."""
    print(f"🔧 Menjalankan fungsi: get_pokemon_abilities(name='{name}')")
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        abilities = [ability['ability']['name'] for ability in data['abilities']]
        return json.dumps({"name": data['name'], "abilities": abilities})
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})

def get_pokemon_types(name: str):
    """Mendapatkan daftar tipe (misalnya fire, water, grass) dari Pokémon tertentu."""
    print(f"🔧 Menjalankan fungsi: get_pokemon_types(name='{name}')")
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        types = [t['type']['name'] for t in data['types']]
        return json.dumps({"name": data['name'], "types": types})
    except requests.exceptions.HTTPError:
        return json.dumps({"error": f"Pokémon '{name}' tidak ditemukan."})

# === LANGKAH 2: DESKRIPSIKAN ALAT-ALAT TERSEBUT UNTUK AI ===

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_info",
            "description": "Dapatkan data umum (ID, tinggi, berat) dari Pokémon berdasarkan namanya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Pikachu"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_abilities",
            "description": "Dapatkan daftar semua kemampuan (ability) dari Pokémon tertentu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Snorlax"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_types",
            "description": "Dapatkan tipe elemen dari Pokémon tertentu (misal: fire, water, electric).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama Pokémon, contoh: Bulbasaur"},
                },
                "required": ["name"],
            },
        },
    }
]

# === LANGKAH 3: LOGIKA UTAMA CHATBOT ===

# Simpan histori percakapan
messages = [{"role": "system", "content": "You are a helpful Pokémon assistant. Answer the user's questions based on the function results."}]

print("--- 🤖 Selamat Datang di Chatbot Pokémon Interaktif! 🤖 ---")
print("Ketik 'keluar' atau 'exit' untuk mengakhiri program.")
print("-" * 50)

while True:
    user_input = input("\nAnda: ")
    if user_input.lower() in ["keluar", "exit"]:
        print("👋 Sampai jumpa!")
        break

    messages.append({"role": "user", "content": user_input})

    # Panggilan pertama ke AI untuk memutuskan apakah perlu memanggil fungsi
    print("🤖 Menganalisis pertanyaan...")
    response = client.chat.completions.create(
        model="gpt-4o", # Model terbaru lebih baik dalam function calling
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # Jika AI memutuskan untuk memanggil fungsi
    if tool_calls:
        print("🤖 Memutuskan untuk memanggil fungsi...")
        messages.append(response_message) # Simpan keputusan AI

        available_functions = {
            "get_pokemon_info": get_pokemon_info,
            "get_pokemon_abilities": get_pokemon_abilities,
            "get_pokemon_types": get_pokemon_types,
        }

        # Jalankan setiap fungsi yang diminta AI
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(name=function_args.get("name"))
            
            # Kirim hasil fungsi kembali ke AI
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )
        
        # Panggilan kedua ke AI, sekarang dengan hasil dari fungsi
        print("🤖 Merumuskan jawaban akhir...")
        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        final_answer = second_response.choices[0].message.content
        print(f"\nChatbot: {final_answer}")
        messages.append({"role": "assistant", "content": final_answer})

    # Jika AI menjawab langsung tanpa fungsi
    else:
        answer = response_message.content
        print(f"\nChatbot: {answer}")
        messages.append({"role": "assistant", "content": answer})