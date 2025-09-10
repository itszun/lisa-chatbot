# api_client.py
# -*- coding: utf-8 -*-

import os
import json
import time
import pathlib
import logging
from typing import Any, Dict, List, Optional, Callable, Tuple

import requests

# ===================== ENV LOADER =====================
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ===================== KONFIG DASAR =====================
BASE_URL = os.getenv("REMOTE_BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REMOTE_BASE_URL belum diisi. Contoh: https://lisa.malikaljun.com")

PANEL = (os.getenv("REMOTE_API_PANEL", "admin") or "admin").strip()
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() != "false"

# (Opsional) Debug HTTP
if os.getenv("DEBUG_HTTP", "false").lower() == "true":
    try:
        import http.client as http_client
    except Exception:
        import httplib as http_client  # type: ignore
    http_client.HTTPConnection.debuglevel = 1
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("urllib3").setLevel(logging.DEBUG)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)

# Lokasi cache token (buat folder jika belum ada)
TOKEN_CACHE = pathlib.Path("lisa_python/.token_cache.json")
TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)

# ===================== SESSION =====================
S = requests.Session()
# Jika ingin memaksa bypass proxy environment:
if os.getenv("FORCE_BYPASS_PROXY", "false").lower() == "true":
    S.trust_env = False

ACCESS_TOKEN: Optional[str] = os.getenv("ACCESS_TOKEN")
# ===================== UTIL UMUM =====================
def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text}

def _auth_headers() -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    return h

def _get(url: str, **kw):
    kw.setdefault("headers", _auth_headers())
    kw.setdefault("timeout", 25)
    kw.setdefault("verify", VERIFY_SSL)
    return S.get(url, **kw)

def _post(url: str, **kw):
    kw.setdefault("headers", _auth_headers())
    kw.setdefault("timeout", 25)
    kw.setdefault("verify", VERIFY_SSL)
    return S.post(url, **kw)

def _put(url: str, **kw):
    kw.setdefault("headers", _auth_headers())
    kw.setdefault("timeout", 25)
    kw.setdefault("verify", VERIFY_SSL)
    return S.put(url, **kw)

def _delete(url: str, **kw):
    kw.setdefault("headers", _auth_headers())
    kw.setdefault("timeout", 25)
    kw.setdefault("verify", VERIFY_SSL)
    return S.delete(url, **kw)

def _raise_on_error(r: requests.Response, op_desc: str):
    if r.status_code == 401:
        raise PermissionError(f"Unauthorized (401) saat {op_desc}. Token salah/kadaluarsa/DB berbeda.")
    if r.status_code >= 400:
        raise RuntimeError(f"Server {r.status_code} saat {op_desc} ({r.url})\n{r.text[:1200]}")

# ===================== TOKEN HANDLER =====================
def _save_token(token: str):
    try:
        TOKEN_CACHE.write_text(json.dumps({"token": token}, ensure_ascii=False))
    except Exception:
        pass

def _load_token() -> Optional[str]:
    if TOKEN_CACHE.exists():
        try:
            return json.loads(TOKEN_CACHE.read_text()).get("token")
        except Exception:
            return None
    return None

def set_token(token: str):
    """Set token dari luar (mis. dari Flask) dan simpan ke cache."""
    global ACCESS_TOKEN
    ACCESS_TOKEN = (token or "").strip()
    if ACCESS_TOKEN:
        _save_token(ACCESS_TOKEN)

def clear_token():
    """Hapus token di memori & cache."""
    global ACCESS_TOKEN
    ACCESS_TOKEN = None
    try:
        if TOKEN_CACHE.exists():
            TOKEN_CACHE.unlink()
    except Exception:
        pass

def _extract_token_from_resp(r: requests.Response) -> Optional[str]:
    j = _safe_json(r)
    return j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token")

def _ping_with_token(token: str) -> Tuple[bool, Optional[int]]:
    test_url = f"{BASE_URL}/api/{PANEL}/talent"
    try:
        rr = S.get(
            test_url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
            params={"page": 1, "per_page": 1},
            timeout=15,
            verify=VERIFY_SSL,
        )
        if rr.status_code == 200:
            return True, 200
        if rr.status_code == 401:
            return False, 401
        return True, rr.status_code
    except requests.RequestException:
        return True, None

def login_and_get_token(email: str, password: str) -> str:
    url = f"{BASE_URL}/api/auth/login"
    print(url)

    # x-www-form-urlencoded
    r = S.post(
        url,
        headers={"Accept": "application/json"},
        data={"email": email, "password": password},
        verify=VERIFY_SSL,
        timeout=25,
    )
    if r.ok:
        tok = _extract_token_from_resp(r)
        if tok:
            return tok

    # JSON
    r = S.post(
        url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"email": email, "password": password},
        verify=VERIFY_SSL,
        timeout=25,
    )
    if r.ok:
        tok = _extract_token_from_resp(r)
        if tok:
            return tok

    # multipart/form-data
    r = S.post(
        url,
        headers={"Accept": "application/json"},
        files={"email": (None, email), "password": (None, password)},
        verify=VERIFY_SSL,
        timeout=25,
    )
    if r.ok:
        tok = _extract_token_from_resp(r)
        if tok:
            return tok

    raise RuntimeError(f"Gagal login (HTTP {r.status_code}): {r.text[:500]}")

def ensure_token(preferred_token: Optional[str] = None):
    """
    Server-mode: pastikan ACCESS_TOKEN siap.
      - Jika preferred_token ada (mis. dari header Flask) -> validasi ringan -> pakai.
      - Jika tidak ada, coba dari cache -> validasi -> pakai.
      - Jika tidak ada/invalid, coba login via env LOGIN_EMAIL/LOGIN_PASSWORD.
      - Jika semua gagal -> raise PermissionError.
    """
    global ACCESS_TOKEN
    return True

    # 0) Token dikirim dari caller (Flask header) -> prioritas
    if preferred_token:
        ok, _ = _ping_with_token(preferred_token)
        if ok:
            ACCESS_TOKEN = preferred_token
            _save_token(ACCESS_TOKEN)
            return
        else:
            raise PermissionError("Token dari header tidak valid (401).")

    # 1) Coba token dari cache
    cached = _load_token()
    if cached:
        ok, _ = _ping_with_token(cached)
        if ok:
            ACCESS_TOKEN = cached
            return
        else:
            clear_token()

    # 2) Coba login otomatis dari env
    email = os.getenv("LOGIN_EMAIL")
    password = os.getenv("LOGIN_PASSWORD")
    print(email, password)

    if email and password:
        tok = login_and_get_token(email, password)
        set_token(tok)
        return

    # 3) Tidak ada cara lain di server-mode
    raise PermissionError("Tidak ada token atau kredensial login env. Set 'Authorization: Bearer <token>' atau LOGIN_EMAIL/PASSWORD.")

def relogin_once_on_401(func: Callable, *args, **kwargs):
    """
    Jalankan fungsi API. Jika 401 -> coba login via env sekali -> ulangi request.
    """
    global ACCESS_TOKEN
    print("ACCESS TOKEN")

    try:
        return func(*args, **kwargs)
    except PermissionError:
        email = os.getenv("LOGIN_EMAIL")
        password = os.getenv("LOGIN_PASSWORD")
        print(email, password)

        if not (email and password):
            raise
        # Re-login via env
        ACCESS_TOKEN = login_and_get_token(email, password)
        _save_token(ACCESS_TOKEN)
        return func(*args, **kwargs)

# ===================== GENERIC CRUD PER RESOURCE =====================
def _list_resource(resource: str, page: int = 1, per_page: int = 10, search: Optional[str] = None) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/api/{PANEL}/{resource}"
    params = {"page": page, "per_page": per_page}
    if search:
        params["search"] = search
    r = _get(url, params=params)
    _raise_on_error(r, f"GET list {resource}")
    data = _safe_json(r)
    items = data["data"] if isinstance(data, dict) and "data" in data else data
    return items or []

def _get_detail(resource: str, rid: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/{PANEL}/{resource}/{rid}"
    r = _get(url)
    _raise_on_error(r, f"GET detail {resource} id {rid}")
    data = _safe_json(r)
    return data["data"] if isinstance(data, dict) and "data" in data else data

def _create_resource(resource: str, payload: Dict[str, Any]) -> Any:
    url = f"{BASE_URL}/api/{PANEL}/{resource}"
    r = _post(url, json=payload | {"_method": "POST"})
    _raise_on_error(r, f"POST create {resource}")
    return _safe_json(r)

def _update_resource(resource: str, rid: int, payload: Dict[str, Any]) -> Any:
    url = f"{BASE_URL}/api/{PANEL}/{resource}/{rid}"
    r = _put(url, json=payload)
    _raise_on_error(r, f"PUT update {resource} id {rid}")
    return _safe_json(r)

def _delete_resource(resource: str, rid: int) -> Any:
    url = f"{BASE_URL}/api/{PANEL}/{resource}/{rid}"
    r = _delete(url)
    if r.status_code in (200, 204):
        return {"deleted": True}
    _raise_on_error(r, f"DELETE {resource} id {rid}")
    return {"deleted": True}

# ===================== RESOURCE: TALENT =====================
def list_talent(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    return relogin_once_on_401(_list_resource, "talent", page, per_page, search)

def get_talent_detail(talent_id: int):
    return relogin_once_on_401(_get_detail, "talent", talent_id)

def create_talent(name: str, position: str, birthdate: str, summary: str):
    payload = {"name": name, "position": position, "birthdate": birthdate, "summary": summary}
    return relogin_once_on_401(_create_resource, "talent", payload)

def update_talent(talent_id: int, name: Optional[str] = None, position: Optional[str] = None,
                  birthdate: Optional[str] = None, summary: Optional[str] = None):
    payload: Dict[str, Any] = {}
    if name is not None: payload["name"] = name
    if position is not None: payload["position"] = position
    if birthdate is not None: payload["birthdate"] = birthdate
    if summary is not None: payload["summary"] = summary
    return relogin_once_on_401(_update_resource, "talent", talent_id, payload)

def delete_talent(talent_id: int):
    return relogin_once_on_401(_delete_resource, "talent", talent_id)

# ===================== RESOURCE: CANDIDATES =====================
def list_candidates(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    return relogin_once_on_401(_list_resource, "candidates", page, per_page, search)

def get_candidate_detail(candidate_id: int):
    return relogin_once_on_401(_get_detail, "candidates", candidate_id)

def create_candidate(payload: Dict[str, Any]):
    return relogin_once_on_401(_create_resource, "candidates", payload)

def update_candidate(candidate_id: int, payload: Dict[str, Any]):
    return relogin_once_on_401(_update_resource, "candidates", candidate_id, payload)

def delete_candidate(candidate_id: int):
    return relogin_once_on_401(_delete_resource, "candidates", candidate_id)

# ===================== RESOURCE: COMPANIES =====================
def list_companies(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    return relogin_once_on_401(_list_resource, "companies", page, per_page, search)

def get_company_detail(company_id: int):
    return relogin_once_on_401(_get_detail, "companies", company_id)

def create_company(payload: Dict[str, Any]):
    return relogin_once_on_401(_create_resource, "companies", payload)

def update_company(company_id: int, payload: Dict[str, Any]):
    return relogin_once_on_401(_update_resource, "companies", company_id, payload)

def delete_company(company_id: int):
    return relogin_once_on_401(_delete_resource, "companies", company_id)

# ===================== RESOURCE: COMPANY PROPERTIES =====================
def list_company_properties(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    return relogin_once_on_401(_list_resource, "company-properties", page, per_page, search)

def get_company_property_detail(prop_id: int):
    return relogin_once_on_401(_get_detail, "company-properties", prop_id)

def create_company_property(payload: Dict[str, Any]):
    return relogin_once_on_401(_create_resource, "company-properties", payload)

def update_company_property(prop_id: int, payload: Dict[str, Any]):
    return relogin_once_on_401(_update_resource, "company-properties", prop_id, payload)

def delete_company_property(prop_id: int):
    return relogin_once_on_401(_delete_resource, "company-properties", prop_id)

# ===================== RESOURCE: JOB OPENINGS =====================
def list_job_openings(page: int = 1, per_page: int = 10, search: Optional[str] = None):
    return relogin_once_on_401(_list_resource, "job-openings", page, per_page, search)

def get_job_opening_detail(opening_id: int):
    return relogin_once_on_401(_get_detail, "job-openings", opening_id)

def create_job_opening(payload: Dict[str, Any]):
    return relogin_once_on_401(_create_resource, "job-openings", payload)

def update_job_opening(opening_id: int, payload: Dict[str, Any]):
    return relogin_once_on_401(_update_resource, "job-openings", opening_id, payload)

def delete_job_opening(opening_id: int):
    return relogin_once_on_401(_delete_resource, "job-openings", opening_id)
