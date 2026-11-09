"""Painel tkinter (tema escuro): lista pendências, dispara checagens e mostra próxima verificação."""
import logging
import os
import threading
import tkinter as tk
from datetime import date
from tkinter import ttk

from . import autostart, instance
from . import theme as T

# NOTE: save_password faltava no import original; a linha que salva senha nova
# chamava um nome que nunca foi importado -> NameError em runtime.
from .config import ASSETS_DIR, has_password, load_config, load_password, save_config, save_password
from .watcher import next_run_times, run_check, watch_loop

log = logging.getLogger("uniasselvi.gui")

ICON_PATH = os.path.join(ASSETS_DIR, "app.ico")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

KIND_LABEL = {"prova": "Prova", "trabalho": "Trabalho", "avaliação": "Avaliação",
              "atividade": "Atividade", "producao": "Produção"}


class App:
    def __init__(self, root, specs=None):
        self.root = root
        self.cfg = load_config()
        self.stop = threading.Event()
        self.busy = False
        self.specs = specs or []

        if os.path.exists(ICON_PATH):
            try:
                root.iconbitmap(ICON_PATH)
            except Exception:
                pass
        root.configure(bg=T.C["bg"])
        T.make_font(root)
        T.apply_dark_style(root)
        root.minsize(640, 420)

        self._build()
        self._refresh_status()
        # instância única: se o monitor de fundo (--auto) já está vivo, este painel
        # NÃO cria bandeja nem agenda checagens — evita ícone duplicado na bandeja.
        self.monitor_bg = instance.monitor_pid()
        self.is_monitor = False if self.monitor_bg else instance.claim_monitor()
        if self.is_monitor:
            self._schedule_auto()
            self._make_tray()
        else:
            self.tray = None
            log.info("monitor de fundo ativo (PID %s) — painel sem bandeja própria",
                     self.monitor_bg)
        if has_password() and self.cfg.get("cpf"):
            self.check_now(quiet=True)

    # ---------------- layout ----------------
    def _build(self):
        top = tk.Frame(self.root, bg=T.C["card"])
        top.pack(fill="x")
        inner = tk.Frame(top, bg=T.C["card"])
        inner.pack(fill="x", padx=14, pady=10)

        if os.path.exists(LOGO_PATH):
            try:
                self.logo = tk.PhotoImage(file=LOGO_PATH)
                self.logo = self.logo.subsample(3, 3)
                tk.Label(inner, image=self.logo, bg=T.C["card"]).pack(side="left", padx=(0, 10))
            except Exception:
                pass
        titles = tk.Frame(inner, bg=T.C["card"])
        titles.pack(side="left")
        self.status_lbl = tk.Label(titles, text="Carregando…", bg=T.C["card"],
                                   fg=T.C["text"], font=("Segoe UI", 11, "bold"))
        self.status_lbl.pack(anchor="w")
        self.next_lbl = tk.Label(titles, text="", bg=T.C["card"], fg=T.C["muted"],
                                 font=("Segoe UI", 9))
        self.next_lbl.pack(anchor="w")

        bar = tk.Frame(self.root, bg=T.C["bg"])
        bar.pack(fill="x", padx=14, pady=(12, 4))
        self.btn_check = T.flat_button(bar, "Verificar agora", lambda: self.check_now())
        self.btn_check.pack(side="left")
        T.flat_button(bar, "Testar notificação", self.test_notify, kind="plain").pack(side="left", padx=8)
        self.btn_sms = T.flat_button(bar, "SMS", self.open_sms, kind="plain")
        self.btn_sms.pack(side="left", padx=8)
        T.flat_button(bar, "Trocar login", self.open_login, kind="danger").pack(side="left", padx=8)

        tk.Label(bar, text="alertar a", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(16, 6))
        self.days_var = tk.StringVar(value=str(self.cfg.get("alert_days", 3)))
        ttk.Spinbox(bar, from_=1, to=15, width=4, textvariable=self.days_var,
                    command=self._save_days).pack(side="left")
        tk.Label(bar, text="dias", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        tk.Label(bar, text="mostrar", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 6))
        self.view_var = tk.StringVar(value=str(self.cfg.get("view_days", 5)))
        ttk.Spinbox(bar, from_=1, to=30, width=4, textvariable=self.view_var,
                    command=self._save_view_days).pack(side="left")
        tk.Label(bar, text="dias", bg=T.C["bg"], fg=T.C["muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        self.auto_var = tk.BooleanVar(value=autostart.is_enabled())
        chk = tk.Checkbutton(bar, text="iniciar com o Windows", variable=self.auto_var,
                             command=self._toggle_autostart, bg=T.C["bg"], fg=T.C["muted"],
                             activebackground=T.C["bg"], activeforeground=T.C["text"],
                             selectcolor=T.C["input_bg"], highlightthickness=0,
                             font=("Segoe UI", 9))
        chk.pack(side="left", padx=(12, 0))

        self.task_var = tk.BooleanVar(value=autostart.daily_task_enabled())
        chk2 = tk.Checkbutton(bar, text="checagem diária garantida", variable=self.task_var,
                              command=self._toggle_daily_task, bg=T.C["bg"], fg=T.C["muted"],
                              activebackground=T.C["bg"], activeforeground=T.C["text"],
                              selectcolor=T.C["input_bg"], highlightthickness=0,
                              font=("Segoe UI", 9))
        chk2.pack(side="left", padx=(8, 0))

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=14, pady=8)
        self.frame_up, self.tree_up = self._tree()
        self.frame_all, self.tree_all = self._tree()
        self.frame_over, self.tree_over = self._tree()
        self.nb.add(self.frame_up, text=f"Pendentes ({self.cfg.get('view_days', 5)} dias)")
        self.nb.add(self.frame_all, text="Todas")
        self.nb.add(self.frame_over, text="Atrasados")

        bottom = tk.Frame(self.root, bg=T.C["bg"])
        bottom.pack(fill="x", padx=14, pady=(0, 10))
        self.log_txt = tk.Text(bottom, height=4, font=("Consolas", 9), state="disabled",
                               bg=T.C["card"], fg=T.C["muted"], relief="flat",
                               highlightthickness=1, highlightbackground=T.C["border"])
        self.log_txt.pack(fill="x")
        self._log_handler = GuiLogHandler(self.log_txt)
        logging.getLogger("uniasselvi").addHandler(self._log_handler)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _tree(self):
        f = tk.Frame(self.nb, bg=T.C["bg"])
        cols = ("kind", "title", "subject", "label", "deadline", "days", "periods")
        tree = ttk.Treeview(f, columns=cols, show="headings")
        for c, w, head in (("kind", 80, "Tipo"), ("title", 220, "Título"),
                           ("subject", 150, "Disciplina"), ("label", 120, "Prazo"),
                           ("deadline", 85, "Data"), ("days", 55, "Dias"),
                           ("periods", 260, "Períodos")):
            tree.heading(c, text=head)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True)
        tree.bind("<Double-1>", lambda e: self.open_ava())
        return f, tree

    # ---------------- ações ----------------
    def check_now(self, quiet=False):
        if self.busy:
            return
        self.busy = True
        self.status_lbl.config(text="Verificando AVA2…")
        T.set_button(self.btn_check, "VERIFICANDO…", enabled=False)

        def work():
            try:
                tasks, alerts, info = run_check(self.cfg, force=not quiet)
                self._safe_after(self._show_results, tasks, alerts, info)
            except Exception as e:
                log.error("checagem falhou: %s", e)
                self._safe_after(self._show_error, e)
            finally:
                self.busy = False
                self._safe_after(lambda: T.set_button(self.btn_check, "Verificar agora", enabled=True))

        threading.Thread(target=work, daemon=True).start()

    def _safe_after(self, func, *args):
        """root.after seguro: ignora se a janela já foi destruída durante a tarefa."""
        try:
            if self.root.winfo_exists():
                self.root.after(0, func, *args)
        except Exception:
            pass

    def _show_results(self, tasks, alerts, info):
        self.info = info
        self._refresh_status(info)
        for t in (self.tree_up, self.tree_all, self.tree_over):
            t.delete(*t.get_children())
        today = date.today()
        view_days = int(self.cfg.get("view_days", 5))
        for t in sorted(tasks, key=lambda x: (x.deadline or date.max)):
            d = t.days_left(today)
            row = (KIND_LABEL.get(t.kind, t.kind), t.title[:70], t.subject[:50],
                   t.deadline_label, t.deadline.strftime("%d/%m/%Y") if t.deadline else "-",
                   f"{d:+d}" if d is not None else "-",
                   t.periods_text()[:120])
            self.tree_all.insert("", "end", values=row)
            if d is not None and 0 <= d <= view_days:
                self.tree_up.insert("", "end", values=row)
            if d is not None and d < 0:
                self.tree_over.insert("", "end", values=row)
        self.status_lbl.config(
            text=f"{info.get('name','')} — {info.get('course','')} | "
                 f"{len(tasks)} pendências | {len(alerts)} alerta(s) novo(s)")

    def _show_error(self, e):
        msg = str(e)
        if "senha" in msg.lower() or "autoriz" in msg.lower() or "login" in msg.lower():
            self.status_lbl.config(text="Login recusado pelo AVA2 — use 'Trocar login'.")
        else:
            self.status_lbl.config(text=f"Erro: {msg[:120]}")

    def _refresh_status(self, info=None):
        runs = next_run_times(self.cfg)
        nxt = runs[0].strftime("%d/%m %H:%M") if runs else "-"
        cred = "ok" if (has_password() and self.cfg.get("cpf")) else "faltam credenciais"
        self.next_lbl.config(text=f"Checagens automáticas: {', '.join(self.cfg.get('check_times', []))} "
                                 f"| próxima: {nxt} | credenciais: {cred}")

    def _schedule_auto(self):
        threading.Thread(target=watch_loop, args=(self.cfg,),
                         kwargs={"stop_event": self.stop}, daemon=True).start()

    def open_login(self):
        LoginDialog(self.root, self.cfg, on_saved=self._after_login)

    def open_sms(self):
        SmsDialog(self.root, self.cfg)

    def _after_login(self):
        self.cfg = load_config()
        self._refresh_status()
        self.check_now(quiet=True)

    def _save_days(self):
        try:
            self.cfg["alert_days"] = int(self.days_var.get())
            save_config(self.cfg)
            self.check_now(quiet=True)
        except ValueError:
            pass

    def _save_view_days(self):
        try:
            self.cfg["view_days"] = int(self.view_var.get())
            save_config(self.cfg)
            self.nb.tab(self.frame_up,
                        text=f"Pendentes ({self.cfg['view_days']} dias)")
            self.check_now(quiet=True)
        except ValueError:
            pass

    def _toggle_autostart(self):
        want = self.auto_var.get()
        try:
            if want:
                ok = autostart.enable()
            else:
                ok = autostart.disable()
        except Exception as e:
            log.error("autostart: %s", e)
            ok = False
        if not ok:
            self.auto_var.set(not want)
            self.status_lbl.config(text="Não consegui configurar a inicialização automática.")
        else:
            log.info("autostart %s", "ativado" if want else "desativado")

    def _toggle_daily_task(self):
        want = self.task_var.get()
        try:
            if want:
                ok = autostart.enable_daily_task()
            else:
                ok = autostart.disable_daily_task()
        except Exception as e:
            log.error("tarefa diária: %s", e)
            ok = False
        if not ok:
            self.task_var.set(not want)
            self.status_lbl.config(text="Não consegui configurar a tarefa diária "
                                        "(tente abrir o app como administrador).")
        else:
            log.info("tarefa diária %s", "ativada" if want else "desativada")

    def test_notify(self):
        # toast nativo pode bloquear até ser dispensado: rodar fora da main thread
        from .notifier import notify
        threading.Thread(target=notify, daemon=True, kwargs={
            "title": "Uniasselvi: teste de notificação",
            "body": "Se você viu isso, as notificações estão funcionando.\n"
                    "Acesse o AVA2: https://ava2.uniasselvi.com.br",
        }).start()

    def open_ava(self):
        import webbrowser
        webbrowser.open("https://ava2.uniasselvi.com.br")

    def on_close(self):
        """X minimiza para a bandeja; sair de verdade só pelo menu da bandeja."""
        if self.tray is not None:
            self.root.withdraw()
            self.status_lbl.config(text="App minimizado na bandeja (ícone Uniasselvi). "
                                        "Clique no ícone para reabrir.")
            log.info("janela minimizada para a bandeja")
        else:
            self.quit_for_real()

    def quit_for_real(self):
        self.stop.set()
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            pass
        if getattr(self, "is_monitor", False):
            instance.release_monitor()
        logging.getLogger("uniasselvi").removeHandler(self._log_handler)
        self.root.destroy()

    # ---------------- bandeja ----------------
    def _make_tray(self):
        self.tray = None
        try:
            import pystray
            from PIL import Image
        except Exception as e:
            log.warning("pystray indisponível (%s) — X fechará normalmente", e)
            return
        try:
            img = Image.open(ICON_PATH) if os.path.exists(ICON_PATH) else Image.new("RGB", (64, 64), "#2563EB")
        except Exception:
            img = Image.new("RGB", (64, 64), "#2563EB")

        def show(icon=None, item=None):
            self.root.after(0, self._tray_show)

        def check(icon=None, item=None):
            self.root.after(0, self.check_now)

        def quit(icon=None, item=None):
            self.root.after(0, self.quit_for_real)

        def open_ava(icon=None, item=None):
            self.root.after(0, self.open_ava)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir painel", show, default=True),
            pystray.MenuItem("Verificar agora", check),
            pystray.MenuItem("Abrir AVA2 no navegador", open_ava),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", quit),
        )
        self.tray = pystray.Icon("uniasselvi", img,
                                 "Uniasselvi — Provas e Trabalhos (rodando em segundo plano)",
                                 menu)
        self.tray.run_detached()
        log.info("ícone na bandeja criado")

    def _tray_show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(400, lambda: self.root.attributes("-topmost", False))
        try:
            self.root.focus_set()
        except Exception:
            pass


class GuiLogHandler(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        try:
            line = self.format(record) + "\n"
            self.widget.after(0, self._append, line)
        except Exception:
            pass

    def _append(self, line):
        self.widget.config(state="normal")
        self.widget.insert("end", line)
        lines = int(self.widget.index("end-1c").split(".")[0])
        if lines > 200:
            self.widget.delete("1.0", f"{lines-200}.0")
        self.widget.see("end")
        self.widget.config(state="disabled")


class LoginDialog:
    def __init__(self, parent, cfg, on_saved):
        self.cfg = cfg
        self.on_saved = on_saved
        self.d = tk.Toplevel(parent)
        self.d.title("Credenciais AVA2")
        self.d.transient(parent)
        self.d.resizable(False, False)
        self.d.configure(bg=T.C["bg"])
        self.d.geometry("440x380")
        if os.path.exists(ICON_PATH):
            try:
                self.d.iconbitmap(ICON_PATH)
            except Exception:
                pass
        pad = {"padx": 20, "pady": (6, 2)}

        def label(text):
            tk.Label(self.d, text=text, bg=T.C["bg"], fg=T.C["muted"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", **pad)

        label("CPF ou e-mail de aluno")
        self.user = T.PlaceholderEntry(self.d, placeholder="000.000.000-00", width=34)
        self.user.set_value(cfg.get("cpf", ""))
        self.user.pack(anchor="w", padx=20, ipady=5)

        label("Senha (em branco = manter a salva)")
        self.pw = T.PlaceholderEntry(self.d, placeholder="nova senha", width=34, show="●")
        self.pw.pack(anchor="w", padx=20, ipady=5)

        label("Horários de checagem (HH:MM, separados por vírgula)")
        self.times = T.PlaceholderEntry(self.d, placeholder="08:30,18:30", width=34)
        self.times.set_value(",".join(cfg.get("check_times", [])))
        self.times.pack(anchor="w", padx=20, ipady=5)

        label("Código da especialização (vazio = primeiro curso)")
        self.spec = T.PlaceholderEntry(self.d, placeholder="automático", width=34)
        self.spec.set_value(cfg.get("specialization", ""))
        self.spec.pack(anchor="w", padx=20, ipady=5)

        self.msg = tk.Label(self.d, text="", bg=T.C["bg"], fg=T.C["err"],
                            font=("Segoe UI", 9), wraplength=400, justify="left")
        self.msg.pack(anchor="w", padx=20, pady=(8, 0))

        row = tk.Frame(self.d, bg=T.C["bg"])
        row.pack(pady=14)
        self.btn = T.flat_button(row, "SALVAR E TESTAR", self.save)
        self.btn.pack(side="left")
        T.flat_button(row, "Cancelar", self.d.destroy, kind="plain").pack(side="left", padx=8)
        self.d.bind("<Return>", lambda e: self.save())

    def save(self):
        from uniasselvi.api import AuthError, UniAPI
        cpf = self.user.value().strip()
        pw = self.pw.value()
        if not cpf:
            self.msg.config(text="Preencha o CPF.")
            return
        if not pw and not has_password():
            self.msg.config(text="Preencha a senha.")
            return
        self.cfg["cpf"] = cpf
        times = [t.strip() for t in self.times.value().split(",") if t.strip()]
        if times:
            self.cfg["check_times"] = times
        self.cfg["specialization"] = self.spec.value().strip()
        save_config(self.cfg)
        if pw:
            save_password(pw)
        T.set_button(self.btn, "TESTANDO…", enabled=False)

        def work():
            api = UniAPI()
            try:
                api.login(cpf, pw or load_password())
                specs = api.get_specializations("ALUN")
                lst = specs if isinstance(specs, list) else []
                if not self.cfg["specialization"] and lst:
                    first = lst[0]
                    self.cfg["specialization"] = str(first.get("specialization")
                                                     or first.get("code")
                                                     or first.get("espe_codi") or "")
                    save_config(self.cfg)
                self.d.after(0, lambda: (self.d.destroy(), self.on_saved()))
            except AuthError as e:
                # NOTE: o lambda era chamado DEPOIS do bloco except, e o Python
                # apaga a variavel 'e' ao sair do except -> NameError no callback
                # do Tkinter em vez de mostrar o erro na janela. Captura antecipada
                # via argumento default.
                self.d.after(0, lambda err=e: self._fail(f"Login recusado: {err}"))
            except Exception as e:
                self.d.after(0, lambda err=e: self._fail(f"Erro: {err}"))

        threading.Thread(target=work, daemon=True).start()

    def _fail(self, msg):
        self.msg.config(text=msg)
        T.set_button(self.btn, "SALVAR E TESTAR", enabled=True)


class SmsDialog:
    """Configura notificação por SMS (Zenvia ou Twilio) e dispara um teste."""

    def __init__(self, parent, cfg):
        self.cfg = cfg
        from uniasselvi import sms as smsmod
        self.smsmod = smsmod
        creds = smsmod.load_sms_credentials() or {}

        self.d = tk.Toplevel(parent)
        self.d.title("Notificação por SMS")
        self.d.transient(parent)
        self.d.resizable(False, False)
        self.d.configure(bg=T.C["bg"])
        self.d.geometry("470x520")
        pad = {"padx": 20, "pady": (6, 2)}

        def label(text):
            lbl = tk.Label(self.d, text=text, bg=T.C["bg"], fg=T.C["muted"],
                           font=("Segoe UI", 9, "bold"))
            lbl.pack(anchor="w", **pad)
            return lbl
        self.provider = tk.StringVar(value=creds.get("provider", "zenvia"))
        rowp = tk.Frame(self.d, bg=T.C["bg"])
        rowp.pack(anchor="w", padx=20)
        for val, txt in (("zenvia", "Zenvia (brasileira)"), ("twilio", "Twilio")):
            tk.Radiobutton(rowp, text=txt, value=val, variable=self.provider,
                           command=self._on_provider, bg=T.C["bg"], fg=T.C["text"],
                           selectcolor=T.C["input_bg"], activebackground=T.C["bg"],
                           activeforeground=T.C["text"], highlightthickness=0,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))

        # telefone
        label("Seu celular (com +55)")
        self.to = T.PlaceholderEntry(self.d, placeholder="+5551999999999", width=40)
        self.to.set_value(cfg.get("sms_to", ""))
        self.to.pack(anchor="w", padx=20, ipady=5)

        # token
        self.token_lbl = label("Token da API")
        self.token = T.PlaceholderEntry(self.d, placeholder="", width=40, show="●")
        self.token.pack(anchor="w", padx=20, ipady=5)

        # sender
        self.sender_lbl = label("Remetente")
        self.sender = T.PlaceholderEntry(self.d, placeholder="", width=40)
        self.sender.pack(anchor="w", padx=20, ipady=5)

        # sid (twilio)
        self.sid_lbl = label("Account SID (Twilio)")
        self.sid = T.PlaceholderEntry(self.d, placeholder="", width=40)
        self.sid.pack(anchor="w", padx=20, ipady=5)

        # ativar
        self.enabled = tk.BooleanVar(value=bool(cfg.get("sms_enabled")))
        tk.Checkbutton(self.d, text="Enviar SMS de alerta (além do toast do Windows)",
                       variable=self.enabled, bg=T.C["bg"], fg=T.C["text"],
                       activebackground=T.C["bg"], activeforeground=T.C["text"],
                       selectcolor=T.C["input_bg"], highlightthickness=0,
                       font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(8, 0))

        self.hint = tk.Label(self.d, text="", bg=T.C["bg"], fg=T.C["muted"],
                             font=("Segoe UI", 8), wraplength=430, justify="left")
        self.hint.pack(anchor="w", padx=20, pady=(6, 0))

        self.msg = tk.Label(self.d, text="", bg=T.C["bg"], fg=T.C["err"],
                            font=("Segoe UI", 9), wraplength=430, justify="left")
        self.msg.pack(anchor="w", padx=20, pady=(6, 0))

        row = tk.Frame(self.d, bg=T.C["bg"])
        row.pack(pady=12)
        self.btn = T.flat_button(row, "SALVAR E TESTAR SMS", self.save)
        self.btn.pack(side="left")
        T.flat_button(row, "Cancelar", self.d.destroy, kind="plain").pack(side="left", padx=8)

        if creds.get("token"):
            self._saved_token = creds["token"]
            self._saved_provider = creds.get("provider", "zenvia")
            self.token.placeholder = "token salvo — deixe em branco para manter"
            self.token._show_ph()
        else:
            self._saved_token = None
            self._saved_provider = None
        self.sender.set_value(creds.get("sender", ""))
        self.sid.set_value(creds.get("account_sid", ""))
        self._on_provider()

    def _on_provider(self):
        tw = self.provider.get() == "twilio"
        saved = " (deixe em branco para manter o salvo)" if self._saved_token else ""
        self.token_lbl.config(text="AuthToken da Twilio" if tw else "Token da API Zenvia")
        self.token.set_placeholder(("AuthToken da Twilio" if tw else "token do app.zenvia.com") + saved)
        self.sender_lbl.config(text="Número remetente alugado na Twilio" if tw else "Nome/número remetente (opcional)")
        self.sender.set_placeholder("+1..." if tw else "Zenvia")
        self.sid_lbl.pack_forget() if not tw else None
        if tw:
            self.sid_lbl.pack(anchor="w", padx=20, pady=(6, 2))
            self.sid.pack(anchor="w", padx=20, ipady=5)
        else:
            self.sid_lbl.pack_forget()
            self.sid.pack_forget()
        self.hint.config(text=(
            "Twilio: ~US$ 0,06/SMS para o Brasil + número remetente alugado (~US$1,15/mês). "
            "Crie conta grátis em twilio.com/console e copie Account SID + AuthToken."
            if tw else
            "Zenvia: pacote de ~R$ 100 por 1.000 SMS (~R$ 0,10 cada). Crie conta em zenvia.com, "
            "gere o token em app.zenvia.com/home/api e informe aqui. O remetente é seu número "
            "aprovado na Zenvia (ou nome remetente configurado no painel deles)."
        ))

    def save(self):
        to = self.to.value().strip()
        token = self.token.value().strip()
        if not to:
            self.msg.config(text="Informe seu celular (com +55).")
            return
        provider = self.provider.get()
        if not token:
            if self._saved_token and self._saved_provider == provider:
                token = self._saved_token
            else:
                self.msg.config(text="Informe o token deste provedor.")
                return
        sender = self.sender.value().strip()
        sid = self.sid.value().strip()
        if provider == "twilio" and not sid:
            self.msg.config(text="Twilio exige o Account SID.")
            return
        if provider == "twilio" and not sender:
            self.msg.config(text="Twilio exige o número remetente alugado.")
            return

        self.cfg["sms_to"] = to
        self.cfg["sms_enabled"] = bool(self.enabled.get())
        save_config(self.cfg)
        self.smsmod.save_sms_credentials(provider, token, sid, sender)
        T.set_button(self.btn, "ENVIANDO TESTE…", enabled=False)

        def work():
            ok, msg = self.smsmod.send_sms(self.cfg,
                                           "Uniasselvi App: teste de SMS de alerta de provas.")
            self.d.after(0, lambda: self._result(ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def _result(self, ok, msg):
        if ok:
            self.msg.config(text=f"{msg} — confira seu celular.", fg=T.C["ok"])
        else:
            self.msg.config(text=f"SMS falhou: {msg}", fg=T.C["err"])
        T.set_button(self.btn, "SALVAR E TESTAR SMS", enabled=True)


def run_gui():
    root = tk.Tk()
    root.title("Uniasselvi — Provas e Trabalhos")
    root.geometry("820x560")
    App(root)
    root.mainloop()
    return 0
