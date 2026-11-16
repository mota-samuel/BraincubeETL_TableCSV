"""Notificação do resumo de execução: SMTP e/ou webhook do Teams (opcionais)."""
from __future__ import annotations

import html
import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

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


# --- Alerta imediato (texto puro) -------------------------------------------


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


# --- Resumo diário: texto (fallback) ----------------------------------------


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


# --- Resumo diário: HTML com logos ------------------------------------------

ASSETS_EMAIL = Path(__file__).resolve().parent.parent / "assets" / "email"

# (cid usado no HTML, arquivo). Esquerda = empresa, direita = equipe.
LOGO_ESQUERDA = ("logo_empresa", ASSETS_EMAIL / "logo_empresa.png")
LOGO_DIREITA = ("logo_equipe", ASSETS_EMAIL / "logo_grupo.png")
LOGOS_EMAIL = [LOGO_ESQUERDA, LOGO_DIREITA]

# Estilos inline: clientes de e-mail (Outlook, Gmail) ignoram <style> e classes CSS
_TH = ("padding:8px 10px;background:#1f3b57;color:#ffffff;text-align:left;"
       "font-size:13px;font-family:Arial,sans-serif;")
_TD = ("padding:8px 10px;border-bottom:1px solid #e3e8ee;font-size:13px;"
       "font-family:Arial,sans-serif;vertical-align:top;")


def _badge_status(status: str) -> str:
    cores = {"ok": ("#e6f4ea", "#1e7e34"), "falha": ("#fdecea", "#b3261e")}
    fundo, texto = cores.get(status, ("#eef1f4", "#44546a"))
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            f'background:{fundo};color:{texto};font-weight:bold;font-size:12px;">'
            f'{html.escape(str(status))}</span>')


def _card(rotulo: str, valor: int, cor: str) -> str:
    return (f'<td style="padding:12px 18px;background:#f5f7fa;border-left:4px solid {cor};'
            f'font-family:Arial,sans-serif;">'
            f'<div style="font-size:12px;color:#5b6b7c;">{rotulo}</div>'
            f'<div style="font-size:22px;font-weight:bold;color:{cor};">{valor}</div></td>')


def _img_logo(cid: str, alinhamento: str) -> str:
    return (
        f'<img src="cid:{cid}" width="130" alt="Logo" '
        f'style="display:block;border:0;outline:none;height:auto;" align="{alinhamento}">'
    )


def _cabecalho(agora: datetime) -> str:
    """Logo da empresa à esquerda, título e data no centro, logo da equipe à direita."""
    data = agora.strftime("%d/%m/%Y")
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border-bottom:1px solid #e3e8ee;margin-bottom:18px;">'
        "<tr>"
        '<td width="30%" style="padding:0 0 14px 0;vertical-align:middle;text-align:left;">'
        f'{_img_logo(LOGO_ESQUERDA[0], "left")}</td>'
        '<td width="40%" style="padding:0 0 14px 0;vertical-align:middle;text-align:center;'
        'font-family:Arial,sans-serif;">'
        '<div style="font-size:20px;font-weight:bold;color:#1f3b57;">Resumo das execuções</div>'
        f'<div style="font-size:13px;color:#5b6b7c;margin-top:4px;">{data}</div>'
        "</td>"
        '<td width="30%" style="padding:0 0 14px 0;vertical-align:middle;text-align:right;">'
        f'{_img_logo(LOGO_DIREITA[0], "right")}</td>'
        "</tr></table>"
    )


def _rodape() -> str:
    return (
        '<div style="margin-top:18px;font-size:11px;color:#9aa6b2;font-family:Arial,sans-serif;">'
        "Mensagem automática do ETL Braincube · Desenvolvido por Samuel Mota"
        "</div>"
    )


def _html_resumo_diario(execucoes: list[dict], agora: datetime) -> str:
    ok = sum(1 for e in execucoes if e.get("status") == "ok")
    falhas = len(execucoes) - ok

    linhas = []
    for e in execucoes:
        dur = float(e.get("duracao_s") or 0)
        erro = html.escape(_truncar(e.get("erro"), 300)) or "—"
        linhas.append(
            "<tr>"
            f'<td style="{_TD}">{html.escape(str(e.get("hora", "-")))}</td>'
            f'<td style="{_TD}">{html.escape(str(e.get("job", "-")))}</td>'
            f'<td style="{_TD}">{_badge_status(e.get("status", "-"))}</td>'
            f'<td style="{_TD}" align="right">{dur:.1f}s</td>'
            f'<td style="{_TD}" align="right">{html.escape(str(e.get("linhas", "-")))}</td>'
            f'<td style="{_TD}color:#b3261e;">{erro}</td>'
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:20px;background:#ffffff;font-family:Arial,sans-serif;color:#1d2733;">
  {_cabecalho(agora)}

  <table role="presentation" cellspacing="8" cellpadding="0" style="margin-bottom:16px;">
    <tr>
      {_card("Total", len(execucoes), "#1f3b57")}
      {_card("OK", ok, "#1e7e34")}
      {_card("Falhas", falhas, "#b3261e")}
    </tr>
  </table>

  <table role="presentation" cellspacing="0" cellpadding="0" width="100%"
         style="border-collapse:collapse;border:1px solid #e3e8ee;">
    <thead>
      <tr>
        <th style="{_TH}">Hora</th>
        <th style="{_TH}">Job</th>
        <th style="{_TH}">Status</th>
        <th style="{_TH}" align="right">Duração</th>
        <th style="{_TH}" align="right">Linhas</th>
        <th style="{_TH}">Erro</th>
      </tr>
    </thead>
    <tbody>
      {''.join(linhas)}
    </tbody>
  </table>

  {_rodape()}
</body></html>"""


def _enviar_html(spec: NotifySpec, assunto: str, corpo_html: str, corpo_texto: str) -> None:
    """multipart/related (HTML + logos inline) contendo multipart/alternative (HTML + texto)."""
    senha = os.environ.get("SMTP_PASSWORD")
    if not senha:
        raise RuntimeError("SMTP_PASSWORD ausente no ambiente")

    remetente = spec.mail_from or spec.mail_user or ""
    msg = MIMEMultipart("related")
    msg["Subject"] = Header(assunto, "utf-8")
    msg["From"] = remetente
    msg["To"] = ", ".join(spec.mail_to)

    alternativa = MIMEMultipart("alternative")
    alternativa.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    alternativa.attach(MIMEText(corpo_html, "html", "utf-8"))
    msg.attach(alternativa)

    for cid, caminho in LOGOS_EMAIL:
        if not caminho.exists():
            log.warning("Logo não encontrada, e-mail segue sem ela: %s", caminho)
            continue
        ext = caminho.suffix.lower()
        subtipo = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
        img = MIMEImage(caminho.read_bytes(), _subtype=subtipo)
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=caminho.name)
        msg.attach(img)

    host, _, porta = (spec.mail_smtp or "").partition(":")
    with smtplib.SMTP(host, int(porta or 587), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(spec.mail_user, senha)
        smtp.sendmail(remetente, spec.mail_to, msg.as_string())


def enviar_resumo_diario(spec: NotifySpec, execucoes: list[dict], agora: datetime) -> None:
    """Consolidado do dia em HTML (com fallback em texto). Sem execuções, não envia."""
    if not execucoes:
        return
    ok = sum(1 for e in execucoes if e.get("status") == "ok")
    falhas = len(execucoes) - ok
    assunto = (f"[ETL Braincube] Resumo diário {agora.strftime('%d/%m')} — "
               f"{len(execucoes)} exec. ({ok} OK / {falhas} falha(s))")
    _enviar_html(spec, assunto,
                 _html_resumo_diario(execucoes, agora),
                 _corpo_resumo_diario(execucoes, agora))