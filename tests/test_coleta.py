import pytest

from coletar_datasus import MESES, UFS, normaliza, num_br
from coletar_perfil import PROCESSOS, chave, todos_casos, todos_nacionais


@pytest.mark.parametrize("texto, esperado", [
    ("-", 0),            # zero verdadeiro no TabNet
    ("...", None),       # dado não disponível
    ("12", 12),
    ("1.234", 1234),
    ("6.252,36", 6252.36),
    ("7,4", 7.4),
    (" 3.606,08 ", 3606.08),
])
def test_num_br(texto, esperado):
    assert num_br(texto) == esperado


def test_normaliza():
    assert normaliza("  Período:\n Jul/2025\t ") == "Período: Jul/2025"


def test_periodo_e_estados():
    assert len(UFS) == 27
    assert len(MESES) == 14
    assert MESES[0] == (2025, 7) and MESES[-1] == (2026, 8)


def test_quantidade_de_consultas_por_perfil():
    categorias = sum(len(cats) for *_, cats in PROCESSOS.values())
    assert categorias == 14
    assert len(todos_casos()) == 27 * 14 * 14 == 5292
    assert len(todos_nacionais()) == 2 * 14 * 14 == 392


def test_chaves_unicas_e_no_formato_esperado():
    chaves = [chave(*c) for c in todos_casos() + todos_nacionais()]
    assert len(chaves) == len(set(chaves)) == 5684
    assert chave("sexo", "Fem", "df", 2025, 8) == "df|2025-08|sexo|Fem"
    assert chave("raca", "Parda", "Região", 2026, 1) == "BR-Região|2026-01|raca|Parda"
    assert chave("faixa", "80 anos e mais", "Unidade_da_Federação", 2025, 12) == \
        "BR-Unidade_da_Federação|2025-12|faixa|80 anos e mais"
