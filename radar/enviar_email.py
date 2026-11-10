"""Envia o resumo diário do radar por e-mail (Gmail). Credenciais vêm dos Secrets do GitHub."""
import json, os, smtplib, ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

PAINEL = "https://viniciusdieguez.github.io/curriculos/radar/"

def montar(dados, top=10):
    emp = [e for e in dados["empresas"] if e["score"] > 0][:top]
    dt = datetime.fromisoformat(dados["atualizado_em"]).strftime("%d/%m/%Y")
    html = [f"<h2>Radar de terceirização — {dt}</h2>"]
    if not emp:
        html.append("<p>Nenhum sinal novo nas empresas monitoradas hoje.</p>")
    for e in emp:
        html.append(f"<p><b>{escape(e['empresa'])}</b> — {e['score']} pontos<br>"
                    f"<small>{escape(e['segmento'])} · {escape(e['cidade'])}/{escape(e['estado'])}</small></p><ul>")
        for s in e["sinais"][:3]:
            t = escape(s["texto"]); t = f'<a href="{escape(s["link"])}">{t}</a>' if s.get("link") else t
            html.append(f"<li>[{escape(s['fonte'])}] {t}</li>")
        html.append("</ul>")
    status = "; ".join(f"{k}: {v}" for k, v in dados.get("fontes", {}).items())
    html.append(f'<p><a href="{PAINEL}">Abrir o painel completo</a></p><p><small>Fontes — {escape(status)}</small></p>')
    return f"Radar de terceirização — {dt}", "\n".join(html)

def main():
    user, senha, destino = (os.environ.get(k, "").strip() for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "EMAIL_DESTINO"))
    if not (user and senha and destino):
        print("Secrets de e-mail não configurados; envio ignorado."); return
    dados = json.loads((Path(__file__).parent / "data.json").read_text(encoding="utf-8"))
    assunto, corpo = montar(dados)
    m = EmailMessage(); m["Subject"] = assunto; m["From"] = user; m["To"] = destino
    m.set_content("Abra este e-mail em um leitor que exiba HTML ou acesse " + PAINEL)
    m.add_alternative(corpo, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, senha.replace(" ", "")); s.send_message(m)
    print("E-mail enviado.")

if __name__ == "__main__":
    main()
