"""
Uniasselvi AVA2 — monitor de provas e trabalhos pendentes.

Uso:
  python app.py gui            abre a janelinha (padrão)
  python app.py login          salva CPF + senha (pergunta no terminal)
  python app.py check          checagem única (notifica se algo vence em <= N dias)
  python app.py watch          loop agendado no terminal (horários do config.json)
"""
import argparse
import getpass
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uniasselvi.config import has_password, load_config, save_config, save_password
from uniasselvi.watcher import run_check, watch_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log"),
                            encoding="utf-8"),
    ],
)
log = logging.getLogger("uniasselvi")


def cmd_login():
    cfg = load_config()
    cpf = input(f"CPF ou e-mail de aluno [{cfg.get('cpf') or '-'}]: ").strip() or cfg.get("cpf", "")
    pw = getpass.getpass("Senha do AVA2 (não fica em texto puro): ")
    if not cpf or not pw:
        print("CPF e senha são obrigatórios.")
        return 1
    cfg["cpf"] = cpf
    save_config(cfg)
    mode = save_password(pw)
    print(f"Senha salva ({mode}). Testando login...")
    from uniasselvi.api import AuthError, UniAPI
    api = UniAPI()
    try:
        api.login(cpf, pw)
        specs = api.get_specializations("ALUN")
        print("Login OK. Cursos encontrados:")
        for s in (specs if isinstance(specs, list) else []):
            print("  -", s.get("name") or s.get("specialization_name"),
                  "| código:", s.get("specialization") or s.get("code") or s.get("espe_codi"),
                  "| modalidade:", s.get("modality") or s.get("modality_name"))
        return 0
    except AuthError as e:
        print("Login falhou:", e)
        return 1


def cmd_check(force=True):
    cfg = load_config()
    if not cfg.get("cpf") or not has_password():
        print("Falta configurar credenciais: rode  python app.py login")
        return 1
    try:
        tasks, alerts, info = run_check(cfg, force=force)
    except Exception as e:
        print("Erro:", e)
        return 1
    print(f"Aluno: {info.get('name')} | Curso: {info.get('course')} | Semestre: {info.get('semester')}")
    up, over = info["upcoming"], info["overdue"]
    if not up and not over:
        print(f"Nada vencendo nos próximos {cfg['alert_days']} dias.")
    for t in over:
        print(f"[ATRASADO] {t.kind}: {t.title} ({t.subject}) venceu em {t.deadline.strftime('%d/%m/%Y')}")
    for t in up:
        print(f"[{t.days_left()}d] {t.kind}: {t.title} — {t.deadline_label} {t.deadline.strftime('%d/%m/%Y')} ({t.subject})")
    print(f"Alertas disparados nesta rodada: {len(alerts)}")
    return 0


def cmd_watch():
    cfg = load_config()
    if not cfg.get("cpf") or not has_password():
        print("Falta configurar credenciais: rode  python app.py login")
        return 1
    print("Monitorando. Horários:", ", ".join(cfg.get("check_times", [])),
          "| alerta a", cfg.get("alert_days"), "dias. Ctrl+C para sair.")
    try:
        watch_loop(cfg)
    except KeyboardInterrupt:
        print("Parado.")
    return 0


def cmd_gui():
    from uniasselvi.gui import run_gui
    return run_gui()


def main():
    p = argparse.ArgumentParser(description="Monitor AVA2 Uniasselvi")
    p.add_argument("command", nargs="?", default="gui",
                   choices=["gui", "login", "check", "watch"])
    args = p.parse_args()
    return {"login": cmd_login, "check": cmd_check, "watch": cmd_watch,
            "gui": cmd_gui}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
