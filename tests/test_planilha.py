import copy
import json
from pathlib import Path

import openpyxl
import pytest

from extrator.pedido import planejar
from extrator.planilha import SR, gerar, montar

PEDIDO = json.loads((Path(__file__).parent / "dados" / "pedido_fa.json").read_text(encoding="utf-8"))
UFS = ["11 Rondônia", "12 Acre", "13 Amazonas", "14 Roraima", "15 Pará", "16 Amapá", "17 Tocantins", "21 Maranhão",
       "22 Piauí", "23 Ceará", "24 Rio Grande do Norte", "25 Paraíba", "26 Pernambuco", "27 Alagoas", "28 Sergipe",
       "29 Bahia", "31 Minas Gerais", "32 Espírito Santo", "33 Rio de Janeiro", "35 São Paulo", "41 Paraná",
       "42 Santa Catarina", "43 Rio Grande do Sul", "50 Mato Grosso do Sul", "51 Mato Grosso", "52 Goiás",
       "53 Distrito Federal"]
REG = ["1 Região Norte", "2 Região Nordeste", "3 Região Sudeste", "4 Região Sul", "5 Região Centro-Oeste"]


@pytest.fixture
def plano():
    p = copy.deepcopy(PEDIDO)
    p["periodos"] = p["periodos"][:1]
    p["filtros"] = {k: v for k, v in p["filtros"].items() if k in ("Lista Morb  CID-10", "Sexo", "Unidade da Federação")}
    p["ordem_dos_blocos"] = ["Sexo"]
    p["conteudos"] = ["Internações", "Óbitos"]
    p["layout"]["conteudos_nos_blocos"] = ["Internações"]
    return planejar(p)


def resultado(colunas, linhas, sem_registro=False):
    return {"sem_registro": sem_registro, "colunas": colunas, "linhas": linhas, "problemas": [],
            "consultado_em": "2026-11-10T10:00:00", "pdf": "evidencias/x.pdf", "png": None, "png_formulario": None}


def dados_para(plano, sem_registro_regioes=False):
    d = {}
    for c in plano.consultas:
        rot = UFS if c.linha_tipo == "principal" else REG
        if c.papel["tipo"] == "base":
            # o site devolve os conteúdos na ordem dele (Óbitos antes de Internações aqui)
            linhas = [["TOTAL", "-", "100"]] + [[u, "-" if "Acre" in u else "1", str(i + 1)] for i, u in enumerate(rot)]
            if "Roraima" in str(rot):
                linhas = [lin for lin in linhas if "Roraima" not in lin[0]]  # linha que o site não trouxe
            d[c.chave] = resultado([c.linha, "Óbitos", "Internações"], linhas)
        else:
            sem = sem_registro_regioes and c.linha_tipo == "regioes"
            d[c.chave] = resultado([c.linha, "Masc", "Fem", "Total"],
                                   [["TOTAL", "60", "40", "100"]] + [[u, "...", "2", "2"] for u in rot], sem)
    return d


def celula(m, plano, rotulo, grupo, subcoluna):
    il = next(i for i, lin in enumerate(m.linhas) if lin.rotulo == rotulo)
    ic = next(i for i, c in enumerate(m.colunas) if c.grupo == grupo and c.subcoluna == subcoluna)
    return m.celulas[(plano.abas[0], il, ic)]


def test_valores_e_regras_de_sr(plano):
    m = montar(plano, dados_para(plano))
    assert celula(m, plano, "SÃO PAULO", None, "Internações").valor == 20
    assert celula(m, plano, "ACRE", None, "Óbitos").valor == SR  # "-" no site
    assert celula(m, plano, "ACRE", None, "Óbitos").motivo == "site mostra '-'"
    assert celula(m, plano, "RORAIMA", None, "Internações").motivo == "linha ausente no site"
    assert celula(m, plano, "ACRE", "SEXO", "Masculino").valor == SR  # "..." no site
    assert celula(m, plano, "ACRE", "SEXO", "Feminino").valor == 2
    assert celula(m, plano, "BRASIL - TOTAL", None, "Internações").valor == 100
    assert celula(m, plano, "NORTE", "=TOTAL", "INTERNAÇÕES").valor == 1


def test_mapa_aponta_para_a_tabela_do_site(plano):
    m = montar(plano, dados_para(plano))
    c = celula(m, plano, "SÃO PAULO", None, "Internações")
    assert (c.rotulo_site, c.coluna_site, c.colunas_site, c.texto) == ("35 São Paulo", 1, 2, "20")


def test_sem_registro_vira_sr(plano):
    m = montar(plano, dados_para(plano, sem_registro_regioes=True))
    c = celula(m, plano, "NORTE", "SEXO", "Feminino")
    assert c.valor == SR and c.motivo == "nenhum registro selecionado"


def test_consulta_faltando_impede_planilha(plano, tmp_path):
    d = dados_para(plano)
    d.pop(plano.consultas[0].chave)
    r = gerar(plano, d, tmp_path)
    assert r["planilha"] is None and r["faltando"] == [plano.consultas[0].chave]


@pytest.mark.parametrize("formato", ["por_periodo", "longo", "serie"])
def test_grava_os_tres_formatos(plano, tmp_path, formato):
    plano.pedido["saida"]["formato"] = formato
    r = gerar(plano, dados_para(plano), tmp_path)
    wb = openpyxl.load_workbook(r["planilha"])
    assert "EVIDÊNCIAS" in wb.sheetnames and wb["_MAPA"].sheet_state == "hidden"
    copias = sum(1 for c in montar(plano, dados_para(plano)).celulas if plano.colunas[c[2]].grupo == "=TOTAL")
    assert wb["_MAPA"].max_row - 1 == r["celulas"] - (copias if formato == "serie" else 0)  # série não repete o total


def test_layout_por_periodo(plano, tmp_path):
    r = gerar(plano, dados_para(plano), tmp_path)
    ws = openpyxl.load_workbook(r["planilha"]).worksheets[0]
    assert [ws.cell(1, i).value for i in range(1, 7)] == ["ESTADOS", "Internações", "Óbitos", None, "INTERNAÇÕES", "SEXO"]
    assert [ws.cell(2, i).value for i in (6, 7)] == ["Masculino", "Feminino"]
    assert ws.cell(3, 1).value == "ACRE" and ws.cell(3, 3).value == SR
