# chatbot.py
import os, json
from openai import OpenAI
from api_client import interactive_login, ensure_token, list_talent
from tools_registry import tools, available_functions

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY belum diisi.")
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You are a helpful assistant for a remote Admin API. "
    "Use the tools to perform CRUD on resources under /api/{panel}/... "
    "Prefer concise answers, show key fields only. "
    "If an operation fails, return a short, actionable error message."
)

def main():
    # login (atau paste token manual kalau gagal)
    interactive_login()
    ensure_token()
    print(list_talent(page=1, per_page=5))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("\n--- 🤖 Chatbot Admin API ---")
    print("Kamu bisa tanya: talent, candidates, companies, company-properties, job-openings.")
    print("Contoh: 'tampilkan talent halaman 1', 'detail candidates id 3', 'buat company ...'")
    print("Ketik 'keluar' untuk selesai.")
    print("-" * 50)

     # tidak minta login kalau token cache valid


    while True:
        try:
            user_input = input("\nAnda: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Sampai jumpa!")
            break

        if user_input.lower() in ["keluar", "exit"]:
            print("👋 Sampai jumpa!")
            break

        messages.append({"role": "user", "content": user_input})
        print("🤖 Menganalisis…")

        try:
            resp1 = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            msg = resp1.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            if tool_calls:
                messages.append(msg)
                print("🛠️ Menjalankan fungsi…")
                for tc in tool_calls:
                    fn_name = tc.function.name
                    args = json.loads(tc.function.arguments or "{}")
                    try:
                        out = available_functions[fn_name](**args)
                        payload = json.dumps(out, ensure_ascii=False) if not isinstance(out, str) else out
                    except Exception as fn_err:
                        payload = json.dumps({"error": str(fn_err)}, ensure_ascii=False)
                    messages.append({
                        "tool_call_id": tc.id,
                        "role": "tool",
                        "name": fn_name,
                        "content": payload,
                    })

                print("🧠 Menyusun jawaban…")
                resp2 = client.chat.completions.create(model="gpt-4o", messages=messages)
                final_answer = resp2.choices[0].message.content
                print(f"\nChatbot: {final_answer}")
                messages.append({"role": "assistant", "content": final_answer})
            else:
                answer = msg.content or "(tidak ada jawaban)"
                print(f"\nChatbot: {answer}")
                messages.append({"role": "assistant", "content": answer})

        except Exception as e:
            print(f"\n❌ Terjadi error: {e}")

if __name__ == "__main__":
    main()
