"""Notificações no Windows: toast nativo (win11toast) -> PowerShell WinRT -> popup tkinter."""
import logging
import os
import subprocess

log = logging.getLogger("uniasselvi.notify")

from .config import ASSETS_DIR

ICON_PATH = os.path.join(ASSETS_DIR, "app.ico")


def _toast_win11(title: str, body: str) -> bool:
    """Notificação padrão do Windows 11 (aparece no Centro de Notificações)."""
    try:
        from win11toast import toast
        toast(app_id="Uniasselvi App", title=title, body=body,
              icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
              duration="long")
        return True
    except Exception as e:
        log.warning("win11toast falhou: %s", e)
        return False

_TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$title = $template.GetElementsByTagName('text').Item(0)
$title.AppendChild($template.CreateTextNode(%TITLE%)) | Out-Null
$body = $template.GetElementsByTagName('text').Item(1)
$body.AppendChild($template.CreateTextNode(%BODY%)) | Out-Null
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Uniasselvi App')
$notifier.Show($template)
"""


def _ps_quote(s: str) -> str:
    """Aspas simples PowerShell (escape duplicando ')."""
    return "'" + str(s).replace("'", "''") + "'"


def send_toast(title: str, body: str) -> bool:
    ps = (_TOAST_PS
          .replace("%TITLE%", _ps_quote(title))
          .replace("%BODY%", _ps_quote(body)))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0:
            return True
        log.warning("toast falhou (rc=%s): %s", r.returncode, r.stderr.decode("utf-8", "ignore")[:300])
    except Exception as e:
        log.warning("toast exceção: %s", e)
    return False


def send_popup(title: str, body: str) -> bool:
    """Fallback: janelinha tkinter que some sozinha."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title(title[:60])
        root.attributes("-topmost", True)
        try:
            root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        w, h = 420, 150
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{sw - w - 20}+{sh - h - 60}")
        tk.Label(root, text=title, font=("Segoe UI", 12, "bold"), wraplength=400,
                 justify="left").pack(padx=12, pady=(12, 4), anchor="w")
        tk.Label(root, text=body, font=("Segoe UI", 10), wraplength=400,
                 justify="left").pack(padx=12, anchor="w")
        root.after(20000, root.destroy)
        root.mainloop()
        return True
    except Exception as e:
        log.warning("popup fallback falhou: %s", e)
        return False


def notify(title: str, body: str):
    """Toast nativo do Windows (win11toast); fallback PowerShell WinRT; fallback popup."""
    log.info("NOTIFICAR: %s | %s", title, body.replace("\n", " / "))
    if _toast_win11(title, body):
        return
    if not send_toast(title, body):
        send_popup(title, body)
