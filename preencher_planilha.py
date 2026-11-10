"""
Gera a cópia preenchida da planilha a partir do que coletar_datasus.py coletou.

- O arquivo original "FA - INTERNAÇÕES.xlsx" nunca é alterado.
- Estados: linha TOTAL da consulta estadual (a mesma tabela salva em PDF/PNG).
- NORTE ... SUL e BRASIL - TOTAL: consulta nacional por Região (calculada pelo TabNet).
- Conferências automáticas (qualquer falha é listada no relatório):
    1. cada estado/mês: consulta estadual == consulta nacional por UF (os 4 valores);
    2. soma das internações e óbitos dos 27 estados == TOTAL nacional;
    3. TOTAL nacional por UF == TOTAL nacional por Região;
    4. valores já digitados à mão na planilha original x valores do site.
  Diferença de exatamente R$ 0,01 só no valor médio entre a consulta estadual e a nacional é
  arredondamento do próprio TabNet: vira AVISO (a planilha usa a estadual). Qualquer outra falha
  faz o script terminar com código 1, o que impede a entrega em rodar_noite.py.
- Aba extra "EVIDÊNCIAS": cada valor com o texto exato do site, data/hora e link do PDF/PNG.

Uso:
  python preencher_planilha.py           -> "FA - INTERNAÇÕES - preenchida.xlsx"
  python preencher_planilha.py --demo    -> "FA - INTERNAÇÕES - preenchida (DEMO).xlsx"
"""
import json
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from coletar_datasus import ABA, CAMPOS, MESES, UFS

PASTA = Path(__file__).resolve().parent
ORIGINAL = PASTA / "FA - INTERNAÇÕES.xlsx"

# coluna da planilha -> campo   (B Internações, C Valor médio, D Óbitos, E Média permanência)
COLS = [("B", "internacoes"), ("C", "valor_medio"), ("D", "obitos"), ("E", "media_perm")]
FORMATO = {"B": "0", "C": "#,##0.00", "D": "0", "E": "0.0"}
LINHA_PLANILHA_UF = {nome_planilha: uf for uf, (_, nome_planilha) in UFS.items()}
LINHA_PLANILHA_UF["TOCATINS"] = "to"  # grafia usada na planilha
REGIOES = {31: ("BRASIL - TOTAL", "total"), 32: ("NORTE", "norte"), 33: ("NORDESTE", "nordeste"),
           34: ("CENTRO-OESTE", "centro-oeste"), 35: ("SUDESTE", "sudeste"), 36: ("SUL", "sul")}


def nome_limpo(s):
    """'12 Acre' -> 'acre';  '1 Região Norte' -> 'norte';  'TOTAL' -> 'total'."""
    s = re.sub(r"^\d+\s+", "", s.strip()).lower()
    return re.sub(r"^região\s+", "", s)


def so_arredondamento(estadual, nacional):
    """True se as duas consultas só diferem no valor médio, e por no máximo R$ 0,01."""
    outros = [c for c in CAMPOS if c != "valor_medio"]
    if any(estadual[c] != nacional[c] for c in outros):
        return False
    a, b = estadual["valor_medio"], nacional["valor_medio"]
    return a is not None and b is not None and round(abs(a - b), 2) <= 0.01


def valor_celula(v):
    return int(v) if float(v).is_integer() else v


def main():
    demo = "--demo" in sys.argv
    dados = json.loads((PASTA / ("dados_demo.json" if demo else "dados_coletados.json")).read_text(encoding="utf-8"))
    destino = PASTA / ("FA - INTERNAÇÕES - preenchida (DEMO).xlsx" if demo else "FA - INTERNAÇÕES - preenchida.xlsx")

    wb = openpyxl.load_workbook(ORIGINAL)
    ev = wb.create_sheet("EVIDÊNCIAS")
    ev.append(["Aba", "Linha", "Estado / Região", "Internações", "Valor médio intern", "Óbitos",
               "Média permanência", "Texto exato no site (Intern | Valor médio | Média perm | Óbitos)",
               "Consultado em", "Conferência nacional", "PDF", "PNG", "Print do formulário"])
    for c in ev[1]:
        c.font = Font(bold=True)

    problemas, divergencias_manuais, faltando, avisos = [], [], [], []
    preenchidas = conferidos = 0

    def link(celula, caminho):
        if caminho:
            celula.value = Path(caminho).name
            celula.hyperlink = caminho.replace("\\", "/")
            celula.font = Font(color="0563C1", underline="single")

    for ws in wb.worksheets:
        if ws.title == "EVIDÊNCIAS":
            continue
        nome_mes, ano = ws.title.split()
        ano = int(ano)
        mes = ABA.index(nome_mes.upper())
        if (ano, mes) not in MESES:
            sys.exit(f"ERRO: aba inesperada {ws.title}")
        sufixo = f"{ano}-{mes:02d}"

        nac_uf = dados.get(f"BR-Unidade_da_Federação|{sufixo}")
        nac_reg = dados.get(f"BR-Região|{sufixo}")
        uf_nac = {nome_limpo(k): v for k, v in (nac_uf["tabela"] or {}).items()} if nac_uf else None
        reg_nac = {nome_limpo(k): v for k, v in (nac_reg["tabela"] or {}).items()} if nac_reg else None
        soma = {"internacoes": 0, "obitos": 0}
        completos = 0

        for row in range(3, 30):
            nome = (ws[f"A{row}"].value or "").strip().upper()
            uf = LINHA_PLANILHA_UF.get(nome)
            if uf is None:
                sys.exit(f"ERRO: linha {row} da aba {ws.title} tem nome inesperado: {nome!r}")
            reg = dados.get(f"{uf}|{sufixo}")
            if reg is None:
                faltando.append(f"{ws.title} / {nome}")
                continue
            completos += 1
            total = None if reg["sem_registro"] else reg["tabela"]["TOTAL"]
            if total:
                soma["internacoes"] += total["internacoes"]
                soma["obitos"] += total["obitos"]

            # 1. conferência estadual x nacional
            situacao = "não conferido (sem consulta nacional)"
            if uf_nac is not None:
                outro = uf_nac.get(UFS[uf][0].lower())
                iguais = (total is None and outro is None) or (
                    total is not None and outro is not None and all(total[c] == outro[c] for c in CAMPOS))
                if iguais:
                    situacao = "OK - idêntico"
                    conferidos += 1
                elif total is not None and outro is not None and so_arredondamento(total, outro):
                    situacao = "OK - R$ 0,01 no valor médio (arredondamento do TabNet)"
                    avisos.append(f"{ws.title} / {nome}: estadual={total['texto_site']} "
                                  f"nacional={outro['texto_site']} (arredondamento do TabNet; usado o estadual)")
                else:
                    situacao = "DIFERENTE"
                    problemas.append(f"{ws.title} / {nome}: estadual={total and total['texto_site']} "
                                     f"nacional={outro and outro['texto_site']}")

            for col, campo in COLS:
                novo = "SR" if total is None else valor_celula(total[campo])
                cel = ws[f"{col}{row}"]
                if cel.value is not None and cel.value != novo:
                    divergencias_manuais.append(f"{ws.title} / {nome} / coluna {col}: "
                                                f"digitado={cel.value!r}  site={novo!r}")
                cel.value = novo
                if novo != "SR":
                    cel.number_format = FORMATO[col]
                preenchidas += 1

            ev.append([ws.title, row, nome] +
                      [("SR" if total is None else valor_celula(total[c]))
                       for c in ("internacoes", "valor_medio", "obitos", "media_perm")] +
                      ["Nenhum registro selecionado" if total is None else " | ".join(total["texto_site"]),
                       reg["consultado_em"].replace("T", " "), situacao])
            r = ev.max_row
            link(ev.cell(r, 11), reg["pdf"])
            link(ev.cell(r, 12), reg["png"])
            link(ev.cell(r, 13), reg.get("png_formulario"))

        if reg_nac is None:
            faltando.append(f"{ws.title} / regiões e Brasil")
            continue
        # 2. e 3. conferências do total nacional
        tot_reg = reg_nac["total"]
        if uf_nac is not None:
            if any(uf_nac["total"][c] != tot_reg[c] for c in CAMPOS):
                problemas.append(f"{ws.title}: TOTAL nacional por UF diferente do TOTAL por Região")
            if completos == 27 and any(soma[c] != tot_reg[c] for c in soma):
                problemas.append(f"{ws.title}: soma dos estados {soma} diferente do TOTAL nacional "
                                 f"{tot_reg['texto_site']}")
        for row, (rotulo, chave) in REGIOES.items():
            if (ws[f"A{row}"].value or "").strip().upper() != rotulo:
                sys.exit(f"ERRO: linha {row} da aba {ws.title} não é {rotulo}")
            linha = reg_nac.get(chave)
            for col, campo in COLS:
                novo = "SR" if linha is None else valor_celula(linha[campo])
                ws[f"{col}{row}"].value = novo
                if novo != "SR":
                    ws[f"{col}{row}"].number_format = FORMATO[col]
                preenchidas += 1
            ev.append([ws.title, row, rotulo] +
                      [("SR" if linha is None else valor_celula(linha[c]))
                       for c in ("internacoes", "valor_medio", "obitos", "media_perm")] +
                      ["SR" if linha is None else " | ".join(linha["texto_site"]),
                       nac_reg["consultado_em"].replace("T", " "), "fonte: consulta nacional por Região"])
            r = ev.max_row
            link(ev.cell(r, 11), nac_reg["pdf"])
            link(ev.cell(r, 12), nac_reg["png"])

    for i, larg in enumerate([11, 7, 22, 12, 17, 9, 17, 48, 19, 34, 42, 42, 52], start=1):
        ev.column_dimensions[get_column_letter(i)].width = larg
    ev.freeze_panes = "A2"
    wb.save(destino)

    print(f"Células preenchidas: {preenchidas}")
    print(f"Estado/mês conferidos com a consulta nacional e idênticos: {conferidos}")
    print(f"Avisos (R$ 0,01 de arredondamento no valor médio): {len(avisos)}")
    for a in avisos:
        print("  AVISO", a)
    print(f"Problemas nas conferências: {len(problemas)}")
    for p in problemas:
        print("  PROBLEMA", p)
    print(f"Diferenças com o que já estava digitado no original: {len(divergencias_manuais)}")
    for d in divergencias_manuais:
        print("  DIFERENÇA", d)
    print(f"Consultas ainda não coletadas: {len(faltando)}"
          + ("" if demo or not faltando else "\n  " + "\n  ".join(faltando)))
    print(f"Gravado: {destino.name}  (original intacto)")
    if not demo and (problemas or divergencias_manuais or faltando):
        sys.exit(1)


if __name__ == "__main__":
    main()
