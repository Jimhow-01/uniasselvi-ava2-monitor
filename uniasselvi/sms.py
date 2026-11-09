"""Notificação por SMS via Twilio ou Zenvia.

Credenciais (token) cifradas com DPAPI do Windows em .cred_sms — nunca em texto puro.
Sempre retorna (ok, mensagem) para a UI/log poderem explicar falhas.
"""
import base64
import json
import logging
import os

import requests

from .config import APP_DIR

log = logging.getLogger("uniasselvi.sms")
_CRED_PATH = os.path.join(APP_DIR, ".cred_sms")


# ---------------- credenciais ----------------
def _dpapi_available():
    try:
        import win32crypt  # noqa: F401
        return True
    except Exception:
        return False


def save_sms_credentials(provider: str, token: str, account_sid: str = "", sender: str = ""):
    data = {"provider": provider, "token": token,
            "account_sid": account_sid, "sender": sender}
    blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if _dpapi_available():
        import win32crypt
        enc = win32crypt.CryptProtectData(blob, "uniasselvi-sms", None, None, None, 0)
        with open(_CRED_PATH, "wb") as f:
            f.write(base64.b64encode(enc))
    else:
        with open(_CRED_PATH, "wb") as f:
            f.write(blob)


def load_sms_credentials():
    if not os.path.exists(_CRED_PATH):
        return None
    try:
        with open(_CRED_PATH, "rb") as f:
            raw = f.read()
        if _dpapi_available():
            try:
                import win32crypt
                blob = win32crypt.CryptUnprotectData(base64.b64decode(raw), None, None, None, 0)[1]
            except Exception:
                blob = raw
        else:
            blob = raw
        data = json.loads(blob.decode("utf-8"))
        if data.get("token"):
            return data
    except Exception:
        return None
    return None


def sms_configured(cfg):
    return bool(cfg.get("sms_enabled") and cfg.get("sms_to") and load_sms_credentials())


# ---------------- envio ----------------
def _send_twilio(creds, to, text):
    sid, token = creds.get("account_sid"), creds.get("token")
    frm = creds.get("sender")
    if not sid or not token:
        return False, "Twilio sem Account SID / AuthToken"
    if not frm:
        return False, "Twilio exige um número remetente (alugado na Twilio, ~US$1,15/mês)"
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"To": to, "From": frm, "Body": text},
        auth=(sid, token), timeout=25)
    if r.status_code in (200, 201):
        return True, "SMS enviado (Twilio)"
    try:
        msg = r.json().get("message", r.text[:200])
    except ValueError:
        msg = r.text[:200]
    return False, f"Twilio HTTP {r.status_code}: {msg}"


def _send_zenvia(creds, to, text):
    token = creds.get("token")
    if not token:
        return False, "Zenvia sem API token"
    sender = creds.get("sender") or "Zenvia"
    # NOTE: o strip original removia '+', ' ' e '-' mas NAO parenteses, entao um
    # numero digitado como "+55 (51) 99999-9999" chegava como "55(51)999999999"
    # e a Zenvia recusava. Normalizar por digitos cobre todos os formatos.
    zto = "".join(ch for ch in to if ch.isdigit())
    r = requests.post(
        "https://api.zenvia.com/v2/channels/sms/messages",
        json={"from": sender, "to": zto,
              "contents": [{"type": "text", "text": text}]},
        headers={"X-API-TOKEN": token, "Content-Type": "application/json"},
        timeout=25)
    if r.status_code in (200, 201, 202):
        return True, "SMS enviado (Zenvia)"
    return False, f"Zenvia HTTP {r.status_code}: {r.text[:200]}"


def send_sms(cfg, text: str):
    """Envia um SMS (truncado a 160 chars = 1 segmento, sem custo extra de multi-segmento)."""
    creds = load_sms_credentials()
    to = (cfg.get("sms_to") or "").strip()
    if not creds or not to:
        return False, "SMS não configurado (telefone/token)"
    text = text[:160]
    provider = creds.get("provider", "zenvia")
    try:
        if provider == "twilio":
            return _send_twilio(creds, to, text)
        return _send_zenvia(creds, to, text)
    except requests.RequestException as e:
        return False, f"Falha de rede no SMS: {e}"
