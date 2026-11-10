"""
Monta a planilha do pedido a partir dos resultados coletados.

- Cada célula vem de uma consulta do plano: a linha é casada pelo rótulo do site e a coluna pelo
  cabeçalho do site. Nada é calculado: o valor é o texto exato do site, convertido em número.
- Sem resultado vira "SR": consulta com "Nenhum registro selecionado", linha que o site não trouxe,
  célula com "-" (zero) ou "..." (dado não disponível).
- Aba EVIDÊNCIAS: cada consulta com data/hora, filtros e links do PDF/PNG.
- Aba _MAPA (oculta): de onde veio cada célula (consulta, rótulo da linha e posição da coluna no
  site). A conferência independente usa essa aba para reler cada valor no PDF.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .coleta import slug
from .formularios import normaliza
from .pedido import ColunaPlanilha, chave_linha
from .tabnet import casas_decimais, descrever_filtros, num_br

SR = "SR"
FORMATOS = {0: "0", 1: "0.0", 2: "#,##0.00"}


@dataclass
class Celula:
    valor: object  # número ou "SR"
    texto: str = ""  # texto exato do site
    consulta: str = ""
    rotulo_site: str = ""
    coluna_site: int = -1  # posição entre as colunas de valores da tabela do site
    colunas_site: int = 0
    motivo: str = ""


@dataclass
class Montagem:
    abas: list
    linhas: list
    colunas: list
    celulas: dict = field(default_factory=dict)  # (aba, i_linha, i_coluna) -> Celula
    faltando: list = field(default_factory=list)
    problemas: list = field(default_factory=list)


def _fontes(plano):
    """(aba, uf, tipo de linha) -> {índice da coluna da planilha: (chave da consulta, rótulo da coluna no site)}."""
    fontes = {}
    idx = {(c.grupo, c.subcoluna, c.conteudo): i for i, c in enumerate(plano.colunas)}
    for c in plano.consultas:
        f = fontes.setdefault((c.aba, c.uf, c.linha_tipo), {})
        p = c.papel
        if p["tipo"] == "base":
            for k in c.conteudos:
                for chave in ((None, k, k), ("=TOTAL", k.upper(), k)):
                    if chave in idx:
                        f[idx[chave]] = (c.chave, k)
        elif p["tipo"] == "bloco" and p["modo"] == "total":
            for k in c.conteudos:
                if (p["bloco"], p["subcoluna"], k) in idx:
                    f[idx[(p["bloco"], p["subcoluna"], k)]] = (c.chave, k)
        else:  # coluna ativa: categorias do site -> subcolunas
            k = c.conteudos[0]
            for i, col in enumerate(plano.colunas):
                if col.grupo == p["bloco"] and col.conteudo == k:
                    if p["tipo"] == "bloco":
                        site = next((s for s, nome in p["mapa"].items() if nome == col.subcoluna), None)
                    else:
                        site = chave_linha(col.subcoluna)
                    if site is not None:
                        f[i] = (c.chave, ("chave", site))
    return fontes


def _expandir_dinamicos(plano, dados):
    """Blocos de coluna sem lista conhecida de categorias e linhas sem lista conhecida: usam o que o site trouxe."""
    colunas = []
    for col in plano.colunas:
        if col.subcoluna != "*":
            colunas.append(col)
            continue
        vistos = []
        for c in plano.consultas:
            if c.papel.get("bloco") == col.grupo and c.chave in dados and not dados[c.chave]["sem_registro"]:
                for s in dados[c.chave]["colunas"][1:-1]:
                    if s not in vistos:
                        vistos.append(s)
        colunas += [ColunaPlanilha(col.grupo, s, col.conteudo) for s in vistos]
    linhas = list(plano.linhas)
    if plano.linhas_dinamicas:
        novas = []
        for lin in linhas:
            if lin.tipo == "principal" and lin.chave == "total":
                vistos = []
                for c in plano.consultas:
                    if c.uf == lin.uf and c.linha_tipo == "principal" and c.papel["tipo"] == "base" and c.chave in dados:
                        for row in dados[c.chave]["linhas"]:
                            if normaliza(row[0]) != "total" and row[0] not in vistos:
                                vistos.append(row[0])
                pre = lin.rotulo[:-len("TOTAL")] if lin.rotulo.endswith("TOTAL") and lin.rotulo != "TOTAL" else ""
                from .pedido import LinhaPlanilha
                novas += [LinhaPlanilha(pre + v.upper(), lin.uf, "principal", chave_linha(v)) for v in vistos]
                if vistos:
                    novas.append(LinhaPlanilha("", lin.uf, "separador"))
            novas.append(lin)
        linhas = novas
    return colunas, linhas


def montar(plano, dados):
    colunas, linhas = _expandir_dinamicos(plano, dados)
    plano_exp = type(plano)(**{**plano.__dict__, "colunas": colunas})
    fontes = _fontes(plano_exp)
    m = Montagem(abas=plano.abas, linhas=linhas, colunas=colunas)
    m.faltando = [c.chave for c in plano.consultas if c.chave not in dados]
    m.problemas = [p for c in plano.consultas if c.chave in dados for p in dados[c.chave].get("problemas", [])]
    for aba in plano.abas:
        for il, lin in enumerate(linhas):
            if lin.tipo == "separador":
                continue
            f = fontes.get((aba, lin.uf, lin.tipo), {})
            for ic, _ in enumerate(colunas):
                if ic not in f:
                    m.celulas[(aba, il, ic)] = Celula(SR, motivo="sem consulta (período ou filtro inexistente)")
                    continue
                chave, col_site = f[ic]
                r = dados.get(chave)
                if r is None:
                    m.celulas[(aba, il, ic)] = Celula(SR, consulta=chave, motivo="consulta não coletada")
                    continue
                if r["sem_registro"]:
                    m.celulas[(aba, il, ic)] = Celula(SR, consulta=chave, motivo="nenhum registro selecionado")
                    continue
                cab = r["colunas"]
                if isinstance(col_site, tuple):
                    j = next((k for k, s in enumerate(cab) if k > 0 and chave_linha(s) == col_site[1]), None)
                else:
                    j = next((k for k, s in enumerate(cab) if k > 0 and normaliza(s) == normaliza(col_site)), None)
                row = next((x for x in r["linhas"] if chave_linha(x[0]) == lin.chave), None)
                if j is None or row is None:
                    m.celulas[(aba, il, ic)] = Celula(SR, consulta=chave, rotulo_site=row[0] if row else "",
                                                      coluna_site=(j - 1) if j else -1, colunas_site=len(cab) - 1,
                                                      motivo="coluna ausente no site" if row else "linha ausente no site")
                    continue
                texto = row[j]
                v = num_br(texto)
                m.celulas[(aba, il, ic)] = Celula(SR if v is None else v, texto, chave, row[0], j - 1, len(cab) - 1,
                                                  "" if v is not None else f"site mostra {texto!r}")
    return m


# ---------------------------------------------------------------- gravação
def _nome_aba(nome, usados):
    base = re.sub(r"[\\/*?:\[\]]", " ", nome).upper().strip()[:31] or "ABA"
    n, i = base, 2
    while n in usados:
        n = f"{base[:28]} {i}"
        i += 1
    usados.add(n)
    return n


def _escrever(ws, linha, coluna, cel, mapa, nome_ws):
    from openpyxl.utils import get_column_letter

    c = ws.cell(linha, coluna, cel.valor)
    if cel.valor != SR:
        c.number_format = FORMATOS.get(casas_decimais(cel.texto), "0.00")
    mapa.append([nome_ws, f"{get_column_letter(coluna)}{linha}", cel.valor if cel.valor != SR else SR,
                 cel.consulta, cel.rotulo_site, cel.coluna_site, cel.colunas_site, cel.motivo])


def gravar(plano, montagem, dados, destino):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    pedido = plano.pedido
    formato = pedido.get("saida", {}).get("formato", "por_periodo")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    usados, mapa = set(), []
    negrito, cinza = Font(bold=True), PatternFill("solid", fgColor="EDEDED")
    linhas, colunas = montagem.linhas, montagem.colunas
    cab_linha = "ESTADOS" if normaliza(pedido["linha"]) == normaliza("Unidade da Federação") else pedido["linha"].upper()

    def cabecalho(ws, niveis, ncols):
        for r in range(1, niveis + 1):
            for cc in range(1, ncols + 1):
                ws.cell(r, cc).fill = cinza
        ws.freeze_panes = ws.cell(niveis + 1, 2)
        ws.column_dimensions["A"].width = 32

    if formato == "por_periodo":
        cb = sorted({c.conteudo for c in colunas if c.grupo not in (None, "=TOTAL")})
        niveis = 3 if len(cb) > 1 else 2
        for aba in montagem.abas:
            ws = wb.create_sheet(_nome_aba(aba, usados))
            ws["A1"] = cab_linha
            ws["A1"].font = negrito
            pos, x, anterior = {}, 2, None
            for ic, col in enumerate(colunas):
                if col.grupo == "=TOTAL" and anterior is None:
                    x += 1  # coluna em branco entre o total e os blocos
                if col.grupo is not None and anterior is None and col.grupo != "=TOTAL" and \
                        not any(c.grupo == "=TOTAL" for c in colunas):
                    x += 1
                if col.grupo is None:
                    ws.cell(1, x, col.subcoluna).font = negrito
                elif col.grupo == "=TOTAL":
                    ws.cell(1, x, col.subcoluna).font = negrito
                else:
                    if col.grupo != anterior:
                        ws.cell(1, x, col.grupo).font = negrito
                    prev = colunas[ic - 1] if ic else None
                    if niveis == 3:
                        if not prev or prev.grupo != col.grupo or prev.subcoluna != col.subcoluna:
                            ws.cell(2, x, col.subcoluna)
                        ws.cell(3, x, col.conteudo)
                    else:
                        ws.cell(2, x, col.subcoluna)
                ws.column_dimensions[get_column_letter(x)].width = max(11, min(30, len(col.subcoluna) + 2))
                pos[ic] = x
                anterior = col.grupo
                x += 1
            for il, lin in enumerate(linhas):
                r = niveis + 1 + il
                ws.cell(r, 1, lin.rotulo)
                if lin.tipo == "separador":
                    continue
                for ic in range(len(colunas)):
                    _escrever(ws, r, pos[ic], montagem.celulas[(aba, il, ic)], mapa, ws.title)
            cabecalho(ws, niveis, x - 1)
    elif formato == "longo":
        ws = wb.create_sheet(_nome_aba("DADOS", usados))
        cab = ["Período", "Estado", "Linha", "Bloco", "Coluna", "Conteúdo", "Valor", "Consulta"]
        for i, t in enumerate(cab, start=1):
            ws.cell(1, i, t).font = negrito
        r = 2
        for aba in montagem.abas:
            for il, lin in enumerate(linhas):
                if lin.tipo == "separador":
                    continue
                for ic, col in enumerate(colunas):
                    cel = montagem.celulas[(aba, il, ic)]
                    grupo = "TOTAL" if col.grupo in (None, "=TOTAL") else col.grupo
                    for i, v in enumerate([aba, (lin.uf or "BR").upper(), lin.rotulo, grupo, col.subcoluna,
                                           col.conteudo], start=1):
                        ws.cell(r, i, v)
                    _escrever(ws, r, 7, cel, mapa, ws.title)
                    ws.cell(r, 8, cel.consulta)
                    r += 1
        cabecalho(ws, 1, len(cab))
    else:  # série no tempo: uma aba por grupo (TOTAL e cada bloco), períodos lado a lado
        grupos = []
        for ic, col in enumerate(colunas):
            g = "TOTAL" if col.grupo is None else col.grupo
            if col.grupo == "=TOTAL":
                continue
            if g not in [x[0] for x in grupos]:
                grupos.append((g, []))
            next(x for x in grupos if x[0] == g)[1].append(ic)
        for g, ics in grupos:
            ws = wb.create_sheet(_nome_aba(g, usados))
            ws["A1"] = cab_linha
            x = 2
            pos = {}
            for aba in montagem.abas:
                ws.cell(1, x, aba).font = negrito
                for ic in ics:
                    col = colunas[ic]
                    ws.cell(2, x, col.subcoluna if g != "TOTAL" else col.conteudo)
                    pos[(aba, ic)] = x
                    x += 1
            for il, lin in enumerate(linhas):
                r = 3 + il
                ws.cell(r, 1, lin.rotulo)
                if lin.tipo == "separador":
                    continue
                for (aba, ic), xx in pos.items():
                    _escrever(ws, r, xx, montagem.celulas[(aba, il, ic)], mapa, ws.title)
            cabecalho(ws, 2, x - 1)

    ev = wb.create_sheet("EVIDÊNCIAS")
    cab = ["Consulta", "Período", "Estado", "Linhas", "Papel", "Filtros", "Consultado em", "Resultado",
           "Formulário", "PDF", "PNG", "Print do formulário", "Períodos no site"]
    for i, t in enumerate(cab, start=1):
        ev.cell(1, i, t).font = negrito
    for r, c in enumerate(plano.consultas, start=2):
        d = dados.get(c.chave)
        papel = c.chave.split("|")[3]
        vals = [c.chave, c.aba, (c.uf or "BR").upper(), "regiões" if c.linha_tipo == "regioes" else "principal",
                papel, descrever_filtros(c.para_dict()), (d or {}).get("consultado_em", "").replace("T", " "),
                "não coletada" if d is None else ("Nenhum registro selecionado" if d["sem_registro"] else
                                                  f"{len(d['linhas'])} linhas"), c.caminho_def]
        for i, v in enumerate(vals, start=1):
            ev.cell(r, i, v)
        ev.cell(r, 13, ", ".join(c.periodos))
        for i, k in ((10, "pdf"), (11, "png"), (12, "png_formulario")):
            caminho = (d or {}).get(k)
            if caminho:
                cel = ev.cell(r, i, Path(caminho).name)
                cel.hyperlink = caminho.replace("\\", "/")
                cel.font = Font(color="0563C1", underline="single")
    for i, larg in enumerate([40, 12, 8, 10, 30, 60, 19, 26, 22, 40, 40, 40, 30], start=1):
        ev.column_dimensions[get_column_letter(i)].width = larg
    ev.freeze_panes = "A2"

    mp = wb.create_sheet("_MAPA")
    for i, t in enumerate(["Aba", "Célula", "Valor", "Consulta", "Rótulo no site", "Coluna no site",
                           "Colunas no site", "Motivo do SR"], start=1):
        mp.cell(1, i, t).font = negrito
    for r, lin in enumerate(mapa, start=2):
        for i, v in enumerate(lin, start=1):
            mp.cell(r, i, v)
    mp.sheet_state = "hidden"
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=1, max_row=3):
            for c in row:
                if c.value is not None and c.row <= 3:
                    c.alignment = Alignment(vertical="center")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def gerar(plano, dados, pasta):
    m = montar(plano, dados)
    destino = Path(pasta) / f"{slug(plano.pedido['nome'])}.xlsx"
    if not m.faltando:
        gravar(plano, m, dados, destino)
    total = len(m.celulas)
    sr = sum(1 for c in m.celulas.values() if c.valor == SR)
    return {"planilha": destino if not m.faltando else None, "celulas": total, "sr": sr,
            "faltando": m.faltando, "problemas": m.problemas}
