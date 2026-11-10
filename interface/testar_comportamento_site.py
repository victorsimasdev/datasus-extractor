"""Testa no site o que acontece quando se marcam várias opções no mesmo campo (protótipo)."""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

OP = json.loads((Path(__file__).resolve().parent / "opcoes_formularios.json").read_text(encoding="utf-8"))
TODAS = "TODAS_AS_CATEGORIAS__"


def consultar(base, linha, conteudos, arquivos, filtros=None, coluna="--Não-Ativa--"):
    campos = OP[base]["nacional"]["campos"]
    d = OP[base]["nacional"]["def"]
    dados = [("Linha", linha), ("Coluna", coluna)]
    dados += [("Incremento", c) for c in conteudos]
    dados += [("Arquivos", a) for a in arquivos]
    filtros = filtros or {}
    for nome in campos:
        if nome.startswith("S"):
            for v in filtros.get(nome, [TODAS]):
                dados.append((nome, v))
    dados += [("formato", "table"), ("mostre", "Mostra")]
    corpo = urllib.parse.urlencode(dados, encoding="windows-1252").encode()
    for t in range(4):
        try:
            req = urllib.request.Request(f"http://tabnet.datasus.gov.br/cgi/tabcgi.exe?{d}", data=corpo,
                                         headers={"User-Agent": "Mozilla/5.0",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            txt = urllib.request.urlopen(req, timeout=180).read().decode("windows-1252", "replace")
            break
        except Exception as e:
            print("   nova tentativa:", e)
            time.sleep(5)
    tab = re.search(r'<table[^>]*class="?tabdados"?[^>]*>(.*?)</table>', txt, re.S | re.I)
    if not tab:
        if "Nenhum registro selecionado" in txt:
            return {"cab": [], "linhas": {}}
        return {"erro": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", txt)))[:300], "cab": [], "linhas": {}}
    corpo_t = tab.group(1)
    cab_html = corpo_t[:corpo_t.upper().find("</THEAD>")]
    cab = [limpa(c) for c in re.split(r"<th[^>]*>", cab_html, flags=re.I)[1:]]
    tbody = corpo_t[corpo_t.upper().find("<TBODY"):]
    linhas = {}
    for tr in re.split(r"<tr[^>]*>", tbody, flags=re.I)[1:]:
        cel = [limpa(c) for c in re.split(r"<t[hd][^>]*>", tr, flags=re.I)[1:]]
        if cel:
            linhas["Total" if cel[0].lower() == "total" else cel[0]] = cel[1:]
    return {"cab": cab, "linhas": linhas}


def limpa(c):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()


def n(s):
    return 0.0 if s in ("-", "...") else float(s.replace(".", "").replace(",", "."))


def total(r, col=0):
    return n(r["linhas"]["Total"][col]) if "Total" in r["linhas"] else 0.0


def caso(nome, base, linha, conteudo, arquivo, campo, valores):
    print(f"\n== {nome}  ({base}, campo {campo})")
    sep = [consultar(base, linha, [conteudo], [arquivo], {campo: [v]}) for v in valores]
    jun = consultar(base, linha, [conteudo], [arquivo], {campo: valores})
    for v, r in zip(valores, sep):
        print(f"   só {v:>3}: Total = {r['linhas'].get('Total')}")
    print(f"   juntos : Total = {jun['linhas'].get('Total')}   (colunas: {jun['cab']})")
    soma = sum(total(r) for r in sep)
    ok = soma > 0 and abs(soma - total(jun)) < 0.5
    print(f"   soma dos separados = {soma:,.0f}  ->  {'JUNTOS = SOMA: uma linha só, somada' if ok else 'ATENÇÃO: juntos diferente da soma'}")
    return sep, jun


if __name__ == "__main__":
    caso("Cor/raça: Branca + Preta", "sih", "Região", "Internações", "niuf2507.dbf", "SCor/raça", ["1", "2"])
    caso("Faixa etária: 60 a 69 + 70 a 79", "sih", "Região", "Internações", "niuf2507.dbf", "SFaixa_Etária_1",
         ["10", "11"])
    caso("Sexo: Masc + Fem", "sih", "Região", "Internações", "niuf2507.dbf", "SSexo", ["1", "2"])

    print("\n== Conteúdo não somável: Valor médio intern, Branca + Preta")
    a = consultar("sih", "Região", ["Valor_médio_intern"], ["niuf2507.dbf"], {"SCor/raça": ["1"]})
    b = consultar("sih", "Região", ["Valor_médio_intern"], ["niuf2507.dbf"], {"SCor/raça": ["2"]})
    j = consultar("sih", "Região", ["Valor_médio_intern"], ["niuf2507.dbf"], {"SCor/raça": ["1", "2"]})
    print(f"   Branca {a['linhas'].get('Total')}  Preta {b['linhas'].get('Total')}  juntos {j['linhas'].get('Total')}"
          f"  (soma seria {total(a) + total(b):,.2f}: a média junta é recalculada pelo site)")

    print("\n== Período: Jul/2025 + Ago/2025 no mesmo pedido")
    a = consultar("sih", "Região", ["Internações"], ["niuf2507.dbf"])
    b = consultar("sih", "Região", ["Internações"], ["niuf2508.dbf"])
    j = consultar("sih", "Região", ["Internações"], ["niuf2507.dbf", "niuf2508.dbf"])
    print(f"   Jul {a['linhas'].get('Total')}  Ago {b['linhas'].get('Total')}  juntos {j['linhas'].get('Total')}"
          f"  -> {'somados' if abs(total(a) + total(b) - total(j)) < 0.5 else 'não somados'}")

    print("\n== Conteúdo: Internações + Óbitos no mesmo pedido")
    j = consultar("sih", "Região", ["Internações", "Óbitos"], ["niuf2507.dbf"])
    print(f"   colunas: {j['cab']}  Total: {j['linhas'].get('Total')}  -> lado a lado, cada um na sua coluna")

    caso("Mortalidade, Sexo: Masc + Fem", "sim", "Região", "Óbitos_p/Residênc", "obtuf24.dbf", "SSexo", ["1", "2"])
    caso("Nascidos vivos, Tipo de parto: Vaginal + Cesário", "sinasc", "Região", "Nascim_p/resid.mãe", "nvuf24.dbf",
         "STipo_de_parto", ["1", "2"])
    caso("Ambulatorial, Complexidade: duas", "sia", "Região", "Qtd.aprovada", "qauf2507.dbf", "SComplexidade",
         [v for v, _ in OP["sia"]["nacional"]["campos"]["SComplexidade"][1:3]])
