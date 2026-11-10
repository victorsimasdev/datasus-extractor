"""
Preenche a planilha-modelo "FA - INTERNAÇÕES (modelo perfil).xlsx" com as Internações por perfil
coletadas por coletar_perfil.py. O modelo já traz B-E (rodada anterior) e G (= Internações);
este script preenche:
  H Masculino, I Feminino, J-P faixas etárias (20 a 29 ... 80 e mais),
  Q-U cor/raça (Branca, Preta, Parda, Amarela, Indígena).

- O modelo nunca é alterado: o resultado é gravado na pasta de entrega.
- Estados: linha TOTAL da consulta estadual. NORTE ... SUL e BRASIL - TOTAL: consulta nacional por Região.
- "Nenhum registro selecionado" no site = "SR" (mesma convenção da rodada anterior).
- A aba "EVIDÊNCIAS" da entrega anterior (colunas B-E) é copiada para a planilha nova e é criada
  a aba "EVIDÊNCIAS - PERFIL" (colunas H-U): cada valor com o texto exato do site, data/hora e links.
- Conferências automáticas (qualquer falha é listada e impede a entrega):
    1. cada estado/mês/categoria: consulta estadual == consulta nacional por UF;
    2. soma dos 27 estados == TOTAL nacional;
    3. TOTAL nacional por UF == TOTAL nacional por Região;
    4. Masc + Fem, soma das faixas e soma das raças <= Internações (coluna G);
    5. B-E do modelo == planilha entregue na rodada anterior, e G == B;
    6. células H-U já preenchidas no modelo x valores do site.

Uso:
  python preencher_perfil.py           -> ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS/FA - INTERNAÇÕES - preenchida.xlsx
  python preencher_perfil.py --demo    -> "FA - INTERNAÇÕES - preenchida (DEMO PERFIL).xlsx"
"""
import json
import sys
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from coletar_datasus import ABA, MESES, UFS
from coletar_perfil import PROCESSOS, chave
from preencher_planilha import LINHA_PLANILHA_UF, REGIOES, nome_limpo, valor_celula

PASTA = Path(__file__).resolve().parent
MODELO = PASTA / "FA - INTERNAÇÕES (modelo perfil).xlsx"
ANTERIOR = PASTA / "ENTREGA ANTERIOR (Jul-2025 a Ago-2026)" / "FA - INTERNAÇÕES - preenchida.xlsx"
ENTREGA = PASTA / "ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS"
NOME_PLANILHA = "FA - INTERNAÇÕES - preenchida.xlsx"

# coluna -> (processo, categoria, cabeçalho da linha 2 no modelo)
COLUNAS = {"H": ("sexo", "Masc", "Masculin"), "I": ("sexo", "Fem", "Feminino")}
for _col, (_, _cat), _cab in zip("JKLMNOP", PROCESSOS["faixa"][3],
                                 ["20 a 29 anos", "30 a 39 anos", "40 a 49 anos", "50 a 59 anos", "60 a 69 anos",
                                  "70 a 79 anos", "80 anos a mais"]):
    COLUNAS[_col] = ("faixa", _cat, _cab)
for _col, (_, _cat) in zip("QRSTU", PROCESSOS["raca"][3]):
    COLUNAS[_col] = ("raca", _cat, _cat)
GRUPOS = {"sexo": "HI", "faixa": "JKLMNOP", "raca": "QRSTU"}
CABECALHO_GRUPO = {"H1": "SEXO", "J1": "IDADE", "Q1": "RAÇA"}


def copiar_aba(origem, destino):
    """Copia valores, estilos, links e larguras de uma aba de outro arquivo."""
    for linha in origem.iter_rows():
        for c in linha:
            n = destino.cell(c.row, c.column, c.value)
            if c.has_style:
                n._style = copy(c._style)
                n.font, n.number_format = copy(c.font), c.number_format
            if c.hyperlink:
                n.hyperlink = c.hyperlink.target
    for k, d in origem.column_dimensions.items():
        destino.column_dimensions[k].width = d.width
    destino.freeze_panes = origem.freeze_panes


def main():
    demo = "--demo" in sys.argv
    dados = json.loads((PASTA / ("dados_perfil_demo.json" if demo else "dados_perfil.json")).read_text(encoding="utf-8"))
    destino = PASTA / "FA - INTERNAÇÕES - preenchida (DEMO PERFIL).xlsx" if demo else ENTREGA / NOME_PLANILHA

    wb = openpyxl.load_workbook(MODELO)
    anterior = openpyxl.load_workbook(ANTERIOR)
    copiar_aba(anterior["EVIDÊNCIAS"], wb.create_sheet("EVIDÊNCIAS"))
    ev = wb.create_sheet("EVIDÊNCIAS - PERFIL")
    ev.append(["Aba", "Linha", "Estado / Região", "Coluna", "Filtro", "Internações", "Texto exato no site",
               "Consultado em", "Conferência nacional", "PDF", "PNG", "Print do formulário"])
    for c in ev[1]:
        c.font = Font(bold=True)

    problemas, divergencias, faltando, avisos = [], [], [], []
    preenchidas = conferidos = 0

    def link(celula, caminho):
        if caminho:
            celula.value = Path(caminho).name
            celula.hyperlink = caminho.replace("\\", "/")
            celula.font = Font(color="0563C1", underline="single")

    for ws in wb.worksheets:
        if ws.title.startswith("EVIDÊNCIAS"):
            continue
        nome_mes, ano = ws.title.split()
        ano = int(ano)
        mes = ABA.index(nome_mes.upper())
        if (ano, mes) not in MESES:
            sys.exit(f"ERRO: aba inesperada {ws.title}")

        # o layout do modelo tem de ser exatamente o esperado
        for cel, esperado in CABECALHO_GRUPO.items():
            if ws[cel].value != esperado:
                sys.exit(f"ERRO: {ws.title} {cel} = {ws[cel].value!r}, esperado {esperado!r}")
        for col, (_, _, cab) in COLUNAS.items():
            if ws[f"{col}2"].value != cab:
                sys.exit(f"ERRO: {ws.title} {col}2 = {ws[f'{col}2'].value!r}, esperado {cab!r}")

        # 5. B-E iguais à entrega anterior (já conferida com as evidências) e G == B
        wa = anterior[ws.title]
        for row in list(range(3, 30)) + list(REGIOES):
            for c in "BCDE":
                if ws[f"{c}{row}"].value != wa[f"{c}{row}"].value:
                    problemas.append(f"{ws.title} {c}{row}: modelo={ws[f'{c}{row}'].value!r} "
                                     f"entrega anterior={wa[f'{c}{row}'].value!r}")
            if ws[f"G{row}"].value != ws[f"B{row}"].value:
                problemas.append(f"{ws.title} G{row}={ws[f'G{row}'].value!r} diferente de B{row}={ws[f'B{row}'].value!r}")

        for col, (proc, cat, cab) in COLUNAS.items():
            nac_uf = dados.get(chave(proc, cat, "Unidade_da_Federação", ano, mes))
            nac_reg = dados.get(chave(proc, cat, "Região", ano, mes))
            uf_nac = {nome_limpo(k): v for k, v in (nac_uf["tabela"] or {}).items()} if nac_uf else None
            reg_nac = {nome_limpo(k): v for k, v in (nac_reg["tabela"] or {}).items()} if nac_reg else None
            soma, completos = 0, 0
            rotulo_filtro = f"{PROCESSOS[proc][2]}: {cat}"

            for row in range(3, 30):
                nome = (ws[f"A{row}"].value or "").strip().upper()
                uf = LINHA_PLANILHA_UF.get(nome)
                if uf is None:
                    sys.exit(f"ERRO: linha {row} da aba {ws.title} tem nome inesperado: {nome!r}")
                reg = dados.get(chave(proc, cat, uf, ano, mes))
                if reg is None:
                    faltando.append(f"{ws.title} / {nome} / {rotulo_filtro}")
                    continue
                completos += 1
                total = None if reg["sem_registro"] else reg["tabela"]["TOTAL"]
                if total:
                    soma += total["internacoes"]

                # 1. conferência estadual x nacional
                situacao = "não conferido (sem consulta nacional)"
                if uf_nac is not None:
                    outro = uf_nac.get(UFS[uf][0].lower())
                    if (total is None and outro is None) or (
                            total is not None and outro is not None and total["internacoes"] == outro["internacoes"]):
                        situacao = "OK - idêntico"
                        conferidos += 1
                    else:
                        situacao = "DIFERENTE"
                        problemas.append(f"{ws.title} / {nome} / {rotulo_filtro}: estadual={total and total['texto_site']} "
                                         f"nacional={outro and outro['texto_site']}")

                novo = "SR" if total is None else valor_celula(total["internacoes"])
                cel = ws[f"{col}{row}"]
                if cel.value is not None and cel.value != novo:
                    divergencias.append(f"{ws.title} / {nome} / coluna {col}: digitado={cel.value!r}  site={novo!r}")
                cel.value = novo
                if novo != "SR":
                    cel.number_format = "0"
                preenchidas += 1

                ev.append([ws.title, row, nome, col, rotulo_filtro, novo,
                           "Nenhum registro selecionado" if total is None else total["texto_site"][0],
                           reg["consultado_em"].replace("T", " "), situacao])
                r = ev.max_row
                link(ev.cell(r, 10), reg["pdf"])
                link(ev.cell(r, 11), reg["png"])
                link(ev.cell(r, 12), reg.get("png_formulario"))

            if reg_nac is None:
                faltando.append(f"{ws.title} / regiões e Brasil / {rotulo_filtro}")
                continue
            # 2. e 3. conferências do total nacional
            tot_reg = reg_nac["total"]["internacoes"]
            if uf_nac is not None and uf_nac["total"]["internacoes"] != tot_reg:
                problemas.append(f"{ws.title} / {rotulo_filtro}: TOTAL nacional por UF diferente do TOTAL por Região")
            if completos == 27 and soma != tot_reg:
                problemas.append(f"{ws.title} / {rotulo_filtro}: soma dos estados {soma} diferente do TOTAL nacional {tot_reg}")
            for row, (rotulo, k) in REGIOES.items():
                if (ws[f"A{row}"].value or "").strip().upper() != rotulo:
                    sys.exit(f"ERRO: linha {row} da aba {ws.title} não é {rotulo}")
                linha = reg_nac.get(k)
                novo = "SR" if linha is None else valor_celula(linha["internacoes"])
                cel = ws[f"{col}{row}"]
                if cel.value is not None and cel.value != novo:
                    divergencias.append(f"{ws.title} / {rotulo} / coluna {col}: digitado={cel.value!r}  site={novo!r}")
                cel.value = novo
                if novo != "SR":
                    cel.number_format = "0"
                preenchidas += 1
                ev.append([ws.title, row, rotulo, col, rotulo_filtro, novo,
                           "SR" if linha is None else linha["texto_site"][0],
                           nac_reg["consultado_em"].replace("T", " "), "fonte: consulta nacional por Região"])
                r = ev.max_row
                link(ev.cell(r, 10), nac_reg["pdf"])
                link(ev.cell(r, 11), nac_reg["png"])

        # 4. partes nunca maiores que o total de Internações (coluna G)
        for row in list(range(3, 30)) + list(REGIOES):
            total_g = ws[f"G{row}"].value
            tg = 0 if total_g in (None, "SR") else total_g
            for proc, cols in GRUPOS.items():
                vals = [ws[f"{c}{row}"].value for c in cols]
                if any(v is None for v in vals):
                    continue
                s = sum(v for v in vals if v != "SR")
                if s > tg:
                    problemas.append(f"{ws.title} / {ws[f'A{row}'].value}: soma de {PROCESSOS[proc][2]} = {s} "
                                     f"maior que Internações (G) = {total_g}")
                elif proc == "sexo" and s != tg:
                    avisos.append(f"{ws.title} / {ws[f'A{row}'].value}: Masc + Fem = {s}, Internações (G) = {total_g} "
                                  f"(diferença = sexo ignorado ou atualização do site desde a rodada anterior)")

    for i, larg in enumerate([11, 7, 22, 8, 30, 12, 20, 19, 34, 52, 52, 60], start=1):
        ev.column_dimensions[get_column_letter(i)].width = larg
    ev.freeze_panes = "A2"
    destino.parent.mkdir(exist_ok=True)
    wb.save(destino)

    print(f"Células preenchidas (H-U): {preenchidas}")
    print(f"Estado/mês/categoria conferidos com a consulta nacional e idênticos: {conferidos}")
    print(f"Problemas nas conferências: {len(problemas)}")
    for p in problemas:
        print("  PROBLEMA", p)
    print(f"Diferenças com o que já estava digitado: {len(divergencias)}")
    for d in divergencias:
        print("  DIFERENÇA", d)
    print(f"Avisos (Masc + Fem diferente do total de Internações): {len(avisos)}")
    for a in avisos:
        print("  AVISO", a)
    print(f"Consultas ainda não coletadas: {len(faltando)}"
          + ("" if demo or not faltando else "\n  " + "\n  ".join(faltando)))
    print(f"Gravado: {destino}  (modelo intacto)")
    if not demo and (problemas or divergencias or faltando):
        sys.exit(1)


if __name__ == "__main__":
    main()
