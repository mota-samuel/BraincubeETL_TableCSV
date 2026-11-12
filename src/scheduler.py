"""Orquestrador central (Modelo B): avalia o que está vencido, executa, notifica.
Frequências centralizadas em config/schedule.yaml; estado em data/state/.
Modos:
  python -m src.scheduler                # 1 tick: avalia vencidos, executa, sai (recomendado)
  python -m src.scheduler --loop         # processo permanente (tick a cada --interval segundos)

Notificações:
  - falha imediata: e-mail no momento da falha (notify_on: failure no YAML);
  - resumo diário: um único e-mail consolidado por dia, após notify.digest_time
    (ex.: "18:00"), com as execuções registradas em data/execucoes.jsonl.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from .compose import resolver_query
from .config import PROJECT_ROOT, Settings
from .notify import NotifySpec, enviar_resumo, enviar_resumo_diario  # [ALTERADO] + enviar_resumo_diario
from .pipeline import run_query

log = logging.getLogger(__name__)

EXEC_LOG = Path("data/execucoes.jsonl")
SCHEDULE_PADRAO = PROJECT_ROOT / "config" / "schedule.yaml"
DIAS_SEMANA = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class JobSpec(BaseModel):
    name: str
    schedule: str  # "daily HH:MM" | "weekly <mon..sun> HH:MM" | "every <N> minutes"
    queries: list[str]
    enabled: bool = True


class ScheduleFile(BaseModel):
    retry_cooldown_minutes: int = 30
    jobs: list[JobSpec] = Field(default_factory=list)
    notify: NotifySpec = Field(default_factory=NotifySpec)

    @classmethod
    def load(cls, path: Path) -> "ScheduleFile":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(**raw)


def registrar_execucao(job: str, status: str, duracao_s: float, linhas, erro: str | None):
    reg = {"ts": datetime.now().isoformat(timespec="seconds"), "hora": datetime.now().strftime("%H:%M"),
           "job": job, "status": status, "duracao_s": duracao_s, "linhas": linhas, "erro": erro}
    EXEC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EXEC_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def execucoes_do_dia(hoje: str) -> list[dict]:
    if not EXEC_LOG.exists():
        return []
    out = []
    for linha in EXEC_LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(linha)
            if r.get("ts", "").startswith(hoje):
                out.append(r)
        except json.JSONDecodeError:
            continue
    return out


# [NOVO] Resumo diário ---------------------------------------------------------


def verificar_resumo_diario(spec: NotifySpec, state: dict, state_path: Path, agora: datetime) -> None:
    """Envia uma única vez por dia o consolidado das execuções do dia.

    Independente de notify_on (sai mesmo com notify_on: failure).
    digest_time ausente/vazio desativa. Se o envio falhar, tenta de novo no
    próximo tick (não marca como enviado).
    """
    if not getattr(spec, "digest_time", None):
        return
    try:
        hh, mm = map(int, str(spec.digest_time).split(":"))
    except ValueError:
        log.error("digest_time inválido (%r) — resumo diário desativado", spec.digest_time)
        return
    hoje = agora.strftime("%Y-%m-%d")
    alvo = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if agora < alvo or state.get("_digest", {}).get("last_digest") == hoje:
        return
    execs = execucoes_do_dia(hoje)
    if not execs:
        log.info("Resumo diário: nenhuma execução hoje — nada a enviar")
    else:
        try:
            enviar_resumo_diario(spec, execs, agora)
        except Exception:
            log.exception("Falha ao enviar o resumo diário — nova tentativa no próximo tick")
            return
    state["_digest"] = {"last_digest": hoje}
    _salvar_state(state_path, state)


# ---------------------------------------------------------------- fim do novo --


def _parse_schedule(spec: str) -> tuple[str, int | None, int, int]:
    """Retorna (tipo, referencia, hh, mm).
    daily  -> ref=None, hh/mm do horário
    weekly -> ref=weekday (0=segunda), hh/mm
    every  -> ref=intervalo em minutos (hh/mm não usados)
    """
    partes = spec.split()
    if len(partes) == 2 and partes[0] == "daily":
        hh, mm = partes[1].split(":")
        return "daily", None, int(hh), int(mm)
    if len(partes) == 3 and partes[0] == "weekly":
        dia_semana = DIAS_SEMANA.get(partes[1].lower())
        if dia_semana is None:
            raise ValueError(f"dia inválido no schedule: {spec}")
        hh, mm = partes[2].split(":")
        return "weekly", dia_semana, int(hh), int(mm)
    if len(partes) == 3 and partes[0] == "every" and partes[2] == "minutes":
        intervalo = int(partes[1])
        if intervalo < 1:
            raise ValueError(f"intervalo inválido: {spec!r} (minutos >= 1)")
        return "every", intervalo, 0, 0
    raise ValueError(
        f"schedule não suportado: {spec!r} "
        "(use 'daily HH:MM', 'weekly <dia> HH:MM' ou 'every <N> minutes')"
    )


def ultima_ocorrencia(spec: str, agora: datetime) -> datetime:
    """Ocorrência agendada mais recente (<= agora), no fuso do settings."""
    tipo, ref, hh, mm = _parse_schedule(spec)
    if tipo == "every":
        # Marcas fixas de relógio ancoradas na meia-noite: 00:00, 00:N, 00:2N...
        minutos_dia = agora.hour * 60 + agora.minute
        marca = (minutos_dia // ref) * ref
        return agora.replace(hour=marca // 60, minute=marca % 60, second=0, microsecond=0)
    candidato = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if tipo == "daily":
        if candidato > agora:
            candidato -= timedelta(days=1)
        return candidato
    while candidato.weekday() != ref or candidato > agora:
        candidato -= timedelta(days=1)
    return candidato


def _parse_dt(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def proxima_ocorrencia(spec: str, agora: datetime) -> datetime:
    """Próxima ocorrência agendada (> agora), no fuso do settings."""
    tipo, ref, hh, mm = _parse_schedule(spec)
    if tipo == "every":
        minutos_dia = agora.hour * 60 + agora.minute
        proxima_marca = ((minutos_dia // ref) + 1) * ref
        if proxima_marca >= 24 * 60:
            # virou o dia: a primeira marca do dia seguinte é 00:00
            return (agora + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        return agora.replace(
            hour=proxima_marca // 60, minute=proxima_marca % 60,
            second=0, microsecond=0,
        )
    candidato = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if tipo == "daily":
        if candidato <= agora:
            candidato += timedelta(days=1)
        return candidato
    while candidato.weekday() != ref or candidato <= agora:
        candidato += timedelta(days=1)
    return candidato


def _formatar_contagem(delta: timedelta) -> str:
    """Delta positivo em texto humano: '3min', '2h 13min', '4d 15h'."""
    total_seg = max(int(delta.total_seconds()), 0)
    dias, resto = divmod(total_seg, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, _ = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas or dias:
        partes.append(f"{horas}h")
    partes.append(f"{minutos}min")
    return " ".join(partes)


def _formatar_duracao(segundos: float | None) -> str:
    """Duração de execução em texto: '4.3s', '1min 42s', '2h 3min'."""
    if segundos is None:
        return "?"
    if segundos < 60:
        return f"{segundos:.1f}s"
    minutos, resto = divmod(int(segundos), 60)
    if minutos < 60:
        return f"{minutos}min {resto}s"
    horas, minutos = divmod(minutos, 60)
    return f"{horas}h {minutos}min"


def _barra_progresso(frac: float, largura: int = 20) -> str:
    """Barra ASCII/Unicode proporcional ao intervalo já decorrido."""
    frac = min(max(frac, 0.0), 1.0)
    cheios = int(round(frac * largura))
    return "█" * cheios + "░" * (largura - cheios)


def _vencido(job: JobSpec, state: dict, agora: datetime, cooldown_min: int) -> tuple[bool, str]:
    entrada = state.get(job.name) or {}
    ultimo_sucesso = _parse_dt(entrada.get("last_success"))
    ultima_tentativa = _parse_dt(entrada.get("last_attempt"))
    ocorrencia = ultima_ocorrencia(job.schedule, agora)
    if ultimo_sucesso is None or ultimo_sucesso < ocorrencia:
        if entrada.get("last_result") == "failed" and ultima_tentativa is not None:
            if agora - ultima_tentativa < timedelta(minutes=cooldown_min):
                return False, "falhou há pouco; aguardando cooldown de retry"
        return True, f"ocorrência {ocorrencia:%d/%m %H:%M} ainda não atendida"
    return False, f"atendido em {_parse_dt(entrada.get('last_success')):%d/%m %H:%M}"


def _carregar_state(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        log.warning("state corrompido, recomeçando vazio: %s", caminho)
        return {}


def _salvar_state(caminho: Path, state: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)


def executar_job(job: JobSpec, settings: Settings) -> list[dict]:
    """Executa as queries em sequência; falha de uma não interrompe as demais."""
    resultados = []
    for nome in job.queries:
        item = {"consulta": nome, "status": "ok", "linhas": None, "duracao_s": None, "erro": None}
        inicio = datetime.now()
        try:
            resultado = run_query(resolver_query(nome), settings)
            item["linhas"] = resultado.get("linhas")
        except Exception as erro:
            item["status"] = "erro"
            item["erro"] = f"{type(erro).__name__}: {erro}"
            log.exception("Consulta %s falhou no job %s", nome, job.name)
        item["duracao_s"] = round((datetime.now() - inicio).total_seconds(), 1)
        resultados.append(item)
    return resultados


def _tentar_lock(caminho: Path):
    """Impede dois ticks simultâneos; recicla lock órfão de crash (>1h)."""
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        return open(caminho, "x", encoding="utf-8")
    except FileExistsError:
        try:
            if time.time() - caminho.stat().st_mtime > 3600:
                caminho.unlink()
                return open(caminho, "x", encoding="utf-8")
        except OSError:
            return None
        return None


def run_tick(settings: Settings, schedule_path: Path | None = None) -> dict:
    schedule = ScheduleFile.load(schedule_path or SCHEDULE_PADRAO)
    agora = datetime.now(ZoneInfo(settings.timezone))
    state_path = Path(settings.data_dir) / "state" / "scheduler_state.json"
    lock_path = Path(settings.data_dir) / "state" / "scheduler.lock"
    lock = _tentar_lock(lock_path)
    if lock is None:
        log.info("Tick anterior ainda em execução; saindo sem processar")
        return {"agora": agora.isoformat(), "jobs": [], "tick_simultaneo": True}
    try:
        state = _carregar_state(state_path)
        resumo = {"agora": agora.isoformat(), "jobs": []}
        for job in schedule.jobs:
            if not job.enabled:
                continue
            deve, motivo = _vencido(job, state, agora, schedule.retry_cooldown_minutes)
            log.info("Job %s: %s", job.name, motivo)
            if not deve:
                continue
            inicio = datetime.now(agora.tzinfo)
            em_curso = state.get(job.name) or {}
            em_curso["running_since"] = inicio.isoformat()
            state[job.name] = em_curso
            _salvar_state(state_path, state)
            resultados = executar_job(job, settings)
            falhou = any(r["status"] != "ok" for r in resultados)
            duracao_total = round((datetime.now(agora.tzinfo) - inicio).total_seconds(), 1)
            anterior = state.get(job.name) or {}
            state[job.name] = {
                "last_attempt": agora.isoformat(),
                # Na falha, preserva o último sucesso: o job volta a ser due no próximo tick
                "last_success": anterior.get("last_success") if falhou else agora.isoformat(),
                "last_result": "failed" if falhou else "ok",
                "last_error": next((r["erro"] for r in resultados if r["erro"]), None),
                "last_duration_s": duracao_total,
            }
            _salvar_state(state_path, state)

            # [NOVO] registra a execução — base do resumo diário
            registrar_execucao(
                job.name,
                "falha" if falhou else "ok",
                duracao_total,
                sum(int(r.get("linhas") or 0) for r in resultados),
                next((r["erro"] for r in resultados if r["erro"]), None),
            )

            # [ALTERADO] e-mail imediato: sempre em falha; em sucesso, só com notify_on: always
            notify_on = getattr(schedule.notify, "notify_on", None) or "always"
            if notify_on == "always" or (notify_on == "failure" and falhou):
                enviar_resumo(schedule.notify, job.name, resultados, inicio)

            resumo["jobs"].append({"job": job.name, "falhou": falhou, "resultados": resultados})

        # [NOVO] resumo diário — uma vez por dia, independente de notify_on
        verificar_resumo_diario(schedule.notify, state, state_path, agora)

        return resumo
    finally:
        lock.close()
        lock_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="braincube-scheduler")
    parser.add_argument("--schedule", default=str(SCHEDULE_PADRAO))
    parser.add_argument("--settings", default=None)
    parser.add_argument("--loop", action="store_true", help="processo permanente")
    parser.add_argument("--interval", type=int, default=300, help="segundos entre ticks no --loop")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--sem-painel", action="store_true", help="desativa o painel vivo (só logs)")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings) if args.settings else PROJECT_ROOT / "config" / "settings.yaml"
    settings = Settings.load(settings_path)

    if not args.loop:
        from . import logging_setup
        logging_setup.setup(getattr(logging, args.log_level.upper(), logging.INFO))
        resumo = run_tick(settings, Path(args.schedule))
        from rich.console import Console
        from .dashboard import construir_painel
        schedule = ScheduleFile.load(Path(args.schedule))
        state = _carregar_state(Path(settings.data_dir) / "state" / "scheduler_state.json")
        agora = datetime.now(ZoneInfo(settings.timezone))
        Console().print(construir_painel(schedule, state, agora))
        return 1 if any(j["falhou"] for j in resumo["jobs"]) else 0

    if args.sem_painel:
        from . import logging_setup
        logging_setup.setup(getattr(logging, args.log_level.upper(), logging.INFO))
        log.info("Loop permanente iniciado sem painel (intervalo %ss)", args.interval)
        while True:
            try:
                run_tick(settings, Path(args.schedule))
            except Exception:
                log.exception("Tick falhou; continuando no próximo intervalo")
            time.sleep(args.interval)
        return 0

    # ── Loop com painel vivo ──
    from rich.console import Console
    from rich.live import Live
    from rich.logging import RichHandler
    from rich.text import Text
    from .dashboard import PainelVivo, construir_painel

    console = Console()
    state_path = Path(settings.data_dir) / "state" / "scheduler_state.json"

    def refrescar():
        """Reconstrói o painel lendo schedule + state do disco."""
        try:
            schedule = ScheduleFile.load(Path(args.schedule))
            state = _carregar_state(state_path)
            agora = datetime.now(ZoneInfo(settings.timezone))
            return construir_painel(schedule, state, agora)
        except Exception as erro:
            return Text(f"Painel indisponível: {erro}", style="red")

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="%d/%m %H:%M:%S",
        handlers=[RichHandler(console=console, show_time=True, show_level=True, show_path=False)],
    )
    log.info("Loop permanente iniciado (intervalo %ss)", args.interval)
    try:
        with Live(PainelVivo(refrescar), console=console, refresh_per_second=1):
            while True:
                try:
                    run_tick(settings, Path(args.schedule))
                except Exception:
                    log.exception("Tick falhou; continuando no próximo intervalo")
                time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário")
    return 0


if __name__ == "__main__":
    sys.exit(main())