"""Envia o resumo diário do radar por e-mail (Gmail). Credenciais vêm dos Secrets do GitHub."""
import json, os, smtplib, ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

PAINEL = "https://viniciusdieguez.github.io/curriculos/radar/"

COR = {"Notícias": "#1f5fd6", "CVM": "#19a15f", "BNDES": "#c98a10", "Diário municipal": "#7a4fd1", "Alerta Google": "#0e8fa0", "Vagas": "#d6453d"}

def montar(dados, top=10):
    com = [e for e in dados["empresas"] if e["score"] > 0]
    emp = com[:top]
    dt = datetime.fromisoformat(dados["atualizado_em"]).strftime("%d/%m/%Y")
    def kpi(v, t, cor):
        return (f'<td style="width:33%;padding:6px"><div style="background:#fff;border-radius:10px;border-bottom:5px solid {cor};padding:14px 6px;text-align:center">'
                f'<div style="font-size:24px;font-weight:800;color:#0b2559">{escape(str(v))}</div><div style="font-size:12px;color:#5b6b82">{escape(t)}</div></div></td>')
    kp = kpi(len(com), "empresas com sinais", "#19b36b") + kpi(sum(len(e["sinais"]) for e in com), "sinais em destaque", "#1f5fd6") + \
         kpi(f'{com[0]["score"]} pts' if com else "—", "maior pontuação", "#f5b335")
    cards = []
    for e in emp:
        sin = []
        for s in e["sinais"][:3]:
            t = escape(s["texto"]); t = f'<a href="{escape(s["link"])}" style="color:#14213d">{t}</a>' if s.get("link") else t
            c = COR.get(s["fonte"], "#5b6b82")
            sin.append(f'<div style="padding:5px 0;border-top:1px solid #dfe6f0;font-size:13px"><span style="background:{c};color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:700">{escape(s["fonte"])}</span> {t}</div>')
        cor = "#19b36b" if e is emp[0] or e["score"] >= emp[0]["score"] * .6 else "#f5b335"
        cards.append(f'<div style="background:#fff;border-radius:10px;border-top:4px solid {cor};padding:14px 16px;margin-bottom:12px">'
                     f'<table width="100%" cellspacing="0" cellpadding="0"><tr><td><div style="font-size:17px;font-weight:700;color:#14213d">{escape(e["empresa"])}</div>'
                     f'<div style="font-size:12px;color:#5b6b82">{escape(e["segmento"])} · {escape(e["cidade"])}/{escape(e["estado"])}</div></td>'
                     f'<td align="right" style="font-size:24px;font-weight:800;color:#0b2559">{e["score"]} <span style="font-size:12px;color:#5b6b82;font-weight:600">pontos</span></td></tr></table>'
                     f'{"".join(sin)}</div>')
    corpo = "".join(cards) or '<p style="color:#5b6b82">Nenhum sinal novo nas empresas monitoradas hoje.</p>'
    status = "; ".join(f"{k}: {v}" for k, v in dados.get("fontes", {}).items())
    html = (f'<div style="background:#eef2f8;padding:16px;font-family:Arial,Helvetica,sans-serif"><div style="max-width:640px;margin:0 auto">'
            f'<div style="background:#0b2559;border-radius:14px 14px 0 0;padding:26px 24px 46px">'
            f'<div style="color:#f5b335;font-size:12px;font-weight:700;letter-spacing:2px">VDM · RADAR DE OPORTUNIDADES</div>'
            f'<div style="color:#fff;font-size:28px;font-weight:800;line-height:1.15;margin-top:8px">Radar de demanda<br><span style="color:#f5b335">por terceirização</span></div>'
            f'<div style="color:#b8c8ea;font-size:13px;margin-top:8px">Resumo de {dt}</div></div>'
            f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:-30px"><tr>{kp}</tr></table>'
            f'<div style="font-size:14px;font-weight:800;letter-spacing:1px;color:#14213d;border-left:6px solid #19b36b;padding-left:10px;margin:22px 0 12px">DESTAQUES DO DIA</div>'
            f'{corpo}'
            f'<div style="background:#0b2559;border-radius:0 0 14px 14px;padding:18px 24px;text-align:center">'
            f'<a href="{PAINEL}" style="background:#f5b335;color:#0b2559;font-weight:700;text-decoration:none;border-radius:8px;padding:10px 18px;display:inline-block">Abrir o painel completo</a>'
            f'<div style="color:#b8c8ea;font-size:11px;margin-top:12px">Fontes — {escape(status)}</div></div></div></div>')
    return f"Radar de terceirização — {dt}", html

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
