import pytest

from extrator.conferencia import SR, conferir_celula, valores_da_linha

PDF = """MORBIDADE HOSPITALAR DO SUS - POR LOCAL DE INTERNAÇÃO - BRASIL
Período: Jul/2025
Unidade da Federação 20 a 29 anos 30 a 39 anos 80 anos e mais Total
TOTAL 183 271 1.610 2.064
11 Rondônia - 1 16 17
12 Acre 1 2 ... 3
21 Maranhão 2 2 3.606,08 7"""


def test_valores_da_linha():
    assert valores_da_linha(PDF, "11 Rondônia") == ["-", "1", "16", "17"]
    assert valores_da_linha(PDF, "TOTAL") == ["183", "271", "1.610", "2.064"]
    assert valores_da_linha(PDF, "53 Distrito Federal") is None
    assert valores_da_linha(PDF + "\nTOTAL 1 2 3 4", "TOTAL") is None  # repetida


@pytest.mark.parametrize("valor, rotulo, col, problema", [
    (271, "TOTAL", 1, False),
    (1610, "TOTAL", 2, False),
    (SR, "11 Rondônia", 0, False),  # "-" -> SR
    (0, "11 Rondônia", 0, True),  # "-" gravado como 0 é erro
    (SR, "12 Acre", 2, False),  # "..." -> SR
    (3606.08, "21 Maranhão", 2, False),
    (3606.07, "21 Maranhão", 2, True),
    (SR, "12 Acre", 0, True),
    (1, "53 Distrito Federal", 0, True),  # linha que não existe no PDF
])
def test_conferir_celula(valor, rotulo, col, problema):
    assert (conferir_celula(valor, PDF, rotulo, col, 4) is not None) == problema


def test_numero_de_colunas_errado():
    assert "valores no PDF" in conferir_celula(17, PDF, "11 Rondônia", 3, 5)


def test_pdf_sem_registro():
    assert conferir_celula(SR, "Nenhum registro selecionado", "TOTAL", 0, 1) is None
    assert conferir_celula(5, "Nenhum registro selecionado", "TOTAL", 0, 1) is not None
