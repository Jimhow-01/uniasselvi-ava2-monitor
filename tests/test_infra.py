"""Testes de infra: lock de instancia unica, custodia de credencial, citacao
PowerShell e normalizacao de telefone.

Os testes de DPAPI rodam em duas camadas: a logica de round-trip quando
pywin32 existe (Windows) e o comportamento do fallback quando nao existe
(Linux/CI), que e justamente o caminho que importa documentar.
"""
import json
import os

import pytest

from uniasselvi import config as cfgmod
from uniasselvi import instance, notifier, sms


# ---------------------------------------------------------------- lock de instancia
def test_claim_monitor_cria_pid(tmp_path):
    assert instance.claim_monitor() is True
    pid_file = tmp_path / "monitor.pid"
    assert pid_file.exists()
    assert int(pid_file.read_text(encoding="utf-8")) == os.getpid()


def test_claim_monitor_recusa_quando_ha_lock_vivo(tmp_path):
    # outro processo vivo: PID valido + nome comecando com 'python'
    (tmp_path / "monitor.pid").write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch_alive = True
    original = instance._pid_alive
    instance._pid_alive = lambda pid: monkeypatch_alive
    try:
        assert instance.claim_monitor() is False
    finally:
        instance._pid_alive = original


def test_claim_monitor_recupera_lock_de_processo_morto(tmp_path):
    """Um PID velho de execucao anterior nao deve bloquear para sempre."""
    (tmp_path / "monitor.pid").write_text("999999999", encoding="utf-8")
    original = instance._pid_alive
    instance._pid_alive = lambda pid: False
    try:
        assert instance.claim_monitor() is True
        assert int((tmp_path / "monitor.pid").read_text(encoding="utf-8")) == os.getpid()
    finally:
        instance._pid_alive = original


def test_release_monitor_apaga_so_se_e_seu(tmp_path):
    (tmp_path / "monitor.pid").write_text(str(os.getpid()), encoding="utf-8")
    instance.release_monitor()
    assert not (tmp_path / "monitor.pid").exists()


def test_release_monitor_nao_apaga_lock_de_outro(tmp_path):
    (tmp_path / "monitor.pid").write_text("999999999", encoding="utf-8")
    instance.release_monitor()
    # o lock do outro processo sobrevive
    assert (tmp_path / "monitor.pid").exists()


def test_monitor_pid_none_sem_arquivo():
    assert instance.monitor_pid() is None
    assert instance.is_monitor_running() is False


def test_pid_invalido_nao_e_aceito(tmp_path):
    (tmp_path / "monitor.pid").write_text("nao-numero", encoding="utf-8")
    assert instance.monitor_pid() is None


# ---------------------------------------------------------------- DPAPI / fallback
def test_password_dpapi_roundtrip_quando_pywin32_existe(tmp_path):
    if not cfgmod._dpapi_available():
        pytest.skip("DPAPI exige pywin32 (Windows)")
    mode = cfgmod.save_password("senha-de-teste-123")
    assert mode == "dpapi"
    # o arquivo em disco NAO contem a senha em claro
    raw = (tmp_path / ".cred").read_bytes()
    assert b"senha-de-teste-123" not in raw
    assert cfgmod.load_password() == "senha-de-teste-123"


def test_password_fallback_em_texto_puro_sem_dpapi(tmp_path, monkeypatch):
    """NOTE: este teste documenta uma fragilidade real, nao um comportamento desejado.

    Sem pywin32, save_password() grava a senha em `.cred.plain` como JSON legivel.
    """
    monkeypatch.setattr(cfgmod, "_dpapi_available", lambda: False)
    mode = cfgmod.save_password("senha-de-teste-123")
    assert mode == "plain"
    plain = tmp_path / ".cred.plain"
    assert plain.exists()
    # em texto puro, de fato: a senha esta legivel no arquivo
    assert "senha-de-teste-123" in plain.read_text(encoding="utf-8")
    assert cfgmod.load_password() == "senha-de-teste-123"


def test_load_password_none_quando_nada_salvo(tmp_path):
    assert cfgmod.load_password() is None
    assert cfgmod.has_password() is False


def test_has_password_reflete_o_arquivo(tmp_path):
    if not cfgmod._dpapi_available():
        pytest.skip("DPAPI exige pywin32 (Windows)")
    cfgmod.save_password("x")
    assert cfgmod.has_password() is True


def test_load_password_recupera_de_blob_corrompido(tmp_path):
    (tmp_path / ".cred").write_bytes(b"isto nao e base64 de DPAPI")
    assert cfgmod.load_password() is None


# ---------------------------------------------------------------- credenciais de SMS
def test_sms_credentials_roundtrip(tmp_path):
    sms.save_sms_credentials("zenvia", "token-de-teste", "", "Remetente")
    creds = sms.load_sms_credentials()
    assert creds["provider"] == "zenvia"
    assert creds["token"] == "token-de-teste"


def test_sms_credentials_sem_arquivo(tmp_path):
    assert sms.load_sms_credentials() is None


def test_sms_credentials_sem_token_contam_como_nao_configurado(tmp_path):
    (tmp_path / ".cred_sms").write_text(json.dumps({"provider": "zenvia", "token": ""}),
                                        encoding="utf-8")
    assert sms.load_sms_credentials() is None
    assert sms.sms_configured({"sms_enabled": True, "sms_to": "+5551999999999"}) is False


def test_sms_configured_exige_habilitado_destino_e_credencial(tmp_path):
    sms.save_sms_credentials("zenvia", "token-de-teste")
    assert sms.sms_configured({"sms_enabled": True, "sms_to": "+5551999999999"}) is True
    assert sms.sms_configured({"sms_enabled": False, "sms_to": "+5551999999999"}) is False
    assert sms.sms_configured({"sms_enabled": True, "sms_to": ""}) is False
    assert sms.sms_configured({}) is False


def test_sms_fallback_texto_puro_sem_dpapi(tmp_path, monkeypatch):
    """Mesma fragilidade da senha: sem DPAPI o token de SMS vai em claro."""
    monkeypatch.setattr(sms, "_dpapi_available", lambda: False)
    sms.save_sms_credentials("twilio", "ACtokenfake", "ACsid", "+15551234567")
    raw = (tmp_path / ".cred_sms").read_bytes()
    assert b"ACtokenfake" in raw, "sem DPAPI o token fica legivel em disco"
    assert sms.load_sms_credentials()["token"] == "ACtokenfake"


# ---------------------------------------------------------------- normalizacao de telefone
def test_zenvia_strip_de_sinais_do_telefone(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 201

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["to"] = json["to"]
        captured["url"] = url
        return FakeResp()

    monkeypatch.setattr(sms.requests, "post", fake_post)
    ok, msg = sms._send_zenvia({"token": "t", "sender": "Rem"}, "+55 (51) 99999-9999", "oi")
    assert ok is True
    assert captured["to"] == "5551999999999", "deve sobrar apenas digitos"
    assert "zenvia.com" in captured["url"]


def test_zenvia_sem_token_nao_faz_requisicao(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("nao deveria chamar a rede")

    monkeypatch.setattr(sms.requests, "post", boom)
    ok, msg = sms._send_zenvia({"token": ""}, "+5551999999999", "oi")
    assert ok is False
    assert "sem API token" in msg


def test_twilio_exige_sid_token_e_remetente(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("nao deveria chamar a rede")

    monkeypatch.setattr(sms.requests, "post", boom)
    ok, msg = sms._send_twilio({"account_sid": "", "token": "t", "sender": "+15"}, "x", "oi")
    assert ok is False and "Account SID" in msg
    ok, msg = sms._send_twilio({"account_sid": "AC1", "token": "", "sender": "+15"}, "x", "oi")
    assert ok is False and "AuthToken" in msg
    ok, msg = sms._send_twilio({"account_sid": "AC1", "token": "t", "sender": ""}, "x", "oi")
    assert ok is False and "remetente" in msg


def test_send_sms_trunca_para_um_segmento(monkeypatch, tmp_path):
    sent = {}

    def fake_zenvia(creds, to, text):
        sent["text"] = text
        return True, "ok"

    monkeypatch.setattr(sms, "_send_zenvia", fake_zenvia)
    sms.save_sms_credentials("zenvia", "token-de-teste")
    cfg = {"sms_enabled": True, "sms_to": "+5551999999999"}
    ok, _ = sms.send_sms(cfg, "x" * 400)
    assert ok is True
    assert len(sent["text"]) == 160, "1 segmento = 160 chars, sem custo extra"


def test_send_sms_sem_configuracao_nao_tenta_enviar(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("nao deveria enviar")

    monkeypatch.setattr(sms, "_send_zenvia", boom)
    monkeypatch.setattr(sms, "_send_twilio", boom)
    ok, msg = sms.send_sms({"sms_enabled": False, "sms_to": ""}, "oi")
    assert ok is False
    assert "não configurado" in msg


# ---------------------------------------------------------------- citacao PowerShell
def test_ps_quote_envolve_em_aspas():
    assert notifier._ps_quote("texto") == "'texto'"


def test_ps_quote_duplica_aspa_simples():
    # aspas simples em PowerShell escapam duplicando: O'Brien -> 'O''Brien'
    assert notifier._ps_quote("O'Brien") == "'O''Brien'"


def test_ps_quote_neutra_contra_injecao_de_aspa():
    """Um titulo com aspa fechadora nao deve escapar do literal PowerShell."""
    quoted = notifier._ps_quote("fim'; Get-Process; 'inicio")
    assert quoted.startswith("'") and quoted.endswith("'")
    inner = quoted[1:-1]
    # todo ' interno aparece em par: nada fecha a string antes da hora
    i = 0
    while i < len(inner):
        if inner[i] == "'":
            assert i + 1 < len(inner) and inner[i + 1] == "'", f"aspa solta no indice {i}"
            i += 2
        else:
            i += 1


def test_ps_quote_trata_non_string():
    assert notifier._ps_quote(42) == "'42'"


# ---------------------------------------------------------------- degradacao de notificacao
def test_notify_cai_para_popup_quando_toasts_falham(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier, "_toast_win11", lambda t, b: False)
    monkeypatch.setattr(notifier, "send_toast", lambda t, b: False)
    monkeypatch.setattr(notifier, "send_popup", lambda t, b: calls.append((t, b)) or True)
    notifier.notify("titulo", "corpo")
    assert calls == [("titulo", "corpo")]


def test_notify_para_no_toast_winrt_sem_popup(monkeypatch):
    popups = []
    monkeypatch.setattr(notifier, "_toast_win11", lambda t, b: False)
    monkeypatch.setattr(notifier, "send_toast", lambda t, b: True)
    monkeypatch.setattr(notifier, "send_popup", lambda t, b: popups.append(t) or True)
    notifier.notify("titulo", "corpo")
    assert popups == [], "sucesso no toast intermediario nao deve abrir popup"


def test_send_toast_monta_script_com_titulo_e_corpo_citados(monkeypatch):
    seen = {}

    class FakeProc:
        returncode = 0
        stderr = b""

    def fake_run(cmd, capture_output=None, timeout=None, creationflags=None):
        seen["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    assert notifier.send_toast("Título com ' aspa", "corpo") is True
    script = seen["cmd"][-1]
    assert "'Título com '' aspa'" in script, "o titulo deve entrar citado no PowerShell"
    assert "%TITLE%" not in script and "%BODY%" not in script, "placeholders substituidos"
