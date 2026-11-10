import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
import regressao  # noqa: E402


def test_sem_diferenca():
    dados = {"JAN 2022": [["REGIÃO", "Internações"], ["1 REGIÃO NORTE", 84630]]}
    assert regressao.diferencas(dados, dados) == []


def test_diferenca_de_celula_aponta_a_posicao():
    esperado = {"JAN 2022": [["REGIÃO", "Internações"], ["1 REGIÃO NORTE", 84630]]}
    obtido = {"JAN 2022": [["REGIÃO", "Internações"], ["1 REGIÃO NORTE", 84631]]}
    assert regressao.diferencas(esperado, obtido) == ["JAN 2022!B2: esperado 84630, veio 84631"]


def test_linha_a_mais_aba_sumida_e_aba_nova():
    esperado = {"A": [["x"]], "B": [["y"]]}
    obtido = {"A": [["x"], ["SR"]], "C": [["z"]]}
    assert regressao.diferencas(esperado, obtido) == ["A!A2: esperado None, veio 'SR'", "aba 'B' sumiu", "aba nova 'C'"]


def test_limite_de_diferencas():
    esperado = {"A": [[i for i in range(30)]]}
    obtido = {"A": [[i + 1 for i in range(30)]]}
    assert len(regressao.diferencas(esperado, obtido, limite=5)) == 5


def test_nome_da_coluna():
    assert [regressao._coluna(j) for j in (0, 25, 26, 27, 701)] == ["A", "Z", "AA", "AB", "ZZ"]


def test_todo_pedido_tem_esperado():
    pedidos = {f.stem for f in regressao.PEDIDOS.glob("*.json")}
    esperados = {f.stem for f in regressao.ESPERADO.glob("*.json")}
    assert pedidos == esperados == {"sih", "sim", "sinasc", "sia"}
