"""Radar de demanda por terceirização: reúne sinais públicos por empresa e grava data.json."""
import csv, io, json, re, time, unicodedata, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

AQUI = Path(__file__).parent
HOJE = datetime.now(timezone.utc)
PESOS = [("nova fábrica",3),("nova unidade",3),("ampliação",3),("expansão",3),("novo turno",3),
         ("contrata",3),("vagas",3),("empregos",3),("terceiriz",4),("investimento",2),("investirá",2),
         ("greve",2),("demiss",2),("paralisação",2),("licitação",1),("licença ambiental",3),
         ("licenciamento",2),("bndes",3),("financiamento",2),("reestrutura",2),("flexibiliza",2),
         ("custos fixos",2),("acordo coletivo",2),("convenção coletiva",2),("condena",2),("responsabilidade subsidiária",2),("sindicato",1),("eficiência operacional",1)]
ALIASES = {"MBRF":["MARFRIG","BRF"],"CSN":["COMPANHIA SIDERURGICA NACIONAL"],"CBA":["COMPANHIA BRASILEIRA DE ALUMINIO"],
           "Usiminas":["USINAS SIDERURGICAS DE MINAS GERAIS"],"Motiva":["CCR"],"Dexco":["DURATEX"],"Vale":[]}
Q1 = '(expansão OR "nova fábrica" OR "nova unidade" OR contratação OR vagas OR terceirização OR investimento OR greve OR demissões)'
Q3 = '("acordo coletivo" OR "convenção coletiva" OR condenada OR "responsabilidade subsidiária" OR terceirizados OR sindicato)'
Q2 = '("licença ambiental" OR BNDES OR financiamento OR reestruturação OR flexibilização OR "custos fixos")'

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()

def nome_busca(nome): return re.split(r"\s[|\-]\s", nome)[0].strip()
def pontuar(t): t = (t or "").lower(); return sum(p for k, p in PESOS if k in t)
def termos(e): b = nome_busca(e["empresa"]); return [norm(x) for x in [b] + ALIASES.get(b, [])]
def casa(denom, ts): d = norm(denom); return any(re.search(rf"\b{re.escape(t)}\b", d) for t in ts)
def baixar(url, t=180):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 radar-vdm"}), timeout=t).read()
def sinal(fonte, texto, link, data, pontos): return {"fonte": fonte, "texto": texto, "link": link, "data": data, "pontos": pontos}
def data_iso(s):
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(s.strip()[:19], f).replace(tzinfo=timezone.utc)
        except Exception: pass

import html as _html
AVISOS = {}
def sem_tags(t): return re.sub(r"<[^>]+>", "", _html.unescape(t or "")).strip()
def unicos(sinais):
    vistos, out = set(), []
    for s in sinais:
        k = norm(s["texto"].rsplit(" - ", 1)[0])
        if k not in vistos: vistos.add(k); out.append(s)
    return out

# 1) Notícias (Google News RSS)
def noticias_parse(xml, termo, dias=30):
    lim = HOJE - timedelta(days=dias); out = []
    for it in ET.fromstring(xml).iter("item"):
        t = (it.findtext("title") or "").strip()
        if termo.lower() not in t.lower(): continue
        try: d = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception: continue
        if d >= lim and pontuar(t): out.append(sinal("Notícias", t, it.findtext("link"), d.date().isoformat(), pontuar(t)))
    return out

def noticias(termo):
    out = []
    for q in (Q1, Q2, Q3):
        u = "https://news.google.com/rss/search?q=" + urllib.parse.quote(f'"{termo}" {q} when:30d') + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        out += noticias_parse(baixar(u, 30).decode("utf-8"), termo); time.sleep(1.5)
    return unicos(out)

# 2) CVM: fatos relevantes e comunicados (dados abertos IPE)
def cvm_fatos(zbytes, empresas, dias=90):
    z = zipfile.ZipFile(io.BytesIO(zbytes)); nome = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    lim = HOJE - timedelta(days=dias); res = {}
    for r in csv.DictReader(io.TextIOWrapper(z.open(nome), encoding="latin-1"), delimiter=";"):
        txt = f'{r.get("Categoria","")} {r.get("Assunto","")}'; p = pontuar(txt); d = data_iso(r.get("Data_Entrega", ""))
        if not p or not d or d < lim: continue
        for e in empresas:
            if casa(r.get("Nome_Companhia", ""), termos(e)):
                res.setdefault(e["empresa"], []).append(sinal("CVM", f'{r.get("Categoria","")}: {r.get("Assunto","")}', r.get("Link_Download"), d.date().isoformat(), p))
    return res

# 3) CVM: terceirizados declarados no Formulário de Referência
def fre_zip(ano):
    for a in (ano, ano - 1):
        try: return baixar(f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{a}.zip")
        except Exception: pass
    raise ValueError("zip do Formulário de Referência indisponível")

def cvm_terceirizados(zbytes, empresas):
    z = zipfile.ZipFile(io.BytesIO(zbytes)); docs = {}; diag = []
    base = {"CNPJ_Companhia", "Data_Referencia", "Versao", "ID_Documento", "Nome_Companhia"}
    for n in z.namelist():
        if "empregado" not in n.lower() or not n.lower().endswith(".csv"): continue
        rd = csv.DictReader(io.TextIOWrapper(z.open(n), encoding="latin-1"), delimiter=";")
        diag.append(n.replace("fre_cia_aberta_", "").rsplit("_", 1)[0] + str([c for c in (rd.fieldnames or []) if c not in base][:5]))
        for r in rd:
            den = r.get("Nome_Companhia") or ""
            ct = [c for c in r if c and "TERCEIR" in c.upper()]
            if ct: vals = [r[c] for c in ct]
            elif any("TERCEIR" in (v or "").upper() for v in r.values()):
                vals = [r[c] for c in r if c and c.upper().startswith(("QUANT", "QTD", "NUM"))]
            else: continue
            soma = 0
            for v in vals:
                try: soma += int(float((v or "").replace(",", ".")))
                except ValueError: pass
            if den and soma:
                k = (den, int(r.get("ID_Documento") or 0)); docs[k] = docs.get(k, 0) + soma
    if not docs: raise ValueError("sem dados de terceirizados; arquivos: " + "; ".join(diag))
    res = {}
    for e in empresas:
        c = [(i, v, d) for (d, i), v in docs.items() if casa(d, termos(e)) and v > 0]
        if c:
            _, v, _ = max(c); res[e["empresa"]] = [sinal("CVM", f"Formulário de Referência declara {v:,} terceirizados".replace(",", "."), None, None, 4 if v >= 1000 else 2)]
    return res

# 4) BNDES: financiamentos contratados nos últimos 12 meses (dados abertos)
def bndes(empresas, meses=12):
    pk = json.loads(baixar("https://dadosabertos.bndes.gov.br/api/3/action/package_show?id=operacoes-financiamento", 60))
    lim = HOJE - timedelta(days=30 * meses); res = {}; cols = []; com_data = recentes = 0
    for rs in pk["result"]["resources"]:
        if "csv" not in (rs.get("format", "") + rs.get("url", "")).lower(): continue
        try:
            resp = urllib.request.urlopen(urllib.request.Request(rs["url"], headers={"User-Agent": "Mozilla/5.0 radar-vdm"}), timeout=120)
            for r in csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8-sig", errors="replace")):
                r = {norm(k).lower().replace(" ", "_"): v for k, v in r.items() if k}
                if not cols: cols = list(r)[:14]
                d = data_iso(r.get("data_da_contratacao") or r.get("data_contratacao") or "")
                if not d: continue
                com_data += 1
                if d < lim: continue
                recentes += 1
                cli = r.get("cliente") or r.get("nome_cliente") or ""
                for e in empresas:
                    if casa(cli, termos(e)):
                        proj = (r.get("descricao_projeto") or r.get("projeto") or "financiamento").strip()[:100]
                        res.setdefault(e["empresa"], []).append(sinal("BNDES", f"Financiamento contratado: {proj}", None, d.date().isoformat(), 3))
        except Exception as ex:
            AVISOS["BNDES"] = "download interrompido, dados parciais"; print("BNDES parcial:", ex)
    if not com_data: raise ValueError(f"nenhuma data legível; colunas={cols}")
    AVISOS.setdefault("BNDES", f"{recentes} contratos dos últimos {meses} meses lidos")
    return {k: unicos(v) for k, v in res.items()}

# 5) Diários oficiais municipais (Querido Diário, API pública e gratuita)
QD_NOME = {"Vale": "Vale S.A.", "Motiva": "Motiva Infraestrutura", "EMS": None, "Dexco": "Dexco S.A.",
           "Seara": "Seara Alimentos", "Natura": "Natura Cosméticos"}
def querido_diario(empresas, dias=90):
    desde = (HOJE - timedelta(days=dias)).date().isoformat(); res = {}; ok = 0
    for e in empresas:
        b = nome_busca(e["empresa"]); nome = QD_NOME.get(b, b)
        if not nome: continue
        q = f'"{nome}" +(licença | licenciamento | incentivo | ampliação | "nova unidade")'
        u = "https://api.queridodiario.ok.org.br/gazettes?" + urllib.parse.urlencode(
            {"querystring": q, "published_since": desde, "excerpt_size": 250, "number_of_excerpts": 1, "size": 5})
        try: j = json.loads(baixar(u, 60)); ok += 1
        except Exception as ex: print("Querido Diário falhou:", nome, ex); time.sleep(1.5); continue
        for g in j.get("gazettes", []):
            ex = sem_tags(" ".join(g.get("excerpts") or []))[:160]
            res.setdefault(e["empresa"], []).append(sinal("Diário municipal", f'{g.get("territory_name","")}/{g.get("state_code","")}: {ex}',
                                                          g.get("txt_url") or g.get("url"), (g.get("date") or "")[:10], 3))
        time.sleep(1.5)
    if not ok: raise ValueError("nenhuma consulta respondeu")
    AVISOS["Querido Diário"] = f"{ok} consultas; cobre só municípios indexados"
    return {k: unicos(v) for k, v in res.items()}

# 6) Alertas do Google (feeds RSS listados em alertas.txt)
def alertas_google(empresas):
    arq = AQUI / "alertas.txt"
    urls = [l.strip() for l in arq.read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")] if arq.exists() else []
    if not urls: AVISOS["Alertas Google"] = "nenhum alerta em alertas.txt"; return {}
    ns = {"a": "http://www.w3.org/2005/Atom"}; res = {}; itens = 0
    for u in urls:
        try: feed = ET.fromstring(baixar(u, 30))
        except Exception as ex: print("alerta falhou:", ex); continue
        for en in feed.findall("a:entry", ns):
            tit = sem_tags(en.findtext("a:title", "", ns)); txt = tit + " " + sem_tags(en.findtext("a:content", "", ns))
            lk = en.find("a:link", ns); href = lk.get("href") if lk is not None else None
            if href and "url=" in href: href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("url", [href])[0]
            d = (en.findtext("a:published", "", ns) or en.findtext("a:updated", "", ns) or "")[:10]; itens += 1
            for e in empresas:
                if casa(txt, termos(e)): res.setdefault(e["empresa"], []).append(sinal("Alerta Google", tit[:160], href, d, max(1, pontuar(tit))))
    AVISOS["Alertas Google"] = f"{len(urls)} alertas, {itens} itens lidos"
    return {k: unicos(v) for k, v in res.items()}

# 7) Vagas por cargo (portal público da Gupy; interface não oficial, pode mudar)
CARGOS = ["torneiro", "fresador", "ferramenteiro", "operador de empilhadeira", "operador de produção",
          "mecânico de manutenção", "analista administrativo", "supervisor de produção"]
def vagas_gupy(empresas, paginas=3):
    res = {}; lidas = 0; erro = ""
    for cargo in CARGOS:
        for pg in range(paginas):
            u = "https://portal.api.gupy.io/api/job?" + urllib.parse.urlencode({"name": cargo, "limit": 100, "offset": pg * 100})
            try: itens = json.loads(baixar(u, 60)).get("data", [])
            except Exception as ex: erro = str(ex)[:80]; break
            lidas += len(itens)
            for v in itens:
                for e in empresas:
                    if casa(v.get("careerPageName") or v.get("companyName") or "", termos(e)):
                        res.setdefault(e["empresa"], []).append(sinal("Vagas", f'{v.get("name","")} — {v.get("city","")}/{v.get("state","")}',
                                                                      v.get("jobUrl"), (v.get("publishedDate") or "")[:10], 2))
            if len(itens) < 100: break
            time.sleep(1)
    if not lidas: raise ValueError("a Gupy não devolveu vagas " + erro)
    AVISOS["Vagas por cargo"] = f"{lidas} vagas lidas; amostra por cargo, não é o total do mercado"
    return {k: unicos(v) for k, v in res.items()}

def main():
    emp = list(csv.DictReader(open(AQUI / "empresas.csv", encoding="utf-8")))
    sin = {e["empresa"]: [] for e in emp}; status = {}
    def rodar(nome, f):
        try:
            r = f(); n = sum(len(v) for v in r.values()); status[nome] = f"ok ({n} sinais)" + (" — " + AVISOS[nome] if nome in AVISOS else "")
            for k, v in r.items(): sin[k] += v
        except Exception as ex:
            status[nome] = f"erro: {str(ex)[:1200]}"; print(nome, "falhou:", ex)
    def f_not():
        r = {}
        for e in emp:
            try: r[e["empresa"]] = noticias(nome_busca(e["empresa"]))
            except Exception as ex: print("notícia falhou:", e["empresa"], ex)
        return r
    ano = HOJE.year
    rodar("Notícias", f_not)
    rodar("CVM fatos relevantes", lambda: cvm_fatos(baixar(f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"), emp))
    rodar("CVM terceirizados", lambda: cvm_terceirizados(fre_zip(ano), emp))
    rodar("BNDES", lambda: bndes(emp))
    rodar("Querido Diário", lambda: querido_diario(emp))
    rodar("Alertas Google", lambda: alertas_google(emp))
    rodar("Vagas por cargo", lambda: vagas_gupy(emp))
    saida = []
    for e in emp:
        s = sorted(sin[e["empresa"]], key=lambda x: (x["pontos"], x["data"] or ""), reverse=True)
        saida.append({**e, "busca": nome_busca(e["empresa"]), "score": sum(x["pontos"] for x in s[:8]), "sinais": s[:8]})
    saida.sort(key=lambda x: x["score"], reverse=True)
    (AQUI / "data.json").write_text(json.dumps({"atualizado_em": HOJE.isoformat(), "fontes": status, "empresas": saida}, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
