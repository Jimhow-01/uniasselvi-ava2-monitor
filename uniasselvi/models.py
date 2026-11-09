"""Normaliza respostas do AVA2 em tarefas com prazo."""
from dataclasses import dataclass, field
from datetime import date, datetime

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d/%m/%y",
]


def parse_date(value):
    """Aceita 'DD/MM/YYYY', 'YYYY-MM-DD HH:MM:SS', ISO etc. Retorna date ou None."""
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "0000-00-00"):
        return None
    # ISO com fuso: 2026-10-30T18:00:00-03:00
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # data + hora separados por espaço com 'T'
    try:
        return datetime.strptime(s.split("T")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _first(d, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", 0):
            return v
    return default


def _as_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("tests", "data", "results", "pendent", "pendentes",
                  "items", "list", "productions", "activities", "events"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _as_list(v)
                if inner:
                    return inner
        lists = [v for v in data.values() if isinstance(v, list)]
        if len(lists) == 1:
            return lists[0]
    return []


@dataclass
class Task:
    kind: str            # prova | trabalho | avaliação | atividade | producao
    id: str
    title: str
    subject: str = ""
    deadline: date = None
    deadline_label: str = ""   # 'marcar prova até' | 'entrega' | 'prova agendada'
    status: str = ""
    sched_start: date = None   # período para agendar
    sched_end: date = None
    real_start: date = None    # período para realizar
    real_end: date = None
    sched_info: str = ""       # data/hora/local quando já agendada
    raw: dict = field(default_factory=dict, repr=False)

    def days_left(self, today=None):
        if not self.deadline:
            return None
        today = today or date.today()
        return (self.deadline - today).days

    def key(self):
        d = self.deadline.isoformat() if self.deadline else "nodate"
        return f"{self.kind}:{self.id}:{d}"

    def periods_text(self):
        """Ex.: 'Agendar: 12/10/2026 até 14/11/2026 · Realizar: 09/11/2026 até 21/11/2026'."""
        def f(d):
            return d.strftime("%d/%m/%Y") if d else "?"
        parts = []
        if self.sched_start or self.sched_end:
            parts.append(f"Agendar: {f(self.sched_start)} até {f(self.sched_end)}")
        if self.real_start or self.real_end:
            parts.append(f"Realizar: {f(self.real_start)} até {f(self.real_end)}")
        if self.sched_info:
            parts.append(self.sched_info)
        return " · ".join(parts)


def _kind_for_test(t):
    desc = str(_first(t, "type_description", "typeDescription", "description",
                      default="")).lower()
    if _first(t, "need_schedule", "needSchedule"):
        return "prova"
    # NOTE (ordem corrigida): o teste de "final" vinha antes dos marcadores de
    # trabalho, entao "Sintese final", "Producao final" e "Trabalho final" eram
    # classificados como PROVA. O sinal estrutural (need_schedule) continua em
    # primeiro; os marcadores de trabalho passam antes de "final", que agora so
    # decide quando nada mais casou ("Prova Final" continua prova).
    if ("produ" in desc or "desafio" in desc or "síntese" in desc
            or "trabalho" in desc):
        return "trabalho"
    if "final" in desc:
        return "prova"
    return "avaliação"


def parse_pending_tests(data):
    """/test/pendent/get e /test/get -> lista de Task.

    Regras (espelhando o AVA2):
      - need_schedule sem has_schedule  -> prazo de MARCAR a prova (schedule_window_end)
      - has_schedule                    -> prova agendada (schedule.data / data do agendamento)
      - demais                          -> entrega (end_date / janela de realização)
    """
    tasks = []
    for t in _as_list(data):
        if not isinstance(t, dict):
            continue
        # já feita? ignora
        made = _first(t, "exam_made", "examMade", "made", default=None)
        if made in (1, "1", True, "true"):
            continue
        kind = _kind_for_test(t)
        need_sched = _first(t, "need_schedule", "needSchedule")
        has_sched = _first(t, "has_schedule", "hasSchedule")

        # janelas de agendamento e de realização (formatos DD/MM/YYYY ou ISO)
        sched_start = parse_date(_first(t, "schedule_window_start", "schedule_window_begin"))
        sched_end = parse_date(_first(t, "schedule_window_end", "schedule_window_finish"))
        real_start = parse_date(_first(t, "realization_window_start", "realization_window_begin",
                                       "realization_1_oportunity_start"))
        real_end = parse_date(_first(t, "realization_window_end", "realization_window_finish",
                                     "realization_1_oportunity_end"))

        # agendamento concreto (quando já marcou a prova)
        sched = t.get("schedule") or {}
        sched_date = sched_hora = sched_local = None
        if isinstance(sched, dict) and sched:
            sched_date = parse_date(_first(sched, "data", "date", "begin_date",
                                           "schedule_date", "date_start", "beginDate"))
            sched_hora = _first(sched, "hora_inicio", "hour_start", default="")
            local = _first(sched, "ambiente", default="")
            end = _first(sched, "endereco", default="")
            if end:
                local = f"{local} — {end}" if local else end
            sched_local = local or None

        deadline = None
        label = ""
        if need_sched and not has_sched:
            # prova ainda não marcada: o que vale é o ÚLTIMO dia para agendar
            deadline = sched_end
            label = "marcar prova até"
        elif has_sched and sched_date:
            deadline = sched_date
            label = "prova agendada"
        if deadline is None:
            deadline = parse_date(_first(t, "realization_date", "end_date", "endDate")) or real_end
            if label == "":
                label = "entrega"

        title = _first(t, "description", "title", default="(sem título)")
        subject = _first(t, "subject_description", "subject_name", "discipline", default="")
        if isinstance(subject, dict):
            subject = subject.get("description") or subject.get("name") or ""
        if not subject:
            subject = _first(t, "subject", default="")
            if isinstance(subject, dict):
                subject = subject.get("description") or ""
        tid = _first(t, "code", "test_code", "id", default=None)
        status = _first(t, "status_description", "status", default="")

        sched_info = ""
        if has_sched and sched_date:
            sched_info = sched_date.strftime("%d/%m/%Y")
            if sched_hora:
                sched_info += f" {str(sched_hora)[:5]}"
            if sched_local:
                sched_info += f" · {sched_local}"

        tasks.append(Task(kind=kind, id=str(tid), title=str(title), subject=str(subject),
                          deadline=deadline, deadline_label=label, status=str(status),
                          sched_start=sched_start, sched_end=sched_end,
                          real_start=real_start, real_end=real_end,
                          sched_info=sched_info, raw=t))
    return tasks


def parse_complementary(data):
    tasks = []
    for a in _as_list(data):
        if not isinstance(a, dict):
            continue
        deadline = parse_date(_first(a, "end_date", "delivery_date", "due_date",
                                     "final_date", "endDate", "date_end"))
        status = _first(a, "situation_description", "status_description", "situation", default="")
        if str(status).lower() in ("entregue", "aprovado", "done", "concluído", "concluido"):
            continue
        title = _first(a, "title", "description", "name", default="(atividade)")
        aid = _first(a, "code", "id", default=None)
        subject = _first(a, "subject_description", "subject", default="")
        tasks.append(Task(kind="atividade", id=str(aid), title=str(title), subject=str(subject),
                          deadline=deadline, deadline_label="entrega de atividade",
                          status=str(status), raw=a))
    return tasks


def parse_productions(data):
    tasks = []
    for p in _as_list(data):
        if not isinstance(p, dict):
            continue
        deadline = parse_date(_first(p, "end_date", "delivery_date", "due_date", "endDate"))
        status = _first(p, "situation_description", "situationDescription", default="")
        title = _first(p, "title", "description", default="(produção)")
        pid = _first(p, "code", "id", default=None)
        subject = _first(p, "subject_description", "subjectDescription", default="")
        tasks.append(Task(kind="producao", id=str(pid), title=str(title), subject=str(subject),
                          deadline=deadline, deadline_label="entrega",
                          status=str(status), raw=p))
    return tasks
