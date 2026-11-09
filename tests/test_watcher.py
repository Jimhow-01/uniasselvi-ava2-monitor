"""Testes do agendamento e da deduplicacao de alertas (uniasselvi/watcher.py).

Nenhuma chamada de rede: collect() e notify() sao substituidos por stubs.
"""
from datetime import date, datetime, timedelta

import pytest

from uniasselvi import watcher
from uniasselvi.models import Task


# ---------------------------------------------------------------- quiet hours
def test_quiet_hours_desativada_sem_config():
    assert watcher.in_quiet_hours({}) is False
    assert watcher.in_quiet_hours({"quiet_hours": {}}) is False
    assert watcher.in_quiet_hours({"quiet_hours": {"start": "22:00"}}) is False


def test_quiet_hours_dentro_da_janela_mesmo_dia():
    cfg = {"quiet_hours": {"start": "22:00", "end": "23:30"}}
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 22, 30)) is True
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 21, 59)) is False


def test_quiet_hours_borda_exclusiva_no_fim():
    cfg = {"quiet_hours": {"start": "22:00", "end": "23:30"}}
    # start e inclusivo, end e exclusivo (o codigo usa `start <= hm < end`)
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 22, 0)) is True
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 23, 30)) is False


def test_quiet_hours_atravessa_a_meia_noite():
    """22:00-07:00 e o padrao do app: a janela comeca depois de terminar."""
    cfg = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 23, 0)) is True
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 3, 0)) is True
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 6, 59)) is True
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 7, 0)) is False
    assert watcher.in_quiet_hours(cfg, now=datetime(2026, 11, 5, 12, 0)) is False


# ---------------------------------------------------------------- proxima execucao
def test_parse_hm():
    assert watcher._parse_hm("08:30") == (8, 30)
    assert watcher._parse_hm("18:05") == (18, 5)


def test_next_run_times_usa_padrao_quando_config_vazio():
    now = datetime(2026, 11, 5, 9, 0)
    runs = watcher.next_run_times({}, now=now)
    assert [r.strftime("%H:%M") for r in runs] == ["18:30", "08:30"]
    # a de 08:30 ja passou hoje, entao e amanha
    assert runs[1].date() == date(2026, 11, 6)
    assert runs[0].date() == date(2026, 11, 5)


def test_next_run_times_ordena():
    now = datetime(2026, 11, 5, 0, 0)
    runs = watcher.next_run_times({"check_times": ["18:30", "08:30"]}, now=now)
    assert [r.strftime("%H:%M") for r in runs] == ["08:30", "18:30"]


def test_next_run_times_ignora_hora_invalida_sem_quebrar():
    """NOTE: antes da correcao, "25:00" passava por _parse_hm e derrubava
    datetime.replace fora do try -> ValueError nao capturado matava o loop."""
    now = datetime(2026, 11, 5, 9, 0)
    runs = watcher.next_run_times({"check_times": ["25:00", "18:30"]}, now=now)
    assert [r.strftime("%H:%M") for r in runs] == ["18:30"]


def test_next_run_times_ignora_string_malformada():
    now = datetime(2026, 11, 5, 9, 0)
    runs = watcher.next_run_times({"check_times": ["nove e meia", "18:30"]}, now=now)
    assert [r.strftime("%H:%M") for r in runs] == ["18:30"]


def test_next_run_times_exato_no_minuto_rola_para_o_dia_seguinte():
    now = datetime(2026, 11, 5, 18, 30)
    runs = watcher.next_run_times({"check_times": ["18:30"]}, now=now)
    assert runs[0].date() == date(2026, 11, 6)


# ---------------------------------------------------------------- prune do estado
def test_prune_sent_descarta_com_mais_de_30_dias():
    today = date.today()
    old = (today - timedelta(days=45)).isoformat()
    recent = (today - timedelta(days=5)).isoformat()
    out = watcher._prune_sent({"a": old, "b": recent})
    assert out == {"b": recent}


def test_prune_sent_mantem_data_de_hoje():
    out = watcher._prune_sent({"a": date.today().isoformat()})
    assert out == {"a": date.today().isoformat()}


def test_prune_sent_descarta_valor_nao_data():
    # chave com valor inesperado (estado corrompido) sai, nao explode
    out = watcher._prune_sent({"a": "não-é-data", "b": date.today().isoformat()})
    assert "b" in out


# ---------------------------------------------------------------- state em disco
def test_load_state_criou_padrao_sem_arquivo():
    st = watcher.load_state()
    assert st == {"sent": {}, "last_check": None}


def test_save_e_load_state_roundtrip(tmp_path):
    watcher.save_state({"sent": {"prova:1:2026-11-10": "2026-11-07"}, "last_check": "x"})
    st = watcher.load_state()
    assert st["sent"] == {"prova:1:2026-11-10": "2026-11-07"}
    # o arquivo foi escrito no tmp_path do fixture, nao no diretorio do app
    assert (tmp_path / "state.json").exists()


def test_load_state_recupera_de_json_corrompido(tmp_path):
    (tmp_path / "state.json").write_text("{isso não é json", encoding="utf-8")
    assert watcher.load_state() == {"sent": {}, "last_check": None}


# ---------------------------------------------------------------- run_check
def _stub_collect(monkeypatch, tasks, info=None):
    monkeypatch.setattr(watcher, "collect", lambda api, cfg: (tasks, info or {}))
    monkeypatch.setattr(watcher, "load_password", lambda: "senha-de-teste")


@pytest.fixture
def no_notify(monkeypatch):
    """Captura os toasts em vez de chamar o Windows."""
    calls = []
    import uniasselvi.notifier as notifier

    monkeypatch.setattr(notifier, "notify", lambda title, body: calls.append((title, body)))
    return calls


def test_run_check_notifica_pendencias_dentro_da_janela(monkeypatch, no_notify):
    today = date.today()
    tasks = [
        Task(kind="prova", id="1", title="Prova 1", subject="Disciplina Exemplo",
             deadline=today + timedelta(days=2), deadline_label="marcar prova até"),
        Task(kind="trabalho", id="2", title="Trabalho 2", subject="Disciplina Exemplo",
             deadline=today + timedelta(days=20), deadline_label="entrega"),
    ]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    _, alerts, info = watcher.run_check(cfg)
    assert len(alerts) == 1
    assert "marque a prova em 2 dias" in alerts[0][1]
    assert len(no_notify) == 1
    assert "ava2.uniasselvi.com.br" in alerts[0][2]
    # a de 20 dias fica fora da janela de alerta mas continua listada
    assert len(info["upcoming"]) == 1


def test_run_check_nao_repete_alerta_ja_enviado(monkeypatch, no_notify):
    today = date.today()
    tasks = [Task(kind="prova", id="1", title="Prova 1",
                  deadline=today + timedelta(days=1), deadline_label="entrega")]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    watcher.run_check(cfg)
    _, alerts2, _ = watcher.run_check(cfg)
    assert len(alerts2) == 0
    assert len(no_notify) == 1, "a segunda rodada nao deve notificar de novo"


def test_run_check_deduplica_entre_as_duas_camadas(monkeypatch, no_notify):
    """Startup e tarefa agendada rodam o mesmo run_check; o state e o que impede
    o dobro de toast."""
    today = date.today()
    tasks = [Task(kind="prova", id="7", title="Prova",
                  deadline=today + timedelta(days=1), deadline_label="entrega")]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    watcher.run_check(cfg)          # camada 1
    watcher.run_check(cfg)          # camada 2
    assert len(no_notify) == 1


def test_run_check_quiet_hours_supime_toast_mas_registra_como_enviado(monkeypatch, no_notify):
    today = date.today()
    tasks = [Task(kind="prova", id="1", title="Prova",
                  deadline=today + timedelta(days=1), deadline_label="entrega")]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3,
           "quiet_hours": {"start": "00:00", "end": "23:59"}}

    _, alerts, _ = watcher.run_check(cfg)
    assert len(alerts) == 1        # a tarefa foi processada
    assert len(no_notify) == 0     # mas nenhum toast saiu
    # e ficou marcada como enviada: a proxima rodada fora do quiet nao avisa
    _, alerts2, _ = watcher.run_check(cfg, force=True)
    assert len(alerts2) == 0


def test_run_check_forced_ignora_quiet_hours(monkeypatch, no_notify):
    today = date.today()
    tasks = [Task(kind="prova", id="1", title="Prova",
                  deadline=today + timedelta(days=1), deadline_label="entrega")]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3,
           "quiet_hours": {"start": "00:00", "end": "23:59"}}

    watcher.run_check(cfg, force=True)
    assert len(no_notify) == 1, 'force=True (botao "Verificar agora") deve notificar'


def test_run_check_separa_atrasados(monkeypatch, no_notify):
    today = date.today()
    tasks = [
        Task(kind="trabalho", id="1", title="Atrasado",
             deadline=today - timedelta(days=4), deadline_label="entrega"),
        Task(kind="trabalho", id="2", title="No prazo",
             deadline=today + timedelta(days=1), deadline_label="entrega"),
    ]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    _, alerts, info = watcher.run_check(cfg)
    assert [t.id for t in info["overdue"]] == ["1"]
    assert [t.id for t in info["upcoming"]] == ["2"]
    # atrasado nao entra em upcoming, entao nao gera toast por essa via
    assert len(alerts) == 1


def test_run_check_ordena_por_prazo(monkeypatch, no_notify):
    today = date.today()
    tasks = [
        Task(kind="prova", id="longe", title="L", deadline=today + timedelta(days=3),
             deadline_label="entrega"),
        Task(kind="prova", id="perto", title="P", deadline=today + timedelta(days=1),
             deadline_label="entrega"),
    ]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    _, _, info = watcher.run_check(cfg)
    assert [t.id for t in info["upcoming"]] == ["perto", "longe"]


def test_run_check_ignora_tarefa_sem_prazo(monkeypatch, no_notify):
    tasks = [Task(kind="prova", id="1", title="Sem prazo", deadline=None)]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 3, "quiet_hours": {}}

    _, alerts, info = watcher.run_check(cfg)
    assert alerts == []
    assert info["upcoming"] == [] and info["overdue"] == []


def test_run_check_plural_de_dias_no_titulo(monkeypatch, no_notify):
    today = date.today()
    tasks = [
        Task(kind="prova", id="1", title="Um dia", deadline=today + timedelta(days=1),
             deadline_label="entrega"),
        Task(kind="prova", id="2", title="Quatro dias", deadline=today + timedelta(days=4),
             deadline_label="entrega"),
    ]
    _stub_collect(monkeypatch, tasks)
    cfg = {"cpf": "000.000.000-00", "alert_days": 5, "quiet_hours": {}}

    _, alerts, _ = watcher.run_check(cfg)
    titles = [a[1] for a in alerts]
    assert any(" em 1 dia" in t and " dias" not in t for t in titles)
    assert any(" em 4 dias" in t for t in titles)
