"""
Conferência independente (não usa dados_coletados.json): lê o texto dos PDFs de evidência
e compara com cada célula da planilha entregue.

Uso:  python conferir_evidencias.py "ENTREGA - FA INTERNAÇÕES DATASUS"
"""
import sys, unicodedata
from pathlib import Path
import openpyxl, pypdf

ENT = Path(sys.argv[1])
wb = openpyxl.load_workbook(ENT / "FA - INTERNAÇÕES - preenchida.xlsx")
EV = ENT / "evidencias"
MES = {"JUL":"Jul","AGO":"Ago","SET":"Set","OUT":"Out","NOV":"Nov","DEZ":"Dez","JAN":"Jan","FEV":"Fev",
       "MAR":"Mar","ABR":"Abr","MAIO":"Mai","JUN":"Jun"}
NUM = {"JUL":7,"AGO":8,"SET":9,"OUT":10,"NOV":11,"DEZ":12,"JAN":1,"FEV":2,"MAR":3,"ABR":4,"MAIO":5,"JUN":6}
SIGLA = {"ACRE":"ac","ALAGOAS":"al","AMAPÁ":"ap","AMAZONAS":"am","BAHIA":"ba","CEARÁ":"ce","DISTRITO FEDERAL":"df",
 "ESPÍRITO SANTO":"es","GOIÁS":"go","MARANHÃO":"ma","MATO GROSSO":"mt","MATO GROSSO DO SUL":"ms","MINAS GERAIS":"mg",
 "PARÁ":"pa","PARAÍBA":"pb","PARANÁ":"pr","PERNAMBUCO":"pe","PIAUÍ":"pi","RIO DE JANEIRO":"rj",
 "RIO GRANDE DO NORTE":"rn","RIO GRANDE DO SUL":"rs","RONDÔNIA":"ro","RORAIMA":"rr","SANTA CATARINA":"sc",
 "SÃO PAULO":"sp","SERGIPE":"se","TOCANTINS":"to"}
REG = {31:"TOTAL",32:"1 Região Norte",33:"2 Região Nordeste",34:"5 Região Centro-Oeste",35:"3 Região Sudeste",36:"4 Região Sul"}
CID = "Lista Morb CID-10: Transtornos de condução e arritmias cardíacas"
nfc = lambda s: unicodedata.normalize("NFC", s)

def texto(pdf):
    return nfc("\n".join(p.extract_text() for p in pypdf.PdfReader(pdf).pages))

def br(v, casas):  # valor da célula -> texto no formato do site
    if v == 0: return "-"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def linha_pdf(t, rotulo):
    achadas = [l for l in t.splitlines() if l.startswith(rotulo + " ")]
    if len(achadas) != 1: return None
    toks = achadas[0][len(rotulo):].split()
    return toks if len(toks) == 4 else None

erros, ok_cel, sr, usados = [], 0, 0, set()
def cmp(aba, row, nome, celulas, toks):
    global ok_cel
    # planilha: B Intern, C Valor médio, D Óbitos, E Média perm | site: Intern, Valor médio, Média perm, Óbitos
    esperado = [br(celulas[0],0), br(celulas[1],2), br(celulas[3],1), br(celulas[2],0)]
    for col, e, s in zip("BCED", esperado, toks):
        if e == s: ok_cel += 1
        else: erros.append(f"{aba} linha {row} {nome} col {col}: planilha={e} evidência={s}")

for ws in wb.worksheets:
    if ws.title.startswith("EVIDÊNCIAS"): continue
    m, ano = ws.title.split(); n = NUM[m]
    pref = f"{ano}-{n:02d} - {ws.title}"
    periodo = f"Período: {MES[m]}/{ano}"
    for row in range(3, 30):
        nome = ws[f"A{row}"].value.strip().upper()
        estado = "TOCANTINS" if nome == "TOCATINS" else nome
        pdf = EV / estado / f"{pref} - {estado}.pdf"
        png = pdf.with_suffix(".png"); usados |= {pdf, png}
        cel = [ws[f"{c}{row}"].value for c in "BCDE"]
        if not pdf.is_file() or not png.is_file():
            erros.append(f"{ws.title} {nome}: evidência ausente"); continue
        t = texto(pdf)
        if f"tabcgi.exe?sih/cnv/ni{SIGLA[estado]}.def" not in t:
            erros.append(f"{ws.title} {nome}: PDF não é da consulta do estado")
        if "Nenhum registro selecionado" in t:
            form = EV / estado / f"{pref} - {estado} - FORMULARIO (sem registro).png"; usados.add(form)
            if cel == ["SR"]*4 and form.is_file(): sr += 1; ok_cel += 4
            else: erros.append(f"{ws.title} {nome}: site sem registro, planilha={cel}")
            continue
        for trecho in (CID, periodo, "segundo Município"):
            if trecho not in t: erros.append(f"{ws.title} {nome}: PDF sem '{trecho}'")
        cab = [l for l in t.splitlines() if l.startswith("MORBIDADE HOSPITALAR DO SUS - POR LOCAL DE INTERNAÇÃO - ")]
        if not cab or cab[0].split(" - ")[-1].upper() != estado:
            erros.append(f"{ws.title} {nome}: título do PDF = {cab}")
        toks = linha_pdf(t, "TOTAL")
        if toks is None or "SR" in cel: erros.append(f"{ws.title} {nome}: TOTAL={toks} planilha={cel}"); continue
        cmp(ws.title, row, nome, cel, toks)
    pdf = EV / "_BRASIL (conferência nacional)" / f"{pref} - BRASIL por Região.pdf"
    usados |= {pdf, pdf.with_suffix(".png")}
    t = texto(pdf)
    for trecho in (CID, periodo, "segundo Região", "POR LOCAL DE INTERNAÇÃO - BRASIL"):
        if trecho not in t: erros.append(f"{ws.title} Região: PDF sem '{trecho}'")
    for row, rot in REG.items():
        cel = [ws[f"{c}{row}"].value for c in "BCDE"]
        toks = linha_pdf(t, rot)
        if toks is None: erros.append(f"{ws.title} {rot}: linha não encontrada"); continue
        cmp(ws.title, row, ws[f"A{row}"].value, cel, toks)

# aba EVIDÊNCIAS: links apontam para arquivos existentes
ev = wb["EVIDÊNCIAS"]; links_ok = links_bad = 0
for r in ev.iter_rows(min_row=2):
    for c in r[10:13]:
        if c.hyperlink:
            if (ENT / c.hyperlink.target).is_file(): links_ok += 1
            else: links_bad += 1; erros.append(f"link quebrado: {c.hyperlink.target}")
todos = {p for p in EV.rglob("*") if p.is_file() and p.name != "desktop.ini"}
print(f"Células conferidas idênticas à evidência: {ok_cel}  (das quais {sr*4} 'SR' em {sr} estado/mês sem registro)")
print(f"Links da aba EVIDÊNCIAS ok: {links_ok}, quebrados: {links_bad}")
print(f"Arquivos de evidência: {len(todos)}; usados na conferência: {len(usados & todos)}; não referenciados: {len(todos - usados)}")
for p in sorted(todos - usados): print("  extra:", p.relative_to(EV))
print(f"ERROS: {len(erros)}"); [print("  ", e) for e in erros]
