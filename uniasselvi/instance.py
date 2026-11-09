"""Instância única do monitor: lock por PID para não duplicar ícone na bandeja.

- O modo --auto (monitor de fundo) reclama o lock (monitor.pid).
- A GUI, ao abrir, verifica se o monitor está vivo: se sim, NÃO cria bandeja
  própria nem agenda checagens — apenas mostra a janela (o X fecha a janela).
- Se o monitor não está rodando, a GUI cria sua própria bandeja e agenda tudo.
"""
import os

from .config import APP_DIR

PID_PATH = os.path.join(APP_DIR, "monitor.pid")


def _read_pid():
    try:
        with open(PID_PATH, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        name = (psutil.Process(pid).name() or "").lower()
        return name.startswith("python")
    except Exception:
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        except Exception:
            pass
        return False


def monitor_pid():
    """PID do monitor de fundo vivo (ou None)."""
    pid = _read_pid()
    if pid and pid != os.getpid() and _pid_alive(pid):
        return pid
    return None


def is_monitor_running():
    return monitor_pid() is not None


def claim_monitor():
    """Tenta virar O monitor (atômico via O_EXCL). False se já existe um vivo."""
    for _ in range(3):
        if monitor_pid():
            return False
        try:
            fd = os.open(PID_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            # arquivo existe: lock vivo (outro ganhou a corrida) ou velho de processo morto
            if not _pid_alive(_read_pid()):
                try:
                    os.remove(PID_PATH)
                except Exception:
                    pass
            continue
        except Exception:
            return False
    return False


def release_monitor():
    try:
        if _read_pid() == os.getpid():
            os.remove(PID_PATH)
    except Exception:
        pass
