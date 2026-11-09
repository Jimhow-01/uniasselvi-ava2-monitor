"""Launcher do Uniasselvi App: tela de login bonita (CPF + senha) e painel.

Abra com:  pythonw launcher.py   (sem console)  ou  python launcher.py
"""
import os
import sys
import threading
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uniasselvi import theme as T
from uniasselvi.api import ApiError, AuthError, UniAPI
from uniasselvi.config import APP_DIR, ASSETS_DIR, has_password, load_config, load_password, save_config, save_password

ASSETS = ASSETS_DIR
LOGO_PATH = os.path.join(ASSETS, "logo.png")
ICON_PATH = os.path.join(ASSETS, "app.ico")


def _set_icon(root):
    if os.path.exists(ICON_PATH):
        try:
            root.iconbitmap(ICON_PATH)
        except Exception:
            pass


class LoginWindow:
    """Janela de entrada: logo, CPF, senha, botão Entrar."""

    W, H = 440, 600

    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.result = None
        self.busy = False

        root.title("Uniasselvi — AVA2")
        root.resizable(False, False)
        root.configure(bg=T.C["bg"])
        _set_icon(root)
        self._center()

        T.make_font(root)
        T.apply_dark_style(root)

        self._build()
        self._focus_first()

        # credenciais salvas -> tenta entrar direto, sem pedir nada
        if self.cfg.get("cpf") and has_password():
            self._auto_login()

    def _auto_login(self):
        self.status.config(text="Entrando com as credenciais salvas…", fg=T.C["muted"])
        T.set_button(self.btn, "ENTRANDO…", enabled=False)
        self.busy = True
        threading.Thread(target=self._do_login,
                         args=(self.cfg["cpf"], ""), daemon=True).start()

    def _center(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = (sw - self.W) // 2
        y = max(20, (sh - self.H) // 2 - 30)
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    # ---------------- layout ----------------
    def _build(self):
        # faixa de destaque no topo
        band = tk.Frame(self.root, bg=T.C["card"], height=150)
        band.pack(fill="x")
        band.pack_propagate(False)

        self.logo_img = None
        if os.path.exists(LOGO_PATH):
            try:
                self.logo_img = tk.PhotoImage(file=LOGO_PATH)
                tk.Label(band, image=self.logo_img, bg=T.C["card"]).pack(pady=(22, 6))
            except Exception:
                pass
        tk.Label(band, text="UNIASSELVI", bg=T.C["card"], fg=T.C["text"],
                 font=("Segoe UI", 17, "bold")).pack()
        tk.Label(band, text="AVA2 · Provas e Trabalhos Pendentes",
                 bg=T.C["card"], fg=T.C["muted"], font=("Segoe UI", 9)).pack(pady=(0, 18))

        body = tk.Frame(self.root, bg=T.C["bg"])
        body.pack(fill="both", expand=True, padx=34, pady=(22, 10))

        # CPF
        tk.Label(body, text="CPF ou e-mail de aluno", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.user = T.PlaceholderEntry(body, placeholder="000.000.000-00", width=30,
                                       font=("Segoe UI", 12))
        self.user.pack(fill="x", ipady=7, pady=(4, 14))
        self.user.set_value(self.cfg.get("cpf", ""))

        # Senha + olho
        row = tk.Frame(body, bg=T.C["bg"])
        row.pack(fill="x")
        tk.Label(body, text="Senha", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ph = "sua senha do AVA2" + ("  (em branco = senha salva)" if has_password() else "")
        self.pw = T.PlaceholderEntry(row, placeholder=ph, width=26, show="●",
                                     font=("Segoe UI", 12))
        self.pw.pack(side="left", fill="x", expand=True, ipady=7, pady=(4, 0))
        self.eye = tk.Label(row, text="mostrar", bg=T.C["bg"], fg=T.C["accent"],
                            font=("Segoe UI", 9, "underline"), cursor="hand2")
        self.eye.pack(side="left", padx=(8, 0))
        self.eye.bind("<Button-1>", self._toggle_eye)
        self._revealed = False

        # lembrar CPF
        self.remember = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(body, text="Lembrar meu CPF neste computador",
                             variable=self.remember, bg=T.C["bg"], fg=T.C["muted"],
                             activebackground=T.C["bg"], activeforeground=T.C["text"],
                             selectcolor=T.C["input_bg"], highlightthickness=0,
                             font=("Segoe UI", 9))
        chk.pack(anchor="w", pady=(12, 0))

        # status / erro
        self.status = tk.Label(body, text="", bg=T.C["bg"], fg=T.C["err"],
                               font=("Segoe UI", 9), wraplength=360, justify="left")
        self.status.pack(anchor="w", pady=(10, 0))

        # botão principal
        self.btn = T.flat_button(body, "ENTRAR", self.submit, kind="primary")
        self.btn.pack(pady=(16, 8))

        # rodapé
        foot = tk.Frame(self.root, bg=T.C["bg"])
        foot.pack(fill="x", padx=34, pady=(0, 16))
        T.link_label(foot, "Esqueci minha senha", self._open_recovery).pack(side="left")
        T.link_label(foot, "Abrir o AVA2 no navegador", lambda: self._url("https://ava2.uniasselvi.com.br")).pack(side="right")

        self.root.bind("<Return>", lambda e: self.submit())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _focus_first(self):
        if not self.user.get():
            self.user.focus_set()
        else:
            self.pw.focus_set()

    def _toggle_eye(self, _event=None):
        self._revealed = not self._revealed
        self.pw.config(show="" if self._revealed else "●")
        self.eye.config(text="ocultar" if self._revealed else "mostrar")

    def _url(self, u):
        import webbrowser
        webbrowser.open(u)

    def _open_recovery(self):
        self._url("https://areasegura.uniasselvi.com.br/recuperar_senha")

    # ---------------- submit ----------------
    def submit(self):
        if self.busy:
            return
        cpf = self.user.value().strip()
        pw = self.pw.value()
        if not cpf:
            self._error("Informe seu CPF ou e-mail de aluno.")
            self.user.focus_set()
            return
        if not pw and not has_password():
            self._error("Informe sua senha do AVA2.")
            self.pw.focus_set()
            return

        self.busy = True
        self.status.config(text="", fg=T.C["muted"])
        T.set_button(self.btn, "ENTRANDO…", enabled=False)
        threading.Thread(target=self._do_login, args=(cpf, pw), daemon=True).start()

    def _do_login(self, cpf, pw):
        password = pw or load_password()
        api = UniAPI()
        err = None
        try:
            api.login(cpf, password)
            specs = api.get_specializations("ALUN")
            lst = specs if isinstance(specs, list) else []
            self.cfg["cpf"] = cpf if self.remember.get() else ""
            if lst and not self.cfg.get("specialization"):
                first = lst[0]
                self.cfg["specialization"] = str(first.get("specialization")
                                                 or first.get("code")
                                                 or first.get("espe_codi") or "")
            save_config(self.cfg)
            save_password(password)
            self.result = (password, lst)
        except AuthError as e:
            err = f"Login recusado: {e}"
        except ApiError as e:
            err = f"Erro na API: {e}"
        except Exception as e:
            err = f"Erro inesperado: {e}"
        self.root.after(0, self._finish, err)

    def _finish(self, err):
        self.busy = False
        if err:
            self._error(err)
            T.set_button(self.btn, "ENTRAR", enabled=True)
            self.pw.focus_set()
            return
        password, specs = self.result
        T.set_button(self.btn, "ABRIR PAINEL…", enabled=False)
        self.root.after(0, lambda: self._open_panel(password, specs))

    def _error(self, msg):
        self.status.config(text=msg, fg=T.C["err"])

    def _open_panel(self, password, specs):
        from uniasselvi.gui import App
        self.root.title("Uniasselvi — Painel")
        self.root.resizable(True, True)
        self.root.geometry("820x560")
        for w in self.root.winfo_children():
            w.destroy()
        App(self.root, specs=specs)


def _auto_mode():
    """Modo sem interface: roda o agendador em segundo plano (usado pelo início do Windows)."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(APP_DIR, "app.log"), encoding="utf-8")],
    )
    from uniasselvi import instance
    from uniasselvi.watcher import run_check, watch_loop
    cfg = load_config()
    if not cfg.get("cpf") or not has_password():
        logging.getLogger("uniasselvi").info("auto: sem credenciais salvas, nada a monitorar")
        return 0

    # instância única: se já existe um monitor vivo (outro --auto ou painel), sai sem duplicar
    if not instance.claim_monitor():
        logging.getLogger("uniasselvi").info(
            "auto: monitor já ativo (PID %s) — esta instância vai sair", instance.monitor_pid())
        return 0

    # ícone na bandeja para mostrar que o monitor está rodando
    tray = None
    try:
        import pystray
        from PIL import Image
        icon_path = os.path.join(ASSETS, "app.ico")
        img = Image.open(icon_path) if os.path.exists(icon_path) else Image.new("RGB", (64, 64), "#2563EB")

        def check(icon=None, item=None):
            threading.Thread(target=lambda: run_check(cfg, force=True), daemon=True).start()

        def open_ava(icon=None, item=None):
            import webbrowser
            webbrowser.open("https://ava2.uniasselvi.com.br")

        def quit_auto(icon=None, item=None):
            # encerra o monitor de verdade: libera o lock e mata o processo
            try:
                instance.release_monitor()
            except Exception:
                pass
            try:
                if icon is not None:
                    icon.stop()
            except Exception:
                pass
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Verificar agora", check, default=True),
            pystray.MenuItem("Abrir AVA2 no navegador", open_ava),
            pystray.MenuItem("Abrir painel", lambda i=None, it=None: _open_panel_from_auto()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", quit_auto),
        )
        tray = pystray.Icon("uniasselvi_auto", img,
                            "Uniasselvi — monitorando provas e trabalhos", menu)
        tray.run_detached()
    except Exception as e:
        logging.getLogger("uniasselvi").warning("auto: bandeja indisponível: %s", e)

    # checagem imediata ao ligar o PC (não silenciosa: se algo vence em <=N dias, notifica)
    try:
        tasks, alerts, info = run_check(cfg, force=True)
        logging.getLogger("uniasselvi").info(
            "auto: checagem de inicialização — %d pendências, %d alertas", len(tasks), len(alerts))
    except Exception as e:
        logging.getLogger("uniasselvi").error("auto: checagem inicial falhou: %s", e)
    try:
        watch_loop(cfg)
    except KeyboardInterrupt:
        pass
    finally:
        if tray is not None:
            try:
                tray.stop()
            except Exception:
                pass
    return 0


def _open_panel_from_auto():
    """Abre o painel GUI a partir do modo auto (tray)."""
    import subprocess
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable])
    else:
        subprocess.Popen([sys.executable, os.path.join(APP_DIR, "launcher.py")])


def _selftest():
    """Verifica imports críticos e dispara um toast de teste (para o .exe)."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(APP_DIR, "selftest.log"), encoding="utf-8")],
    )
    log = logging.getLogger("selftest")
    results = []
    for mod in ("requests", "pystray", "PIL", "win11toast", "win32crypt"):
        try:
            __import__(mod)
            results.append(f"import {mod}: ok")
        except Exception as e:
            results.append(f"import {mod}: FALHOU ({e})")
    from uniasselvi.notifier import _toast_win11
    ok = _toast_win11("Uniasselvi selftest", "Imports e notificação funcionando no executável.")
    results.append(f"toast nativo: {'ok' if ok else 'FALHOU'}")
    from uniasselvi import instance
    results.append(f"instance lock: {'ok' if instance.claim_monitor() else 'monitor já ativo'}")
    instance.release_monitor()
    for line in results:
        log.info(line)
    return 0


def _check_mode():
    """Checagem única (usada pelo Agendador de Tarefas do Windows): roda, notifica e sai."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(APP_DIR, "app.log"), encoding="utf-8")],
    )
    log = logging.getLogger("uniasselvi")
    from uniasselvi.watcher import run_check
    cfg = load_config()
    if not cfg.get("cpf") or not has_password():
        log.info("task: sem credenciais salvas, nada a verificar")
        return 0
    try:
        tasks, alerts, info = run_check(cfg, force=True)
        log.info("task: checagem agendada — %d pendências, %d alertas novos",
                 len(tasks), len(alerts))
        return 0
    except Exception as e:
        log.error("task: checagem agendada falhou: %s", e)
        return 1


def main():
    if "--auto" in sys.argv:
        return _auto_mode()
    if "--check" in sys.argv:
        return _check_mode()
    if "--selftest" in sys.argv:
        return _selftest()
    root = tk.Tk()
    LoginWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
