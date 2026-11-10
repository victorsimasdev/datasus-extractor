from pathlib import Path

import pytest

from extrator.tabnet import casas_decimais, conferir_somas, ler_tabela_html, num_br, segmentos, validar_resultado

DADOS = Path(__file__).parent / "dados"
CID = {"Lista Morb  CID-10": ["Transtornos de condução e arritmias cardíacas"]}


def html(nome):
    return (DADOS / nome).read_text(encoding="utf-8")


@pytest.mark.parametrize("texto, valor", [
    ("-", None), ("...", None), ("", None), ("12", 12), ("1.234", 1234), ("6.252,36", 6252.36), ("7,4", 7.4),
])
def test_num_br(texto, valor):
    assert num_br(texto) == valor


def test_num_br_inteiro_e_int():
    assert isinstance(num_br("1.263.166"), int)


def test_casas_decimais():
    assert [casas_decimais(s) for s in ("12", "7,4", "3.606,08", "-")] == [0, 1, 2, 0]


def test_le_tabela_por_uf():
    t = ler_tabela_html(html("resultado_uf.html"))
    assert t["colunas"] == ["Unidade da Federação", "Internações", "Valor médio intern"]
    assert t["linhas"][0] == ["TOTAL", "7.475", "5.267,84"]
    assert ["12 Acre", "13", "728,99"] in t["linhas"]
    assert len(t["linhas"]) == 29  # TOTAL + 27 estados + ignorado/exterior (linhas zeradas exibidas)


def test_le_tabela_com_coluna_ativa():
    t = ler_tabela_html(html("resultado_coluna.html"))
    assert t["colunas"] == ["Região", "Masc", "Fem", "Total"]
    assert t["linhas"][0] == ["TOTAL", "3.952", "3.523", "7.475"]


def test_le_sem_registro():
    assert ler_tabela_html(html("resultado_sem_registro.html"))["sem_registro"] is True


def test_pagina_sem_tabela_e_erro():
    with pytest.raises(ValueError):
        ler_tabela_html("<html><body>Múltiplos conteúdos exigem coluna não ativa.</body></html>")


def test_segmentos_do_titulo():
    t = ler_tabela_html(html("resultado_coluna.html"))["titulo"]
    s = segmentos(t, ["Sexo", "Lista Morb  CID-10", "Período"])
    assert s == {"Lista Morb  CID-10": "transtornos de conducao e arritmias cardiacas", "Sexo": "masc, fem",
                 "Período": "jul/2025"}


def consulta(**kw):
    c = {"chave": "teste", "periodos": ["Jul/2025"], "filtros_rotulos": {**CID, "Sexo": ["Masc", "Fem"]},
         "coluna": "Sexo", "conteudos": ["Internações"]}
    c.update(kw)
    return c


def test_valida_resultado_certo():
    assert validar_resultado(consulta(), ler_tabela_html(html("resultado_coluna.html"))) == []


@pytest.mark.parametrize("errado", [
    {"periodos": ["Ago/2025"]},
    {"filtros_rotulos": {**CID, "Sexo": ["Ign"]}},
    {"filtros_rotulos": {**CID, "Cor/raça": ["Branca"]}},
    {"coluna": "--Não-Ativa--"},
])
def test_valida_resultado_errado(errado):
    with pytest.raises(ValueError):
        validar_resultado(consulta(**errado), ler_tabela_html(html("resultado_coluna.html")))


def test_conteudos_em_outra_ordem_sao_aceitos():
    t = ler_tabela_html(html("resultado_uf.html"))
    c = consulta(coluna="--Não-Ativa--", conteudos=["Valor médio intern", "Internações"], filtros_rotulos=CID)
    assert validar_resultado(c, t) == []


def test_soma_diferente_do_total_e_registrada():
    t = ler_tabela_html(html("resultado_coluna.html"))
    t["linhas"][1][1] = "170"  # Norte Masc: 169 -> 170
    problemas = conferir_somas(consulta(), t)
    assert len(problemas) == 2  # coluna Masc e linha Norte
