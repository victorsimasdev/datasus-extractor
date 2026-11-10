import copy
import json
from pathlib import Path

import pytest

from extrator import app, fila

PEDIDO = json.loads((Path(__file__).parent / "dados" / "pedido_fa.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASUS_EXTRATOR_HOME", str(tmp_path / "app"))
    monkeypatch.setattr(fila, "iniciar_executor", lambda: True)


@pytest.fixture
def api():
    return app.Api()


def test_bases(api):
    b = {x["chave"]: x for x in api.bases()}
    assert set(b) == {"sih", "sim", "sinasc", "sia"}
    assert b["sih"]["mensal"] and not b["sim"]["mensal"]


def test_formulario_nacional_e_estadual(api):
    nac = api.formulario("sih", "nacional", [])
    assert "Unidade da Federação" in nac["linhas"] and "Não ativa" not in nac["colunas"]
    sexo = next(f for f in nac["filtros"] if f["nome"] == "Sexo")
    assert sexo["coluna"] and [lbl for _, lbl in sexo["opcoes"]] == ["Masc", "Fem", "Ign"]
    est = api.formulario("sih", "estadual", ["ac", "rr"])
    mun = next(f for f in est["filtros"] if f["nome"] == "Município")
    assert mun["geo"] and all(lbl.startswith(("AC · ", "RR · ")) for _, lbl in mun["opcoes"])


def test_estimar_usa_o_plano_real(api):
    e = api.estimar(PEDIDO)
    assert e["consultas"] == 112 and e["arquivos"] == 224 and len(e["abas"]) == 14
    assert e["linhas"][-1] == "SUL"
    assert api.estimar({"nome": "x"})["erro"]


def test_gerar_coloca_na_fila_e_pede_confirmacao_para_substituir(api, tmp_path):
    p = copy.deepcopy(PEDIDO)
    p["saida"]["pasta"] = str(tmp_path / "saida")
    r = api.gerar(p)
    assert r["ok"] and r["posicao"] == 1
    assert api.gerar(p)["erro"]  # já está na fila
    fila.atualizar(r["id"], situacao=fila.CONCLUIDO)
    assert api.gerar(p)["existe"]
    assert api.gerar(p, substituir=True)["ok"]
    lista = api.coletas()["coletas"]
    assert [c["situacao"] for c in lista] == [fila.CONCLUIDO, fila.NA_FILA]


def test_acoes_e_log(api, tmp_path):
    p = copy.deepcopy(PEDIDO)
    p["saida"]["pasta"] = str(tmp_path / "saida")
    r = api.gerar(p)
    assert api.log(r["id"]) == []
    Path(r["pasta"], "execucao.log").write_text("linha 1\nlinha 2\n", encoding="utf-8")
    assert api.log(r["id"]) == ["linha 1", "linha 2"]
    assert api.acao_coleta(r["id"], "remover")["ok"]
    assert api.coletas()["coletas"] == []
