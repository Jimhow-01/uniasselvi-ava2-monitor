"""Atalho de inicialização do Windows: roda o watcher sem GUI ao logar."""
import os
import subprocess
import sys

from .config import APP_DIR, ASSETS_DIR

LNK_NAME = "Uniasselvi App (notificador).lnk"
STARTUP_DIR = os.path.join(os.path.expandvars(r"%APPDATA%"), "Microsoft",
                           "Windows", "Start Menu", "Programs", "Startup")

ICON = os.path.join(ASSETS_DIR, "app.ico")


def _target():
    """(executável, argumentos) do atalho de inicialização.

    Prioridade: o .exe gerado (dist\\UniasselviApp.exe) quando existir — assim o
    Startup sempre usa o executável, não importa por onde a opção foi marcada.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, "--auto"
    exe = os.path.join(APP_DIR, "dist", "UniasselviApp", "UniasselviApp.exe")
    if not os.path.exists(exe):
        exe = os.path.join(APP_DIR, "dist", "UniasselviApp.exe")
    if os.path.exists(exe):
        return exe, "--auto"
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return pythonw, f'"{os.path.join(APP_DIR, "launcher.py")}" --auto'


def lnk_path():
    return os.path.join(STARTUP_DIR, LNK_NAME)


def is_enabled():
    return os.path.exists(lnk_path())


def enable(pythonw=None):
    lnk = lnk_path()
    os.makedirs(STARTUP_DIR, exist_ok=True)
    target, args = _target()
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{lnk}')
$sc.TargetPath = '{target}'
$sc.Arguments = '{args}'
$sc.WorkingDirectory = '{APP_DIR}'
$sc.IconLocation = '{ICON},0'
$sc.Description = 'Monitor AVA2 - notifica provas e trabalhos ao iniciar o Windows'
$sc.Save()
"""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0 and os.path.exists(lnk)


def disable():
    try:
        if os.path.exists(lnk_path()):
            os.remove(lnk_path())
        return True
    except Exception:
        return False


# ---------------- Agendador de Tarefas (checagem diária garantida) ----------------
TASK_NAME = "Uniasselvi App - checagem diaria"


def _run_ps(script):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, timeout=40,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, r.stdout.decode("utf-8", "ignore"), r.stderr.decode("utf-8", "ignore")


def daily_task_enabled():
    rc, _, _ = _run_ps(f"Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue "
                       "| Out-Null; $?")
    return rc == 0


def enable_daily_task(times=("08:45", "18:45")):
    """Cria tarefa no Agendador que roda UniasselviApp.exe --check todo dia.

    Horários deslocados 15 min dos do monitor (08:30/18:30) para não correr
    junto com ele; state.json já evita notificação duplicada. StartWhenAvailable
    roda a tarefa atrasada quando o PC voltar a ligar.
    """
    target, _args = _target()
    triggers = "\n".join(
        f"$t{ i } = New-ScheduledTaskTrigger -Daily -At '{h}'"
        for i, h in enumerate(times))
    trefs = ",".join(f"$t{i}" for i in range(len(times)))
    script = f"""
$ErrorActionPreference = 'Stop'
{triggers}
$action = New-ScheduledTaskAction -Execute '{target}' -Argument '--check' -WorkingDirectory '{APP_DIR}'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger {trefs} -Settings $settings -Description 'Checagem diaria de provas e trabalhos do AVA2' | Out-Null
'TASK_OK'
"""
    rc, out, err = _run_ps(script)
    return rc == 0 and "TASK_OK" in out


def disable_daily_task():
    rc, _, _ = _run_ps(f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' "
                       "-Confirm:$false -ErrorAction SilentlyContinue; 'DONE'")
    return rc == 0 and not daily_task_enabled()
