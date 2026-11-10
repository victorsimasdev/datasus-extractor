import pytest

from preencher_planilha import LINHA_PLANILHA_UF, nome_limpo, so_arredondamento, valor_celula


def total(intern=12, valor=3606.08, perm=7.4, obitos=1):
    return {"internacoes": intern, "valor_medio": valor, "media_perm": perm, "obitos": obitos}


@pytest.mark.parametrize("rotulo, esperado", [
    ("12 Acre", "acre"), ("1 Região Norte", "norte"), ("5 Região Centro-Oeste", "centro-oeste"),
    ("TOTAL", "total"), ("35 São Paulo", "são paulo"),
])
def test_nome_limpo(rotulo, esperado):
    assert nome_limpo(rotulo) == esperado


def test_valor_celula():
    assert valor_celula(12.0) == 12 and isinstance(valor_celula(12.0), int)
    assert valor_celula(3606.08) == 3606.08


def test_grafia_da_planilha_para_tocantins():
    assert LINHA_PLANILHA_UF["TOCATINS"] == "to"
    assert LINHA_PLANILHA_UF["TOCANTINS"] == "to"


def test_arredondamento_de_um_centavo_e_aceito():
    # casos reais: Acre Nov/2025 e Amapá Abr/2026
    assert so_arredondamento(total(valor=3606.08), total(valor=3606.07))
    assert so_arredondamento(total(20, 3088.41, 6.7, 0), total(20, 3088.42, 6.7, 0))


@pytest.mark.parametrize("nacional", [
    total(valor=3606.06),   # dois centavos
    total(intern=13),       # internações diferentes
    total(obitos=2),
    total(perm=7.5),
    total(valor=None),
])
def test_outras_diferencas_nao_sao_arredondamento(nacional):
    assert not so_arredondamento(total(), nacional)
