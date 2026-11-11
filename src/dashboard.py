"""Painel visual do scheduler (rich): último atendimento + countdown com barras.

No modo --loop, atualizado a cada segundo via Live; no tick único, impresso
uma vez ao final. A fonte de verdade são os arquivos em disco (schedule.yaml
e scheduler_state.json) — o painel não mantém estado próprio.
"""
from __future__ import annotations

from datetime import datetime

from rich.panel import Panel
from rich.table import Table

from .scheduler import (
    ScheduleFile,
    _barra_progresso,
    _formatar_contagem,
    _formatar_duracao,
    proxima_ocorrencia,
    ultima_ocorrencia,
)


def _curto(valor: str | None) -> str:
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return "?"


def construir_painel(schedule: ScheduleFile, state: dict, agora: datetime) -> Panel:
    """Monta o painel a partir do schedule e do state carregados do disco."""
    tabela = Table.grid(padding=(0, 2))
    tabela.add_column(justify="left", no_wrap=True)
    tabela.add_column(justify="left")

    # ── Seção 1: último atendimento ──
    tabela.add_row("[bold cyan]Último atendimento[/]", "")
    for job in schedule.jobs:
        if not job.enabled:
            continue
        entrada = state.get(job.name) or {}
        if entrada.get("last_result") == "failed":
            detalhe = (
                f"[red]FALHOU[/] em {_curto(entrada.get('last_attempt'))} (retry após cooldown)"
            )
        elif entrada.get("last_success"):
            detalhe = (
                f"[green]OK[/] em {_curto(entrada.get('last_success'))} "
                f"(duração: {_formatar_duracao(entrada.get('last_duration_s'))})"
            )
        else:
            detalhe = "[dim]sem execução registrada[/]"
        tabela.add_row(job.name, detalhe)

    # ── Seção 2: próximas execuções com barras ──
    tabela.add_row("", "")
    tabela.add_row("[bold cyan]Próximas execuções[/]", "")
    for job in schedule.jobs:
        if not job.enabled:
            continue
        anterior = ultima_ocorrencia(job.schedule, agora)
        proxima = proxima_ocorrencia(job.schedule, agora)
        intervalo = (proxima - anterior).total_seconds()
        decorrido = (agora - anterior).total_seconds()
        frac = decorrido / intervalo if intervalo > 0 else 1.0
        percentual = int(round(frac * 100))
        cor = "green" if percentual >= 80 else ("yellow" if percentual >= 50 else "white")
        detalhe = (
            f"[{cor}]{_barra_progresso(frac)}[/] {percentual:>3}% — "
            f"em {_formatar_contagem(proxima - agora)} ({proxima:%d/%m %H:%M}) — "
            f"{len(job.queries)} query(s): {', '.join(job.queries)}"
        )
        tabela.add_row(job.name, detalhe)

    return Panel(
        tabela,
        title=f"Braincube ETL — monitor — {agora:%d/%m/%Y %H:%M:%S}",
        border_style="cyan",
    )

class PainelVivo:
    """Renderable dinâmico para o Live: cada atualização reconstrói o painel
    a partir do disco (schedule.yaml + scheduler_state.json)."""

    def __init__(self, construir):
        self._construir = construir

    def __rich_console__(self, console, options):
        yield self._construir()