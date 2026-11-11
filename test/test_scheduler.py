"""Testes do orquestrador: ocorrências agendadas e avaliação de vencidos."""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.scheduler import JobSpec, ScheduleFile, _vencido, ultima_ocorrencia, proxima_ocorrencia

TZ = ZoneInfo("America/Sao_Paulo")
JOB = JobSpec(name="j", schedule="daily 05:00", queries=["x"])


def test_daily_antes_do_horario_vira_ontem():
    agora = datetime(2026, 11, 10, 3, 0, tzinfo=TZ)
    assert ultima_ocorrencia("daily 05:00", agora) == datetime(2026, 11, 9, 5, 0, tzinfo=TZ)


def test_daily_depois_do_horario_e_hoje():
    agora = datetime(2026, 11, 10, 7, 0, tzinfo=TZ)
    assert ultima_ocorrencia("daily 05:00", agora) == datetime(2026, 11, 10, 5, 0, tzinfo=TZ)


def test_weekly_acha_a_ultima_ocorrencia():
    # 10/11/2026 é terça; "weekly mon 06:00" -> segunda 09/11 06:00
    agora = datetime(2026, 11, 10, 7, 0, tzinfo=TZ)
    assert ultima_ocorrencia("weekly mon 06:00", agora) == datetime(2026, 11, 9, 6, 0, tzinfo=TZ)


def test_vencido_quando_nunca_executou():
    deve, _ = _vencido(JOB, {}, datetime(2026, 11, 10, 7, 0, tzinfo=TZ), 30)
    assert deve


def test_nao_vencido_quando_sucesso_apos_ocorrencia():
    state = {"j": {"last_success": "2026-11-10T05:02:00-03:00"}}
    deve, _ = _vencido(JOB, state, datetime(2026, 11, 10, 7, 0, tzinfo=TZ), 30)
    assert not deve


def test_vencido_quando_sucesso_e_da_ocorrencia_anterior():
    state = {"j": {"last_success": "2026-11-09T05:02:00-03:00"}}
    deve, _ = _vencido(JOB, state, datetime(2026, 11, 10, 7, 0, tzinfo=TZ), 30)
    assert deve


def test_cooldown_bloqueia_retry_recente():
    state = {"j": {"last_success": "2026-11-09T05:02:00-03:00",
                   "last_attempt": "2026-11-10T06:50:00-03:00",
                   "last_result": "failed"}}

def test_cooldown_bloqueia_retry_recente():
    state = {"j": {"last_success": "2026-11-09T05:02:00-03:00",
                   "last_attempt": "2026-11-10T06:50:00-03:00",
                   "last_result": "failed"}}
    agora = datetime(2026, 11, 10, 7, 0, tzinfo=TZ)
    deve, motivo = _vencido(JOB, state, agora, 30)
    # Tentativa falhou 10 min atrás (< cooldown de 30 min): não reexecuta
    assert not deve
    assert "cooldown" in motivo


def test_cooldown_expirado_permite_retry():
    state = {"j": {"last_success": "2026-11-09T05:02:00-03:00",
                   "last_attempt": "2026-11-10T06:50:00-03:00",
                   "last_result": "failed"}}
    agora = datetime(2026, 11, 10, 7, 30, tzinfo=TZ)
    deve, _ = _vencido(JOB, state, agora, 30)
    assert deve


def test_schedule_invalido_levanta_erro():
    import pytest
    with pytest.raises(ValueError):
        ultima_ocorrencia("hourly 09:00", datetime(2026, 11, 10, 7, 0, tzinfo=TZ))

def test_lock_bloqueia_segundo_tick(tmp_path):
    from src.scheduler import _tentar_lock
    caminho = tmp_path / "scheduler.lock"
    primeiro = _tentar_lock(caminho)
    assert primeiro is not None
    assert _tentar_lock(caminho) is None
    primeiro.close()
    caminho.unlink()
    assert _tentar_lock(caminho) is not None


def test_lock_orfao_antigo_e_reciclado(tmp_path):
    import os
    import time
    from src.scheduler import _tentar_lock
    caminho = tmp_path / "scheduler.lock"
    caminho.write_text("", encoding="utf-8")
    antigo = time.time() - 7200
    os.utime(caminho, (antigo, antigo))
    handle = _tentar_lock(caminho)
    assert handle is not None
    handle.close()

def test_every_dez_minutos_usa_marcas_fixas_de_relogio():
    agora = datetime(2026, 11, 11, 23, 47, tzinfo=TZ)
    assert ultima_ocorrencia("every 10 minutes", agora) == datetime(2026, 11, 11, 23, 40, tzinfo=TZ)


def test_every_exatamente_na_marca_e_a_propria_marca():
    agora = datetime(2026, 11, 11, 23, 50, tzinfo=TZ)
    assert ultima_ocorrencia("every 10 minutes", agora) == datetime(2026, 11, 11, 23, 50, tzinfo=TZ)

def test_proxima_ocorrencia_daily_hoje_ainda_por_vir():
    agora = datetime(2026, 11, 11, 3, 0, tzinfo=TZ)
    assert proxima_ocorrencia("daily 05:00", agora) == datetime(2026, 11, 11, 5, 0, tzinfo=TZ)


def test_proxima_ocorrencia_daily_ja_passou_vira_amanha():
    agora = datetime(2026, 11, 11, 7, 0, tzinfo=TZ)
    assert proxima_ocorrencia("daily 05:00", agora) == datetime(2026, 11, 12, 5, 0, tzinfo=TZ)


def test_proxima_ocorrencia_weekly_avanca_ate_o_dia():
    # 11/11/2026 é quarta; próximo "weekly mon 06:00" é segunda 16/11
    agora = datetime(2026, 11, 11, 7, 0, tzinfo=TZ)
    assert proxima_ocorrencia("weekly mon 06:00", agora) == datetime(2026, 11, 16, 6, 0, tzinfo=TZ)


def test_proxima_ocorrencia_every_dez_minutos():
    agora = datetime(2026, 11, 11, 23, 47, tzinfo=TZ)
    assert proxima_ocorrencia("every 10 minutes", agora) == datetime(2026, 11, 11, 23, 50, tzinfo=TZ)


def test_proxima_ocorrencia_every_vira_o_dia_meianoite():
    agora = datetime(2026, 11, 11, 23, 55, tzinfo=TZ)
    assert proxima_ocorrencia("every 10 minutes", agora) == datetime(2026, 11, 12, 0, 0, tzinfo=TZ)


def test_duracao_segundos_minutos_horas():
    from src.scheduler import _formatar_duracao
    assert _formatar_duracao(4.3) == "4.3s"
    assert _formatar_duracao(102) == "1min 42s"
    assert _formatar_duracao(7380) == "2h 3min"
    assert _formatar_duracao(None) == "?"


def test_barra_progresso_proporcional():
    from src.scheduler import _barra_progresso
    assert _barra_progresso(0.0) == "░" * 20
    assert _barra_progresso(0.5) == "█" * 10 + "░" * 10
    assert _barra_progresso(1.0) == "█" * 20


def test_barra_progresso_limita_fora_da_faixa():
    from src.scheduler import _barra_progresso
    assert _barra_progresso(-1.0) == "░" * 20
    assert _barra_progresso(2.0) == "█" * 20

def test_painel_constroi_e_renderiza():
    import io

    from rich.console import Console

    from src.dashboard import construir_painel
    from src.scheduler import ScheduleFile

    schedule = ScheduleFile(jobs=[
        JobSpec(name="fechamento_dia", schedule="daily 05:00", queries=["q1", "q2"]),
        JobSpec(name="rapido", schedule="every 10 minutes", queries=["q3"]),
    ])
    state = {
        "fechamento_dia": {"last_success": "2026-11-11T05:02:00-03:00",
                           "last_result": "ok", "last_duration_s": 108.4},
        "rapido": {"last_result": "failed", "last_attempt": "2026-11-11T11:50:00-03:00"},
    }
    agora = datetime(2026, 11, 11, 12, 0, tzinfo=TZ)

    painel = construir_painel(schedule, state, agora)
    saida = io.StringIO()
    Console(width=140, file=saida, force_terminal=True).print(painel)
    texto = saida.getvalue()
    assert "fechamento_dia" in texto and "Próximas execuções" in texto
    assert "FALHOU" in texto and "duração: 1min 48s" in texto


def test_painel_sem_state_mostra_sem_execucao():
    import io

    from rich.console import Console

    from src.dashboard import construir_painel
    from src.scheduler import ScheduleFile

    schedule = ScheduleFile(jobs=[JobSpec(name="x", schedule="daily 05:00", queries=["q"])])
    painel = construir_painel(schedule, {}, datetime(2026, 11, 11, 12, 0, tzinfo=TZ))
    saida = io.StringIO()
    Console(width=140, file=saida, force_terminal=True).print(painel)
    assert "sem execução registrada" in saida.getvalue()

def test_painel_vivo_atende_contrato_de_renderable():
    import io

    from rich.console import Console
    from rich.panel import Panel

    from src.dashboard import PainelVivo

    saida = io.StringIO()
    Console(width=80, file=saida, force_terminal=True).print(
        PainelVivo(lambda: Panel("contador"))
    )
    assert "contador" in saida.getvalue()

def test_painel_mostra_job_em_execucao():
    import io

    from rich.console import Console

    from src.dashboard import construir_painel
    from src.scheduler import ScheduleFile

    schedule = ScheduleFile(jobs=[JobSpec(name="rapido", schedule="every 10 minutes", queries=["q1"])])
    agora = datetime(2026, 11, 11, 1, 53, 53, tzinfo=TZ)
    state = {"rapido": {"running_since": "2026-11-11T01:46:11-03:00",
                        "last_success": "2026-11-11T01:34:00-03:00",
                        "last_result": "ok"}}
    painel = construir_painel(schedule, state, agora)
    saida = io.StringIO()
    Console(width=140, file=saida, force_terminal=True).print(painel)
    assert "em execução desde 01:46" in saida.getvalue()


def test_painel_ignora_running_since_orfao():
    import io

    from rich.console import Console

    from src.dashboard import construir_painel
    from src.scheduler import ScheduleFile

    schedule = ScheduleFile(jobs=[JobSpec(name="rapido", schedule="every 10 minutes", queries=["q1"])])
    agora = datetime(2026, 11, 11, 3, 0, tzinfo=TZ)
    state = {"rapido": {"running_since": "2026-11-11T01:46:11-03:00",
                        "last_success": "2026-11-11T01:34:00-03:00",
                        "last_result": "ok"}}
    painel = construir_painel(schedule, state, agora)
    saida = io.StringIO()
    Console(width=140, file=saida, force_terminal=True).print(painel)
    assert "em execução" not in saida.getvalue()
    assert "01:34" in saida.getvalue()