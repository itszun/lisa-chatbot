# app.py (Versi Final Tanpa Validasi Awal)
# -*- coding: utf-8 -*-
from tools_registry import Helper
from feeder import Feeder
from dataclasses import dataclass
import os
import json
from uuid import uuid4
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from api_client import ensure_token
from prompt import TemplatePrompt
from agent.lisa import Lisa
import json
from agent.tools import tools, retrieve_prompt, fetch_user_data
from logs import setup_logging
# ======================================================================
# KONFIGURASI UMUM
# ======================================================================
MAX_HISTORY_MESSAGES = 100

Helper().register(tools=tools,
                  retrieve_prompt=retrieve_prompt,
                  fetch_user_data=fetch_user_data)

load_dotenv()
setup_logging()

def create_app(config_name=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "fallback-key")

    from admin_panel.admin import init_admin
    init_admin(app) 

    from api_blueprint import api_bp 
    app.register_blueprint(api_bp)

    app.logger.info("Application setup complete.")
    
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True,
            use_reloader=False, threaded=True)