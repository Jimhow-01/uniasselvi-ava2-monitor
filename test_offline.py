"""Testes offline (sem login): parsing de datas, construção de tarefas, alertas."""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uniasselvi import watcher
from uniasselvi.models import parse_complementary, parse_date, parse_pending_tests

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}")


print("== parse_date ==")
check("DD/MM/YYYY", parse_date("30/11/2026") == date(2026, 11, 30))
check("YYYY-MM-DD HH:MM:SS", parse_date("2026-11-30 23:59:59") == date(2026, 11, 30))
check("ISO", parse_date("2026-11-30") == date(2026, 11, 30))
check("ISO com hora", parse_date("2026-11-30T18:00:00") == date(2026, 11, 30))
check("vazio", parse_date("") is None and parse_date(None) is None)
check("lixo", parse_date("abc") is None)

today = date.today()
d3 = (today + timedelta(days=3)).strftime("%d/%m/%Y")
d30 = (today + timedelta(days=30)).strftime("%d/%m/%Y")
d1 = (today - timedelta(days=1)).strftime("%d/%m/%Y")

print("== parse_pending_tests ==")
fake = [
    # avaliação online comum (janela de entrega)
    {"code": 111, "description": "Avaliação P1 Online", "type_description": "Avaliação Online",
     "end_date": d3, "subject_description": "Disciplina A", "exam_made": 0,
     "need_schedule": 0, "has_schedule": 0},
    # prova final que precisa MARCAR (janela de agendamento + janela de realização)
    {"code": 222, "description": "Avaliação Final (Objetiva) - Individual",
     "schedule_window_start": "12/10/2026", "schedule_window_end": d3,
     "realization_window_start": (today + timedelta(days=1)).strftime("%d/%m/%Y"),
     "realization_window_end": (today + timedelta(days=10)).strftime("%d/%m/%Y"),
     "subject_description": "Disciplina B", "exam_made": 0,
     "need_schedule": True, "has_schedule": False},
    # prova já marcada (schedule concreto com data/hora/local)
    {"code": 333, "description": "Avaliação Final (Objetiva) - Individual",
     "subject_description": "Disciplina C", "exam_made": 0, "need_schedule": True,
     "has_schedule": True,
     "schedule": {"data": d30, "hora_inicio": "16:20:00", "ambiente": "Secretaria - Sala 1"}},
    # trabalho/produção pendente
    {"code": 444, "description": "Avaliação III - Desafio Profissional - Individual",
     "end_date": d1, "subject_description": "Disciplina D", "exam_made": 0},
    # já feita -> ignora
    {"code": 555, "description": "Já respondida", "type_description": "Avaliação Online",
     "end_date": d3, "exam_made": 1},
]
tasks = parse_pending_tests(fake)
check("5 itens -> 4 tarefas", len(tasks) == 4)
t = {x.id: x for x in tasks}
check("avaliação online kind", t["111"].kind == "avaliação" and t["111"].deadline_label == "entrega")
check("marcar prova: deadline = último dia p/ agendar",
      t["222"].kind == "prova" and t["222"].deadline_label == "marcar prova até"
      and t["222"].deadline == today + timedelta(days=3))
check("marcar prova: períodos agendar/realizar",
      t["222"].periods_text() == (f"Agendar: 12/10/2026 até {(today+timedelta(days=3)).strftime('%d/%m/%Y')}"
                                  f" · Realizar: {(today+timedelta(days=1)).strftime('%d/%m/%Y')}"
                                  f" até {(today+timedelta(days=10)).strftime('%d/%m/%Y')}"))
check("agendada usa schedule.data e mostra local/hora",
      t["333"].deadline == today + timedelta(days=30)
      and t["333"].deadline_label == "prova agendada"
      and "16:20" in t["333"].periods_text() and "Secretaria" in t["333"].periods_text())
check("desafio profissional = trabalho", t["444"].kind == "trabalho")
check("dias restantes", t["111"].days_left() == 3 and t["444"].days_left() == -1)

print("== parse_complementary ==")
fakec = [{"code": 900, "title": "Atividade complementar", "end_date": d3,
          "situation_description": "Aguardando entrega", "subject_description": "EAD"}]
tc = parse_complementary(fakec)
check("atividade parseada", len(tc) == 1 and tc[0].kind == "atividade" and tc[0].deadline == today + timedelta(days=3))

print("== run_check com dados simulados ==")
tmp = tempfile.mkdtemp()
watcher.STATE_PATH = os.path.join(tmp, "state.json")
orig_collect = watcher.collect


def fake_collect(api, cfg):
    return tasks, {"name": "Aluno Teste", "course": "Curso X", "semester": "2026/2"}


watcher.collect = fake_collect
import uniasselvi.notifier as notifier

sent = []
notifier._toast_win11 = lambda title, body: (sent.append((title, body)), True)[1]

cfg = {"cpf": "x", "alert_days": 3, "check_times": ["08:30"], "quiet_hours": {}}
_, alerts1, info1 = watcher.run_check(cfg, force=True)
check("3 alertas (111,222,444 vencendo/atrasado -> só <=3d e >=0)", len(alerts1) == 2)
check("toast chamado 2x", len(sent) == 2)
_, alerts2, _ = watcher.run_check(cfg, force=True)
check("sem duplicata na 2a rodada", len(alerts2) == 0)
watcher.collect = orig_collect

print(f"\n{ok} ok, {fail} falhas")
sys.exit(1 if fail else 0)
