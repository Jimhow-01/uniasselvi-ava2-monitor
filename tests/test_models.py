"""Testes do parsing de datas e da construcao de tarefas (uniasselvi/models.py).

Nada aqui toca rede nem disco: models.py e puro.
"""
from datetime import date

from uniasselvi.models import (
    Task,
    _as_list,
    _first,
    parse_complementary,
    parse_date,
    parse_pending_tests,
    parse_productions,
)


# ---------------------------------------------------------------- parse_date
def test_parse_date_bruta_ddmmaaaa():
    assert parse_date("30/11/2026") == date(2026, 11, 30)


def test_parse_date_iso_com_hora():
    assert parse_date("2026-11-30 23:59:59") == date(2026, 11, 30)


def test_parse_date_iso_puro():
    assert parse_date("2026-11-30") == date(2026, 11, 30)


def test_parse_date_iso_com_fuso():
    # o AVA2 devolve '2026-10-30T18:00:00-03:00'; strptime dos DATE_FORMATS nao
    # casa isso, entao o fromisoformat do topo precisa pegar
    assert parse_date("2026-10-30T18:00:00-03:00") == date(2026, 10, 30)


def test_parse_date_ano_curto():
    assert parse_date("30/11/26") == date(2026, 11, 30)


def test_parse_date_datetime_objeto():
    from datetime import datetime

    assert parse_date(datetime(2026, 11, 30, 18, 0)) == date(2026, 11, 30)
    assert parse_date(date(2026, 11, 30)) == date(2026, 11, 30)


def test_parse_date_valores_vazios_do_portal():
    # o portal devolve literalmente "0000-00-00" e "null" quando nao ha prazo
    for bad in ("", None, "null", "none", "0000-00-00", "   "):
        assert parse_date(bad) is None, bad


def test_parse_date_lixo():
    assert parse_date("não é uma data") is None


def test_parse_date_data_hora_com_T_fora_de_formato():
    # ultimo recurso: 'YYYY-MM-DDTqualquer coisa'
    assert parse_date("2026-11-30T") == date(2026, 11, 30)


# ---------------------------------------------------------------- _first
def test_first_pula_none_vazio_e_zero():
    d = {"a": None, "b": "", "c": 0, "d": "valor"}
    assert _first(d, "a", "b", "c", "d") == "valor"


def test_first_preserva_falsy_valido():
    # 0 e descartado de proposito (o portal usa 0 como "sem valor")
    assert _first({"a": 0}, "a", default="fallback") == "fallback"


def test_first_default():
    assert _first({}, "x", "y", default="padrao") == "padrao"


# ---------------------------------------------------------------- _as_list
def test_as_list_com_lista():
    assert _as_list([1, 2]) == [1, 2]


def test_as_list_com_chave_conhecida():
    assert _as_list({"tests": [1, 2]}) == [1, 2]
    assert _as_list({"data": [3]}) == [3]
    assert _as_list({"pendentes": [4]}) == [4]


def test_as_list_dict_aninhado():
    assert _as_list({"data": {"results": [5, 6]}}) == [5, 6]


def test_as_list_uma_unica_lista_sem_chave_conhecida():
    assert _as_list({"qualquer_coisa": [7]}) == [7]


def test_as_list_ambiguo_retorna_vazio():
    # duas listas e nenhuma chave conhecida: nao ha como escolher, devolve []
    assert _as_list({"a": [1], "b": [2]}) == []


def test_as_list_nao_iteravel():
    assert _as_list("texto") == []
    assert _as_list(None) == []


# ---------------------------------------------------------------- classificacao
def test_kind_prova_por_need_schedule():
    tasks = parse_pending_tests([{"need_schedule": 1, "schedule_window_end": "30/11/2026"}])
    assert tasks[0].kind == "prova"


def test_kind_prova_por_descricao_final():
    tasks = parse_pending_tests([{"type_description": "Prova Final", "end_date": "30/11/2026"}])
    assert tasks[0].kind == "prova"


def test_kind_trabalho_por_palavras_chave():
    for desc in ("Produção acadêmica", "Desafio da disciplina", "Síntese final", "Trabalho"):
        tasks = parse_pending_tests([{"type_description": desc, "end_date": "30/11/2026"}])
        assert tasks[0].kind == "trabalho", desc


def test_kind_avaliacao_padrao():
    tasks = parse_pending_tests([{"type_description": "Questionário", "end_date": "30/11/2026"}])
    assert tasks[0].kind == "avaliação"


# ---------------------------------------------------------------- as 3 janelas
def test_janela_de_agendamento_manda_no_prazo():
    """Regra central: prova que precisa ser agendada e ainda nao foi -> o prazo que
    importa e o fim da janela de agendamento, nao a data da prova."""
    tasks = parse_pending_tests([{
        "need_schedule": 1,
        "has_schedule": 0,
        "schedule_window_start": "01/11/2026",
        "schedule_window_end": "14/11/2026",
        "realization_window_start": "09/11/2026",
        "realization_window_end": "21/11/2026",
        "description": "Prova presencial",
    }])
    assert len(tasks) == 1
    t = tasks[0]
    assert t.deadline == date(2026, 11, 14)
    assert t.deadline_label == "marcar prova até"
    # as janelas continuam disponiveis para exibir no painel
    assert t.sched_start == date(2026, 11, 1)
    assert t.real_end == date(2026, 11, 21)


def test_prova_ja_agendada_usa_a_data_agendada():
    tasks = parse_pending_tests([{
        "need_schedule": 1,
        "has_schedule": 1,
        "schedule": {"data": "20/11/2026", "hora_inicio": "19:00", "ambiente": "Sala 3"},
        "description": "Prova presencial",
    }])
    t = tasks[0]
    assert t.deadline == date(2026, 11, 20)
    assert t.deadline_label == "prova agendada"
    assert "20/11/2026" in t.sched_info
    assert "19:00" in t.sched_info
    assert "Sala 3" in t.sched_info


def test_entrega_comum_usa_end_date():
    tasks = parse_pending_tests([{"end_date": "05/12/2026", "description": "Fórum"}])
    assert tasks[0].deadline == date(2026, 12, 5)
    assert tasks[0].deadline_label == "entrega"


def test_prova_agendada_sem_data_de_agendamento_cai_na_janela_de_realizacao():
    tasks = parse_pending_tests([{
        "has_schedule": 1,
        "schedule": {},
        "realization_window_end": "18/11/2026",
    }])
    assert tasks[0].deadline == date(2026, 11, 18)


def test_ignora_o_que_ja_foi_feito():
    tasks = parse_pending_tests([
        {"exam_made": 1, "end_date": "30/11/2026"},
        {"examMade": "1", "end_date": "30/11/2026"},
        {"made": True, "end_date": "30/11/2026"},
        {"end_date": "30/11/2026"},
    ])
    assert len(tasks) == 1


def test_subject_como_dict():
    tasks = parse_pending_tests([{
        "end_date": "30/11/2026",
        "subject_description": {"description": "Disciplina Exemplo"},
    }])
    assert tasks[0].subject == "Disciplina Exemplo"


def test_ignora_itens_nao_dict():
    tasks = parse_pending_tests([{"end_date": "30/11/2026"}, "lixo", None, 42])
    assert len(tasks) == 1


def test_envolve_envelope_de_resposta():
    tasks = parse_pending_tests({"data": {"tests": [{"end_date": "30/11/2026"}]}})
    assert len(tasks) == 1


# ---------------------------------------------------------------- Task
def test_task_days_left():
    t = Task(kind="prova", id="1", title="x", deadline=date(2026, 11, 10))
    assert t.days_left(today=date(2026, 11, 7)) == 3
    assert t.days_left(today=date(2026, 11, 10)) == 0
    assert t.days_left(today=date(2026, 11, 12)) == -2


def test_task_days_left_sem_prazo():
    assert Task(kind="prova", id="1", title="x").days_left() is None


def test_task_key_estavel_para_dedupe():
    t = Task(kind="prova", id="42", title="x", deadline=date(2026, 11, 10))
    assert t.key() == "prova:42:2026-11-10"
    assert t.key() == t.key()
    # sem prazo usa sentinela, nao 'None'
    assert Task(kind="prova", id="42", title="x").key() == "prova:42:nodate"


def test_task_periods_text():
    t = Task(
        kind="prova", id="1", title="x",
        sched_start=date(2026, 10, 12), sched_end=date(2026, 10, 14),
        real_start=date(2026, 10, 9), real_end=date(2026, 10, 21),
    )
    txt = t.periods_text()
    assert txt.startswith("Agendar: 12/10/2026 até 14/10/2026")
    assert "Realizar: 09/10/2026 até 21/10/2026" in txt


def test_task_periods_text_vazio_quando_nao_ha_janela():
    assert Task(kind="prova", id="1", title="x").periods_text() == ""


# ---------------------------------------------------------------- complementary / productions
def test_complementary_descarta_entregue():
    tasks = parse_complementary([
        {"code": "1", "end_date": "30/11/2026", "situation_description": "Entregue"},
        {"code": "2", "end_date": "30/11/2026", "situation_description": "Aprovado"},
        {"code": "3", "end_date": "30/11/2026", "situation_description": "Em aberto"},
    ])
    assert [t.id for t in tasks] == ["3"]
    assert tasks[0].kind == "atividade"
    assert tasks[0].deadline_label == "entrega de atividade"


def test_productions_mantem_todas_com_kind_proprio():
    tasks = parse_productions([{"code": "9", "end_date": "30/11/2026", "title": "Produção"}])
    assert tasks[0].kind == "producao"
    assert tasks[0].deadline_label == "entrega"
