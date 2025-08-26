import os
import openai
import mysql.connector
from dotenv import load_dotenv

import tkinter as tk
from tkinter import scrolledtext, messagebox
import tkinter.ttk as ttk
import threading
import queue
from datetime import datetime

# ==============================================================================
# BAGIAN 1: SEMUA LOGIKA BACKEND CHATBOT (SAMA / MINOR PERAPIHAN)
# ==============================================================================

# Muat semua variabel dari file .env
if not load_dotenv():
    try:
        messagebox.showerror("Error Konfigurasi", "File .env tidak ditemukan! Harap pastikan file tersebut ada di folder yang sama.")
    except Exception:
        pass
    raise SystemExit()

# Konfigurasi OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Konfigurasi Database dari .env
def _to_int_port(val, default=3306):
    try:
        return int(val)
    except Exception:
        return default

DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASS"),
    'database': os.getenv("DB_NAME"),
    'port': _to_int_port(os.getenv("DB_PORT", "3306"))
}

def get_database_schema():
    """Mengembalikan skema tabel database dalam bentuk string."""
    return """
    CREATE TABLE talents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(255) NOT NULL,
        position VARCHAR(255), birthdate TEXT, summary TEXT,
        skills JSON, educations JSON
    );
    """

def generate_sql_query(user_question):
    """Mengirim pertanyaan pengguna dan skema DB ke AI untuk diubah menjadi query SQL."""
    schema = get_database_schema()
    prompt = f"""
    Anda adalah asisten database yang TUGAS UTAMANYA adalah membantu mencari data talent.
    Gunakan HANYA sintaks SQL untuk database MySQL.
    Berdasarkan skema tabel berikut:
    {schema}

    PENTING:
    1.  Kolom 'birthdate' adalah TEXT. Gunakan STR_TO_DATE. Contoh: STR_TO_DATE(birthdate, '%Y-%m-%d').
    2.  Kolom 'skills' dan 'educations' adalah JSON. Untuk pencarian teks parsial (substring) yang tidak mempedulikan huruf besar/kecil, gunakan LOWER() dan LIKE. Contoh: WHERE LOWER(skills) LIKE '%python%'.
    3.  Jika pengguna menggunakan singkatan (misal: "ITB", "QA"), buat query yang mencari singkatan ATAU kemungkinan kepanjangannya (misal: 'Institut Teknologi Bandung', 'Quality Assurance'). Gunakan klausa OR.

    Tulis sebuah query SQL SELECT untuk menjawab pertanyaan ini: "{user_question}".
    - HANYA kembalikan query SQL yang valid tanpa penjelasan tambahan.

    Jika pertanyaan tidak berhubungan, jawab saja dengan "INVALID".
    """

    try:
        response = openai.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Anda adalah ahli SQL yang cerdas dan dapat memahami konteks singkatan."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        raw_response = response.choices[0].message.content.strip()
        select_pos = raw_response.upper().find("SELECT")
        if select_pos != -1:
            sql_query = raw_response[select_pos:]
            if sql_query.endswith("```"):
                sql_query = sql_query[:-3]
            return sql_query.strip()
        else:
            return "INVALID"
    except Exception as e:
        return f"ERROR_API: {e}"

def execute_sql_query(query):
    """Menjalankan query SQL ke database dan mengembalikan hasilnya."""
    if not query.strip().upper().startswith("SELECT"):
        return f"Error: Query ('{query}') tidak diawali SELECT.", None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)
        result = cursor.fetchall()
        return result, None
    except mysql.connector.Error as err:
        return None, f"Error Database: {err}"
    finally:
        try:
            if 'connection' in locals() and connection.is_connected():
                cursor.close()
                connection.close()
        except Exception:
            pass

def interpret_results(question, db_result):
    """Mengirim hasil database ke AI untuk diubah menjadi jawaban yang mudah dibaca."""
    prompt = f"""
    Berdasarkan pertanyaan awal: "{question}" dan hasil data dari database: {db_result}
    Buatlah jawaban ramah dalam Bahasa Indonesia. Jika data kosong, sampaikan data tidak ditemukan.
    """
    try:
        response = openai.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Anda adalah asisten yang membantu meringkas data talent."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error API saat interpretasi: {e}"

# ==============================================================================
# BAGIAN 2: KELAS APLIKASI GUI TKINTER (TAMPILAN LEBIH MENARIK)
# ==============================================================================
class ChatbotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 Chatbot Database Talent")
        self.root.geometry("820x620")
        self.root.minsize(740, 560)

        # ==== Tema & Palet Warna ====
        self.theme = "light"
        self.colors = self._get_palette(self.theme)

        # Gunakan ttk theme yang netral
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # ==== Header (Gradien) ====
        self.header = tk.Canvas(root, height=68, bd=0, highlightthickness=0, relief="flat", cursor="arrow")
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self._draw_header_gradient)
        # Teks header akan digambar ulang saat resize
        self.header_text_ids = []

        # ==== Area Chat (message bubbles) ====
        container = tk.Frame(root, bg=self.colors["bg"])
        container.pack(padx=12, pady=(8, 6), expand=True, fill="both")

        self.chat_area = scrolledtext.ScrolledText(
            container, wrap=tk.WORD, state="disabled",
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
            bg=self.colors["panel"], fg=self.colors["text"],
            insertbackground=self.colors["text"]
        )
        self.chat_area.pack(expand=True, fill="both")

        # Tag untuk gaya bubble dan teks
        self._configure_text_tags()

        # ==== Input Area ====
        input_bar = tk.Frame(root, bg=self.colors["bg"])
        input_bar.pack(padx=12, pady=(0, 6), fill="x")

        self.input_text = tk.Text(
            input_bar, height=2, wrap=tk.WORD,
            font=("Segoe UI", 10),
            bg=self.colors["panel"], fg=self.colors["muted"],
            bd=0, highlightthickness=1, highlightbackground=self.colors["border"],
            insertbackground=self.colors["text"]
        )
        self.input_text.pack(side="left", expand=True, fill="x", ipadx=8, ipady=6, padx=(0, 8))
        self._placeholder = "Ketik pertanyaan Anda… (Enter = kirim, Shift+Enter = baris baru)"
        self._show_placeholder()

        # Tombol kiri-kanan
        btn_frame = tk.Frame(input_bar, bg=self.colors["bg"])
        btn_frame.pack(side="right")

        self.theme_btn = tk.Button(
            btn_frame, text="🌙", font=("Segoe UI Symbol", 11),
            bd=0, relief="ridge", cursor="hand2",
            fg=self.colors["text"], bg=self.colors["panel"],
            activebackground=self.colors["panel"]
        )
        self.theme_btn.config(command=self.toggle_theme)
        self.theme_btn.grid(row=0, column=0, padx=(0, 6))

        self.clear_btn = tk.Button(
            btn_frame, text="🧹", font=("Segoe UI Symbol", 11),
            bd=0, relief="ridge", cursor="hand2",
            fg=self.colors["text"], bg=self.colors["panel"],
            activebackground=self.colors["panel"], command=self.clear_chat
        )
        self.clear_btn.grid(row=0, column=1, padx=(0, 6))

        self.send_button = tk.Button(
            btn_frame, text="Kirim ➤", font=("Segoe UI", 10, "bold"),
            fg="white", bg=self.colors["accent"], activeforeground="white",
            activebackground=self.colors["accent_active"], bd=0,
            padx=14, pady=6, cursor="hand2", command=self.send_message
        )
        self.send_button.grid(row=0, column=2)

        # ==== Status Bar ====
        self.status = tk.Label(
            root,
            text=self._build_status_text(),
            anchor="w",
            font=("Segoe UI", 9),
            bg=self.colors["bg"], fg=self.colors["muted"]
        )
        self.status.pack(fill="x", padx=12, pady=(0, 10))

        # ==== Event Bindings ====
        self.input_text.bind("<FocusIn>", self._on_focus_in)
        self.input_text.bind("<FocusOut>", self._on_focus_out)
        self.input_text.bind("<Return>", self._on_return_send)
        self.input_text.bind("<Shift-Return>", self._on_shift_return_newline)
        self.root.bind("<Control-l>", lambda e: (self.input_text.focus_set(), "break"))

        # ==== Queue & Thinking indicator ====
        self.queue = queue.Queue()
        self.is_busy = False
        self.thinking_start_index = None
        self.dots_job = None
        self.dots_state = 0

        self.root.after(100, self.check_queue)

        # Sapaan awal
        self.add_message("bot", "Halo! Selamat datang 👋\nTalent seperti apa yang ingin Anda cari hari ini?")
        # Gambar header text pertama kali
        self._redraw_header_text()

    # ---------- Tema & Palet ----------
    def _get_palette(self, mode="light"):
        if mode == "dark":
            return {
                "bg": "#0B1220",
                "panel": "#111827",
                "text": "#E5E7EB",
                "muted": "#9CA3AF",
                "border": "#1F2937",
                "accent": "#0EA5E9",
                "accent_active": "#0284C7",
                "user_bubble": "#064E3B",
                "bot_bubble": "#0C4A6E",
                "meta": "#94A3B8",
                "grad_start": "#1D4ED8",
                "grad_end": "#059669",
            }
        return {
            "bg": "#F8FAFC",
            "panel": "#FFFFFF",
            "text": "#0F172A",
            "muted": "#64748B",
            "border": "#E2E8F0",
            "accent": "#0EA5E9",
            "accent_active": "#0284C7",
            "user_bubble": "#DCFCE7",
            "bot_bubble": "#E0F2FE",
            "meta": "#64748B",
            "grad_start": "#0EA5E9",
            "grad_end": "#22C55E",
        }

    def apply_theme(self):
        # Frame & background
        self.root.configure(bg=self.colors["bg"])
        self.header.configure(bg=self.colors["bg"])
        self.chat_area.configure(bg=self.colors["panel"], fg=self.colors["text"], insertbackground=self.colors["text"])
        self.status.configure(bg=self.colors["bg"], fg=self.colors["muted"])
        # Input area & buttons
        self.input_text.configure(
            bg=self.colors["panel"], fg=self.colors["text" if not self._is_placeholder() else "muted"],
            highlightbackground=self.colors["border"], insertbackground=self.colors["text"]
        )
        for btn in (self.theme_btn, self.clear_btn):
            btn.configure(bg=self.colors["panel"], fg=self.colors["text"], activebackground=self.colors["panel"])
        self.send_button.configure(bg=self.colors["accent"], activebackground=self.colors["accent_active"])

        # Tag colors
        self._configure_text_tags()
        # Header redraw
        self._draw_header_gradient(None)
        self._redraw_header_text()

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.colors = self._get_palette(self.theme)
        self.theme_btn.config(text="☀️" if self.theme == "dark" else "🌙")
        self.apply_theme()

    # ---------- Header Gradient ----------
    def _draw_header_gradient(self, event):
        c = self.header
        c.delete("grad", "label")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 2:
            return
        # gradient horizontal
        r1, g1, b1 = self.root.winfo_rgb(self.colors["grad_start"])
        r2, g2, b2 = self.root.winfo_rgb(self.colors["grad_end"])
        steps = max(1, w)
        for i in range(steps):
            nr = int(r1 + (r2 - r1) * i / steps) >> 8
            ng = int(g1 + (g2 - g1) * i / steps) >> 8
            nb = int(b1 + (b2 - b1) * i / steps) >> 8
            color = f"#{nr:02x}{ng:02x}{nb:02x}"
            c.create_line(i, 0, i, h, fill=color, tags="grad")
        self._redraw_header_text()

    def _redraw_header_text(self):
        c = self.header
        c.delete("label")
        w = c.winfo_width()
        h = c.winfo_height()
        title = "Chatbot Database Talent"
        subtitle = "Cari & ringkas data talent langsung dari database Anda"
        c.create_text(w//2, h//2 - 6, text=title, fill="white", font=("Segoe UI", 14, "bold"), tags="label")
        c.create_text(w//2, h//2 + 14, text=subtitle, fill="white", font=("Segoe UI", 10), tags="label")

    # ---------- Text Tags / Bubbles ----------
    def _configure_text_tags(self):
        t = self.chat_area
        # Reset & define
        t.tag_configure("left", lmargin1=12, lmargin2=12, rmargin=80, justify="left")
        t.tag_configure("right", lmargin1=80, lmargin2=80, rmargin=12, justify="right")

        t.tag_configure("label_bot", foreground=self.colors["meta"], font=("Segoe UI", 9, "bold"))
        t.tag_configure("label_user", foreground=self.colors["meta"], font=("Segoe UI", 9, "bold"), justify="right")

        t.tag_configure("bot_bubble",
                        background=self.colors["bot_bubble"], spacing1=4, spacing3=6,
                        lmargin1=12, lmargin2=12, rmargin=80)
        t.tag_configure("user_bubble",
                        background=self.colors["user_bubble"], spacing1=4, spacing3=6,
                        lmargin1=80, lmargin2=80, rmargin=12, justify="right")

        t.tag_configure("time_left", foreground=self.colors["meta"], font=("Segoe UI", 8, "italic"), lmargin1=12, lmargin2=12, rmargin=80)
        t.tag_configure("time_right", foreground=self.colors["meta"], font=("Segoe UI", 8, "italic"), lmargin1=80, lmargin2=80, rmargin=12, justify="right")

        t.tag_configure("bot_thinking", foreground=self.colors["muted"], font=("Segoe UI", 10, "italic"))

    # ---------- Helpers ----------
    def _build_status_text(self):
        key_ok = "OK" if openai.api_key else "Tidak ada"
        db_ok = all(DB_CONFIG.get(k) for k in ("host", "user", "database"))
        return f"API Key: {key_ok}   •   DB Config: {'OK' if db_ok else 'Tidak lengkap'}"

    def _is_placeholder(self):
        return self.input_text.get("1.0", "end-1c") == "" and self.input_text.cget("fg") == self.colors["muted"]

    def _show_placeholder(self):
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", self._placeholder)
        self.input_text.configure(fg=self.colors["muted"])

    def _clear_placeholder(self):
        if self._is_placeholder():
            self.input_text.delete("1.0", tk.END)
            self.input_text.configure(fg=self.colors["text"])

    # ---------- Message Handling ----------
    def add_message(self, role, text):
        """
        role: 'bot' atau 'user'
        """
        self.chat_area.config(state="normal")

        ts = datetime.now().strftime("%H:%M")
        if role == "bot":
            # Label
            self.chat_area.insert(tk.END, "Chatbot\n", ("label_bot", "left"))
            # Bubble
            self.chat_area.insert(tk.END, f"{text}\n", ("bot_bubble",))
            # Time
            self.chat_area.insert(tk.END, f"{ts}\n\n", ("time_left",))
        else:
            # Label
            self.chat_area.insert(tk.END, "Anda\n", ("label_user", "right"))
            # Bubble
            self.chat_area.insert(tk.END, f"{text}\n", ("user_bubble", "right"))
            # Time
            self.chat_area.insert(tk.END, f"{ts}\n\n", ("time_right", "right"))

        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)

    def show_thinking(self):
        """Tampilkan indikator 'sedang mengetik...' di area chat dan animasikan titik."""
        if self.thinking_start_index is not None:
            return
        self.chat_area.config(state="normal")
        self.thinking_start_index = self.chat_area.index(tk.END)
        self.chat_area.insert(tk.END, "Chatbot\n", ("label_bot", "left"))
        self.chat_area.insert(tk.END, "Sedang mengetik", ("bot_thinking", "left"))
        self.chat_area.insert(tk.END, "…\n\n", ("bot_thinking", "left"))
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)
        self._animate_dots()

    def hide_thinking(self):
        if self.thinking_start_index is None:
            return
        # Hapus dari thinking_start_index sampai akhir
        self.chat_area.config(state="normal")
        self.chat_area.delete(self.thinking_start_index, tk.END)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)
        self.thinking_start_index = None
        # Stop animasi
        if self.dots_job is not None:
            self.root.after_cancel(self.dots_job)
            self.dots_job = None
            self.dots_state = 0

    def _animate_dots(self):
        if self.thinking_start_index is None:
            return
        # Update tiga titik "…"
        self.dots_state = (self.dots_state + 1) % 4
        dots = "." * self.dots_state if self.dots_state else "…"
        # Ganti baris terakhir yang berisi titik
        self.chat_area.config(state="normal")
        # Hapus dua baris terakhir dari indikator (titik + newline kosong)
        end_index = self.chat_area.index(tk.END)
        # Cari posisi tepat sebelum 2 newline terakhir (aman untuk indikator yang baru ditambahkan)
        # Sederhanakan: hapus 3 karakter terakhir lalu tulis ulang
        try:
            self.chat_area.delete("end-3c", "end-1c")
            self.chat_area.insert(tk.END, dots, ("bot_thinking", "left"))
        except Exception:
            pass
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)
        self.dots_job = self.root.after(450, self._animate_dots)

    # ---------- Events ----------
    def _on_focus_in(self, _):
        self._clear_placeholder()

    def _on_focus_out(self, _):
        if self.input_text.get("1.0", "end-1c").strip() == "":
            self._show_placeholder()

    def _on_shift_return_newline(self, _):
        # Biarkan newline
        return

    def _on_return_send(self, event):
        # Enter = kirim, kecuali jika Shift ditekan
        if event.state & 0x0001:  # Shift mask
            return
        self.send_message()
        return "break"

    def _get_input(self):
        txt = self.input_text.get("1.0", "end-1c")
        if self._is_placeholder():
            return ""
        return txt.strip()

    def _clear_input(self):
        self.input_text.delete("1.0", tk.END)

    # ---------- Action ----------
    def send_message(self):
        if self.is_busy:
            return
        user_input = self._get_input()
        if not user_input:
            return
        # Tampilkan pesan user
        self.add_message("user", user_input)
        # Persiapkan UI untuk proses
        self._clear_input()
        self._show_placeholder()
        self.is_busy = True
        self.send_button.config(state=tk.DISABLED)
        self.show_thinking()
        # Proses di background
        threading.Thread(target=self.process_in_background, args=(user_input,), daemon=True).start()

    def process_in_background(self, user_input):
        sql_query = generate_sql_query(user_input)
        if "ERROR_API" in sql_query:
            self.queue.put(f"Terjadi masalah saat meminta AI menyusun query.\nDetail: {sql_query}")
            return
        if not sql_query or sql_query.upper() == "INVALID":
            self.queue.put("Maaf, saya hanya bisa membantu Anda untuk mencari data talent.")
            return
        db_results, error = execute_sql_query(sql_query)
        if error:
            self.queue.put(f"Terjadi kesalahan saat mengakses database: {error}")
            return
        final_answer = interpret_results(user_input, db_results)
        self.queue.put(final_answer)

    def check_queue(self):
        try:
            message = self.queue.get_nowait()
            self.hide_thinking()
            self.add_message("bot", message)
            self.is_busy = False
            self.send_button.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def clear_chat(self):
        if messagebox.askyesno("Bersihkan Chat", "Hapus semua percakapan?"):
            self.chat_area.config(state="normal")
            self.chat_area.delete("1.0", tk.END)
            self.chat_area.config(state="disabled")
            self.add_message("bot", "Chat telah dibersihkan. Silakan ajukan pertanyaan baru.")
            self.input_text.focus_set()

# ==============================================================================
# BAGIAN 3: MENJALANKAN APLIKASI
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = ChatbotApp(root)
    app.apply_theme()  # Pastikan palet terpasang
    root.mainloop()
