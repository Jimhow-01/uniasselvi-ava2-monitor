"""Coleta pendências do AVA2 e dispara alertas (<= N dias) sem duplicar."""
import json
import logging
import os
import time
from datetime import date, datetime, timedelta

from .api import ApiError, AuthError, UniAPI
from .config import STATE_PATH, load_password
from .models import parse_complementary, parse_pending_tests, parse_productions

log = logging.getLogger("uniasselvi.watcher")


# ---------------- state ----------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sent": {}, "last_check": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _prune_sent(sent):
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    return {k: v for k, v in sent.items() if v >= cutoff}


# ---------------- coleta ----------------
def collect(api: UniAPI, cfg: dict):
    """Login + pendências. Retorna (tasks, info)."""
    cpf = cfg["cpf"]
    password = load_password()
    if not password:
        raise AuthError("Senha não salva — rode `python app.py login` primeiro.")

    api.login(cpf, password)
    specs = api.get_specializations("ALUN")
    spec_list = specs if isinstance(specs, list) else (specs.get("data") or specs.get("specializations") or [])
    if not spec_list:
        raise ApiError(f"Nenhuma especialização encontrada: {specs}")

    chosen = None
    want = cfg.get("specialization") or ""
    for s in spec_list:
        code = str(s.get("specialization") or s.get("code") or s.get("espe_codi") or "")
        if want and code == want:
            chosen = s
            break
    if chosen is None:
        chosen = spec_list[0]
    spec_code = str(chosen.get("specialization") or chosen.get("code") or chosen.get("espe_codi") or "")
    modality = str(chosen.get("modality") or chosen.get("modality_name") or cfg.get("modality") or "")

    user = api.get_user_data("ALUN", spec_code) or {}
    semester = user.get("semester") or chosen.get("ulti_seme") or chosen.get("semester") or ""
    course_code = user.get("course_code") or chosen.get("course_code") or ""
    # o campo `area` do payload do AVA é o código numérico da área do aluno (ex.: "5456")
    area = str(user.get("area") or "") or None
    info = {
        "name": user.get("full_name") or user.get("firstName") or "",
        "course": user.get("course_name") or chosen.get("name") or chosen.get("course_name") or "",
        "spec_code": spec_code,
        "modality": modality,
        "semester": semester,
        "course_code": course_code,
        "area": area,
        "specializations": spec_list,
    }

    tasks = []
    # 1) tentativa direta no agregado de pendências
    pend = api.pending_tests(spec_code, modality, area)
    tasks += parse_pending_tests(pend)

    # 2) fallback: o AVA2 monta a lista chamando /test/get por disciplina
    if not tasks and semester and area:
        try:
            subjects = api.subjects(spec_code, modality, area, semester)
            for s in subjects:
                if not isinstance(s, dict):
                    continue
                try:
                    tests = api.tests_for_subject(spec_code, modality, area, semester,
                                                  str(s.get("code") or ""),
                                                  str(s.get("class") or s.get("turs_codi") or ""),
                                                  str(s.get("course_code") or course_code))
                    parsed = parse_pending_tests(tests)
                    subj_name = str(s.get("description") or "")
                    for t in parsed:
                        # substitui o código (ex.: "ADS19") pelo nome legível
                        if subj_name and (not t.subject or t.subject == str(s.get("code"))):
                            t.subject = subj_name
                    tasks += parsed
                except ApiError as e:
                    log.warning("test/get subj %s: %s", s.get("code"), e)
        except ApiError as e:
            log.warning("subjects: %s", e)

    if cfg.get("include_complementary", True):
        try:
            tasks += parse_complementary(api.complementary_activities(spec_code, modality, area))
        except ApiError as e:
            log.warning("complementary: %s", e)
    if cfg.get("include_calendar", True):
        try:
            tasks += parse_productions(api.productions(spec_code, modality, area))
        except ApiError as e:
            log.warning("productions: %s", e)
    return tasks, info


# ---------------- alertas ----------------
def in_quiet_hours(cfg, now=None):
    q = cfg.get("quiet_hours") or {}
    start, end = q.get("start"), q.get("end")
    if not start or not end:
        return False
    now = now or datetime.now()
    hm = now.strftime("%H:%M")
    if start <= end:
        return start <= hm < end
    return hm >= start or hm < end  # atravessa a meia-noite


def run_check(cfg, force=False):
    """Uma rodada: coleta, filtra por prazo, notifica novidades. Retorna (tasks, alerts, info)."""
    api = UniAPI()
    tasks, info = collect(api, cfg)
    today = date.today()
    n = int(cfg.get("alert_days", 3))

    upcoming = [t for t in tasks if t.deadline and 0 <= t.days_left(today) <= n]
    overdue = [t for t in tasks if t.deadline and t.days_left(today) < 0]
    upcoming.sort(key=lambda t: t.deadline)
    overdue.sort(key=lambda t: t.deadline)

    state = load_state()
    sent = _prune_sent(state.get("sent", {}))
    alerts = []
    quiet = in_quiet_hours(cfg) and not force
    for t in upcoming:
        key = t.key()
        if key in sent:
            continue
        d = t.days_left(today)
        if t.deadline_label == "marcar prova até":
            title = f"Uniasselvi: marque a prova em {d} dia{'s' if d != 1 else ''}"
        else:
            title = f"Uniasselvi: {t.kind} em {d} dia{'s' if d != 1 else ''}"
        periods = t.periods_text()
        body = (f"{t.title}\n"
                f"{t.subject}\n"
                f"{t.deadline_label}: {t.deadline.strftime('%d/%m/%Y')}\n"
                + (f"{periods}\n" if periods else "")
                + "Acesse o AVA2: https://ava2.uniasselvi.com.br")
        if quiet:
            log.info("quiet-hours, não notificado: %s", key)
        else:
            from .notifier import notify
            notify(title, body)
        if cfg.get("sms_enabled"):
            from .sms import send_sms
            sms_text = (f"Uniasselvi: {t.kind} {t.deadline_label} {t.deadline.strftime('%d/%m')}. "
                        f"{t.title[:60]} - {t.subject[:30]}")
            ok, msg = send_sms(cfg, sms_text)
            log.info("sms: %s", msg if ok else f"FALHOU: {msg}")
        sent[key] = today.isoformat()
        alerts.append((t, title, body))

    state["sent"] = sent
    state["last_check"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)
    return tasks, alerts, {"upcoming": upcoming, "overdue": overdue, **info}


# ---------------- loop agendado ----------------
def _parse_hm(s):
    h, m = s.split(":")
    return int(h), int(m)


def next_run_times(cfg, now=None):
    times = cfg.get("check_times") or ["08:30", "18:30"]
    now = now or datetime.now()
    runs = []
    for s in times:
        try:
            h, m = _parse_hm(s)
            # NOTE: o replace() estava FORA do try. Um "check_times" com hora
            # invalida ("25:00") passava por _parse_hm e derrubava datetime.replace
            # com ValueError nao capturado, quebrando o loop inteiro.
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        except Exception:
            continue
        if t <= now:
            t += timedelta(days=1)
        runs.append(t)
    return sorted(runs)


def watch_loop(cfg, stop_event=None):
    """Loop interno (GUI): roda nas horas configuradas até stop_event."""
    while not (stop_event and stop_event.is_set()):
        runs = next_run_times(cfg)
        if not runs:
            time.sleep(3600)
            continue
        wait = (runs[0] - datetime.now()).total_seconds()
        log.info("próxima checagem em %.0f s (%s)", wait, runs[0].strftime("%d/%m %H:%M"))
        end = time.time() + wait
        while time.time() < end:
            if stop_event and stop_event.is_set():
                return
            time.sleep(min(5, end - time.time()))
        try:
            tasks, alerts, info = run_check(cfg)
            log.info("checagem ok: %d pendências, %d alertas novos", len(tasks), len(alerts))
        except AuthError as e:
            log.error("auth: %s", e)
        except Exception as e:
            log.exception("checagem falhou: %s", e)
