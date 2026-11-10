"""
Conferência independente das colunas H-U (não usa dados_perfil.json nem o código da coleta):
lê o texto dos PDFs de evidência e compara com cada célula da planilha entregue.
Para cada célula confere no PDF: estado (endereço e título), Conteúdo = só Internações,
Lista Morb CID-10, Período, o filtro da coluna (ex.: "Sexo: Fem") e o valor da linha TOTAL
(estados) ou da linha da região (NORTE ... SUL, BRASIL - TOTAL).

Uso:  python conferir_perfil.py "ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS"
"""
import sys
import unicodedata
from pathlib import Path

import openpyxl
import pypdf

ENT = Path(sys.argv[1])
wb = openpyxl.load_workbook(ENT / "FA - INTERNAÇÕES - preenchida.xlsx")
EV = ENT / "evidencias_perfil"
MES = {"JUL": "Jul", "AGO": "Ago", "SET": "Set", "OUT": "Out", "NOV": "Nov", "DEZ": "Dez", "JAN": "Jan", "FEV": "Fev",
       "MAR": "Mar", "ABR": "Abr", "MAIO": "Mai", "JUN": "Jun"}
NUM = {"JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12, "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4,
       "MAIO": 5, "JUN": 6}
SIGLA = {"ACRE": "ac", "ALAGOAS": "al", "AMAPÁ": "ap", "AMAZONAS": "am", "BAHIA": "ba", "CEARÁ": "ce",
         "DISTRITO FEDERAL": "df", "ESPÍRITO SANTO": "es", "GOIÁS": "go", "MARANHÃO": "ma", "MATO GROSSO": "mt",
         "MATO GROSSO DO SUL": "ms", "MINAS GERAIS": "mg", "PARÁ": "pa", "PARAÍBA": "pb", "PARANÁ": "pr",
         "PERNAMBUCO": "pe", "PIAUÍ": "pi", "RIO DE JANEIRO": "rj", "RIO GRANDE DO NORTE": "rn",
         "RIO GRANDE DO SUL": "rs", "RONDÔNIA": "ro", "RORAIMA": "rr", "SANTA CATARINA": "sc", "SÃO PAULO": "sp",
         "SERGIPE": "se", "TOCANTINS": "to"}
# coluna -> (pasta, categoria no nome do arquivo, filtro como aparece no PDF)
COL = {"H": ("1 - SEXO", "Masc", "Sexo: Masc"), "I": ("1 - SEXO", "Fem", "Sexo: Fem")}
for c, f in zip("JKLMNOP", ["20 a 29 anos", "30 a 39 anos", "40 a 49 anos", "50 a 59 anos", "60 a 69 anos",
                            "70 a 79 anos", "80 anos e mais"]):
    COL[c] = ("2 - FAIXA ETÁRIA", f, f"Faixa Etária 1: {f}")
for c, f in zip("QRSTU", ["Branca", "Preta", "Parda", "Amarela", "Indígena"]):
    COL[c] = ("3 - COR-RAÇA", f, f"Cor/raça: {f}")
# cabeçalho da linha 2 do modelo, para garantir que cada coluna é a categoria certa
CAB2 = dict(zip("HIJKLMNOPQRSTU", ["Masculin", "Feminino", "20 a 29 anos", "30 a 39 anos", "40 a 49 anos",
                                    "50 a 59 anos", "60 a 69 anos", "70 a 79 anos", "80 anos a mais",
                                    "Branca", "Preta", "Parda", "Amarela", "Indígena"]))
REG = {31: "TOTAL", 32: "1 Região Norte", 33: "2 Região Nordeste", 34: "5 Região Centro-Oeste",
       35: "3 Região Sudeste", 36: "4 Região Sul"}
CID = "Lista Morb CID-10: Transtornos de condução e arritmias cardíacas"
nfc = lambda s: unicodedata.normalize("NFC", s)


def texto(pdf):
    return nfc("\n".join(p.extract_text() for p in pypdf.PdfReader(pdf).pages))


def br(v):  # valor da célula -> texto no formato do site
    return "-" if v == 0 else f"{v:,.0f}".replace(",", ".")


def linha_pdf(t, rotulo):
    achadas = [l for l in t.splitlines() if l.startswith(rotulo + " ")]
    if len(achadas) != 1:
        return None
    toks = achadas[0][len(rotulo):].split()
    return toks[0] if len(toks) == 1 else None


erros, ok_cel, sr, usados = [], 0, 0, set()
for ws in wb.worksheets:
    if ws.title.startswith("EVIDÊNCIAS"):
        continue
    m, ano = ws.title.split()
    pref = f"{ano}-{NUM[m]:02d} - {ws.title}"
    periodo = f"Período: {MES[m]}/{ano}"
    for col, cab in CAB2.items():
        if ws[f"{col}2"].value != cab:
            erros.append(f"{ws.title} {col}2: cabeçalho {ws[f'{col}2'].value!r}, esperado {cab!r}")
    for row in list(range(3, 30)) + list(REG):
        if ws[f"G{row}"].value != ws[f"B{row}"].value:
            erros.append(f"{ws.title} G{row}={ws[f'G{row}'].value!r} diferente de B{row}={ws[f'B{row}'].value!r}")
    for col, (pasta, cat, filtro) in COL.items():
        for row in range(3, 30):
            nome = ws[f"A{row}"].value.strip().upper()
            estado = "TOCANTINS" if nome == "TOCATINS" else nome
            pdf = EV / pasta / estado / f"{pref} - {estado} - {cat}.pdf"
            png = pdf.with_suffix(".png")
            usados |= {pdf, png}
            cel = ws[f"{col}{row}"].value
            onde = f"{ws.title} {col}{row} {nome} [{filtro}]"
            if not pdf.is_file() or not png.is_file():
                erros.append(f"{onde}: evidência ausente")
                continue
            t = texto(pdf)
            if f"tabcgi.exe?sih/cnv/ni{SIGLA[estado]}.def" not in t:
                erros.append(f"{onde}: PDF não é da consulta do estado")
            if "Nenhum registro selecionado" in t:
                form = EV / pasta / estado / f"{pref} - {estado} - {cat} - FORMULARIO (sem registro).png"
                usados.add(form)
                if cel == "SR" and form.is_file():
                    sr += 1
                    ok_cel += 1
                else:
                    erros.append(f"{onde}: site sem registro, planilha={cel!r}")
                continue
            for trecho in (CID, periodo, filtro, "Internações segundo Município", "Município Internações"):
                if trecho not in t:
                    erros.append(f"{onde}: PDF sem '{trecho}'")
            cab = [l for l in t.splitlines() if l.startswith("MORBIDADE HOSPITALAR DO SUS - POR LOCAL DE INTERNAÇÃO - ")]
            if not cab or cab[0].split(" - ")[-1].upper() != estado:
                erros.append(f"{onde}: título do PDF = {cab}")
            tok = linha_pdf(t, "TOTAL")
            if tok is None or cel == "SR" or cel is None or br(cel) != tok:
                erros.append(f"{onde}: planilha={cel!r} evidência TOTAL={tok}")
            else:
                ok_cel += 1

        pdf = EV / pasta / "_BRASIL (conferência nacional)" / f"{pref} - BRASIL por Região - {cat}.pdf"
        usados |= {pdf, pdf.with_suffix(".png")}
        if not pdf.is_file():
            erros.append(f"{ws.title} {col} [{filtro}]: evidência nacional por Região ausente")
            continue
        t = texto(pdf)
        for trecho in (CID, periodo, filtro, "Internações segundo Região", "POR LOCAL DE INTERNAÇÃO - BRASIL",
                       "tabcgi.exe?sih/cnv/niuf.def"):
            if trecho not in t:
                erros.append(f"{ws.title} {col} Região [{filtro}]: PDF sem '{trecho}'")
        for row, rot in REG.items():
            cel = ws[f"{col}{row}"].value
            tok = linha_pdf(t, rot)
            if tok is None and cel == "SR":
                ok_cel += 1  # região ausente da tabela nacional = sem registro
            elif tok is None or cel in ("SR", None) or br(cel) != tok:
                erros.append(f"{ws.title} {col}{row} {ws[f'A{row}'].value} [{filtro}]: planilha={cel!r} evidência={tok}")
            else:
                ok_cel += 1

# a consulta nacional por UF também é evidência (conferência cruzada): só conta como usada
for p in EV.rglob("* - BRASIL por UF - *"):
    usados.add(p)

ev = wb["EVIDÊNCIAS - PERFIL"]
links_ok = links_bad = 0
for r in ev.iter_rows(min_row=2):
    for c in r[9:12]:
        if c.hyperlink:
            if (ENT / c.hyperlink.target).is_file():
                links_ok += 1
            else:
                links_bad += 1
                erros.append(f"link quebrado: {c.hyperlink.target}")
todos = {p for p in EV.rglob("*") if p.is_file() and p.name != "desktop.ini"}
print(f"Células H-U conferidas idênticas à evidência: {ok_cel}  (das quais {sr} 'SR' de estado sem registro)")
print(f"Links da aba EVIDÊNCIAS - PERFIL ok: {links_ok}, quebrados: {links_bad}")
print(f"Arquivos de evidência: {len(todos)}; usados na conferência: {len(usados & todos)}; "
      f"não referenciados: {len(todos - usados)}")
for p in sorted(todos - usados):
    print("  extra:", p.relative_to(EV))
print(f"ERROS: {len(erros)}")
for e in erros:
    print("  ", e)
