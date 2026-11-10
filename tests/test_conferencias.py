import pytest

import conferir_evidencias
import conferir_perfil
from coletar_datasus import num_br

PDF_ESTADO = """MORBIDADE HOSPITALAR DO SUS - POR LOCAL DE INTERNAÇÃO - ACRE
Município Internações Valor médio intern Média permanência Óbitos
Rio Branco 12 3.606,08 7,4 1
TOTAL 12 3.606,08 7,4 1"""


@pytest.mark.parametrize("valor, casas, texto", [
    (0, 0, "-"), (0, 2, "-"), (12, 0, "12"), (1234, 0, "1.234"),
    (3606.08, 2, "3.606,08"), (7.4, 1, "7,4"), (1234567.5, 2, "1.234.567,50"),
])
def test_br_formata_como_o_site(valor, casas, texto):
    assert conferir_evidencias.br(valor, casas) == texto


@pytest.mark.parametrize("valor", [12, 1234, 3606.08, 7.4, 1234567.5])
def test_br_e_num_br_sao_inversos(valor):
    assert num_br(conferir_evidencias.br(valor, 2)) == pytest.approx(valor)


def test_br_perfil():
    assert conferir_perfil.br(0) == "-"
    assert conferir_perfil.br(1234) == "1.234"


def test_linha_pdf_encontra_total():
    assert conferir_evidencias.linha_pdf(PDF_ESTADO, "TOTAL") == ["12", "3.606,08", "7,4", "1"]


def test_linha_pdf_rejeita_ambiguidade_e_formato():
    assert conferir_evidencias.linha_pdf(PDF_ESTADO + "\nTOTAL 1 2 3 4", "TOTAL") is None  # repetida
    assert conferir_evidencias.linha_pdf("TOTAL 12 3.606,08", "TOTAL") is None  # colunas a menos
    assert conferir_evidencias.linha_pdf(PDF_ESTADO, "1 Região Norte") is None  # ausente
    assert conferir_perfil.linha_pdf("TOTAL 1.234", "TOTAL") == "1.234"
    assert conferir_perfil.linha_pdf("TOTAL 1.234 5", "TOTAL") is None


@pytest.mark.parametrize("modulo", [conferir_evidencias, conferir_perfil])
def test_uso_incorreto_retorna_2(modulo, capsys):
    assert modulo.main(["script"]) == 2


@pytest.mark.parametrize("modulo", [conferir_evidencias, conferir_perfil])
def test_planilha_ausente_retorna_1(modulo, tmp_path, capsys):
    assert modulo.main(["script", str(tmp_path)]) == 1
    assert "planilha não encontrada" in capsys.readouterr().out
