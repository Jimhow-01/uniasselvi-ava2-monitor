"""Configuração do app: config.json + senha protegida via DPAPI (Windows)."""
import base64
import json
import os
import sys

# Em exe congelado (PyInstaller): dados ao lado do .exe; assets dentro do bundle.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    ASSETS_DIR = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets")
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ASSETS_DIR = os.path.join(APP_DIR, "assets")

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATE_PATH = os.path.join(APP_DIR, "state.json")

DEFAULTS = {
    "cpf": "",
    "alert_days": 3,          # notificar (toast) quando faltarem <= N dias
    "view_days": 5,           # aba "Pendentes" do painel mostra até N dias à frente
    "check_times": ["08:30", "18:30"],
    "area": "EAD",            # (desusado; a área real vem dos dados do aluno)
    "specialization": "",     # código da especialização (vazio = usar a primeira da lista)
    "include_complementary": True,
    "include_calendar": True,
    "quiet_hours": {"start": "22:00", "end": "07:00"},  # não disparar toast nesse horário
    "sms_enabled": False,     # enviar SMS além do toast
    "sms_to": "",             # telefone com código do país, ex.: +5551999999999
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            for k in DEFAULTS:
                if k in data:
                    cfg[k] = data[k]
        except Exception:
            pass
    return cfg


def save_config(cfg):
    data = {k: cfg.get(k) for k in DEFAULTS}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------- senha ----------------
# Guardada em .cred (bytes cifrados com DPAPI do usuário Windows).
_CRED_PATH = os.path.join(APP_DIR, ".cred")


def _dpapi_available():
    try:
        import win32crypt  # noqa: F401
        return True
    except Exception:
        return False


def save_password(password: str):
    if _dpapi_available():
        import win32crypt
        blob = win32crypt.CryptProtectData(
            password.encode("utf-8"), "uniasselvi-app", None, None, None, 0
        )
        with open(_CRED_PATH, "wb") as f:
            f.write(base64.b64encode(blob))
        return "dpapi"
    # fallback: arquivo local (mantido fora do config.json)
    with open(_CRED_PATH + ".plain", "w", encoding="utf-8") as f:
        json.dump({"password": password}, f)
    return "plain"


def load_password():
    if os.path.exists(_CRED_PATH):
        try:
            with open(_CRED_PATH, "rb") as f:
                blob = base64.b64decode(f.read())
            if _dpapi_available():
                import win32crypt
                return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8")
        except Exception:
            return None
    if os.path.exists(_CRED_PATH + ".plain"):
        try:
            with open(_CRED_PATH + ".plain", encoding="utf-8") as f:
                return json.load(f).get("password")
        except Exception:
            return None
    return None


def has_password():
    return load_password() is not None
