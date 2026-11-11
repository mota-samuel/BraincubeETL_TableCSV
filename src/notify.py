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
    dados = json.dumps({"text": f"**{assunto}**\n\n{corpo}"}).encode("utf-8")
    requisicao = urllib.request.Request(
        webhook, data=dados, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(requisicao, timeout=15) as resposta:
        resposta.read()