"""Notificação do resumo de execução: SMTP e/ou webhook do Teams (opcionais)."""
from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class NotifySpec(BaseModel):
    mail_smtp: str | None = None  # "host:porta"
    mail_user: str | None = None
    mail_from: str | None = None
    mail_to: list[str] = Field(default_factory=list)
    teams_webhook: str | None = None
    notify_on: str = "always"  # always | failure | never
    digest_time: str | None = None  # "18:00" — None/vazio desativa o resumo


def enviar_resumo(spec: NotifySpec, job: str, resultados: list[dict], inicio: datetime) -> None:
    """Nunca levanta exceção: falha de notificação não pode derrubar o tick."""
    falhou = any(r["status"] != "ok" for r in resultados)
    if spec.notify_on == "never" or (spec.notify_on == "failure" and not falhou):
        return

    assunto = f"[ETL Braincube] {job}: {'FALHA' if falhou else 'OK'}"
    linhas = []
    for r in resultados:
        marca = "OK " if r["status"] == "ok" else "ERRO"
        linha = f"{marca} {r['consulta']} ({r['duracao_s']}s"
        if r["linhas"] is not None:
            linha += f", {r['linhas']} linhas"
        linha += ")"
        if r["erro"]:
            linha += f"\n     {r['erro']}"
        linhas.append(linha)
    corpo = f"Job: {job}\nInício: {inicio:%d/%m/%Y %H:%M:%S}\n\n" + "\n".join(linhas)

    if spec.mail_smtp and spec.mail_to:
        try:
            _enviar_email(spec, assunto, corpo)
        except Exception:
            log.exception("Falha ao enviar e-mail do resumo")
    if spec.teams_webhook:
        try:
            _enviar_teams(spec.teams_webhook, assunto, corpo)
        except Exception:
            log.exception("Falha ao enviar webhook do Teams")


def _enviar_email(spec: NotifySpec, assunto: str, corpo: str) -> None:
    host, _, porta = (spec.mail_smtp or "").partition(":")
    senha = os.environ.get("SMTP_PASSWORD")  # nunca em YAML
    mensagem = MIMEText(corpo, "plain", "utf-8")
    mensagem["Subject"] = assunto
    mensagem["From"] = spec.mail_from or spec.mail_user or ""
    mensagem["To"] = ", ".join(spec.mail_to)
    with smtplib.SMTP(host, int(porta or 587), timeout=30) as smtp:
        try:
            smtp.starttls()
        except smtplib.SMTPException:
            log.info("SMTP sem STARTTLS; seguindo sem criptografia")
        if spec.mail_user and senha:
            smtp.login(spec.mail_user, senha)
        smtp.sendmail(mensagem["From"], spec.mail_to, mensagem.as_string())


def _enviar_teams(webhook: str, assunto: str, corpo: str) -> None:
    cartao = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": assunto, "weight": "Bolder", "size": "Medium"},
                    {"type": "TextBlock", "text": corpo, "wrap": True},
                ],
            },
        }],
    }
    dados = json.dumps(cartao).encode("utf-8")
    requisicao = urllib.request.Request(
        webhook, data=dados, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(requisicao, timeout=15) as resposta:
        resposta.read()

# --- Resumo diário ----------------------------------------------------------

def _truncar(txt: str | None, n: int = 200) -> str:
    txt = (txt or "").replace("\n", " ").strip()
    return txt if len(txt) <= n else txt[: n - 3] + "..."


def _corpo_resumo_diario(execucoes: list[dict], agora: datetime) -> str:
    ok = sum(1 for e in execucoes if e.get("status") == "ok")
    falhas = len(execucoes) - ok
    linhas = [
        f"Resumo das execuções de {agora.strftime('%d/%m/%Y')}",
        f"Total: {len(execucoes)} | OK: {ok} | Falhas: {falhas}",
        "",
        "hora   | job               | status | duração | linhas | erro",
    ]
    for e in execucoes:
        linhas.append(
            f"{e.get('hora', '-'):6} | {e.get('job', '-'):17} | "
            f"{e.get('status', '-'):6} | {e.get('duracao_s', 0):7.1f}s | "
            f"{str(e.get('linhas', '-')):>6} | {_truncar(e.get('erro'))}"
        )
    return "\n".join(linhas)


def enviar_resumo_diario(spec: "NotifySpec", execucoes: list[dict], agora: datetime) -> None:
    """Consolidado do dia. Sem execuções, não envia nada."""
    if not execucoes:
        return
    ok = sum(1 for e in execucoes if e.get("status") == "ok")
    falhas = len(execucoes) - ok
    assunto = (f"[ETL Braincube] Resumo diário {agora.strftime('%d/%m')} — "
               f"{len(execucoes)} exec. ({ok} OK / {falhas} falha(s))")
    _enviar_email(spec, assunto, _corpo_resumo_diario(execucoes, agora))