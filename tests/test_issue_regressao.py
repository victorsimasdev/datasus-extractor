import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
import issue_regressao as ir  # noqa: E402

QUANDO = datetime(2026, 11, 11, 4, 3)
COLETA = """OK          sia
DIFERENÇA   sih
             JAN 2022!B3: esperado 84630, veio 84631
             JAN 2022!C3: esperado 3248, veio 3249
OK          sim
FALHOU      sinasc: código 1, sem planilha
             RuntimeError: tentativas esgotadas

Pedidos: 4; com problema: 2
"""


def test_trechos_importantes_pega_as_falhas_e_o_resumo():
    t = ir.trechos_importantes(COLETA)
    assert t == ["DIFERENÇA   sih", "             JAN 2022!B3: esperado 84630, veio 84631",
                 "             JAN 2022!C3: esperado 3248, veio 3249", "FALHOU      sinasc: código 1, sem planilha",
                 "             RuntimeError: tentativas esgotadas", "Pedidos: 4; com problema: 2"]


def test_corpo_da_issue(tmp_path):
    (tmp_path / "relatorio-coleta").mkdir()
    (tmp_path / "relatorio-coleta" / "relatorio-coleta.txt").write_text(COLETA, encoding="utf-8")
    resultados = {"coleta": {"result": "failure"}, "formularios": {"result": "success"},
                  "executavel": {"result": "failure"}}
    corpo = ir.montar_corpo(resultados, tmp_path, "https://github.com/x/y/actions/runs/1", QUANDO)
    assert "falhou em **11/11/2026 às 04:03**" in corpo
    assert "| Coleta no site | ❌ falhou |" in corpo and "| Formulários do site | ✅ passou |" in corpo
    assert "JAN 2022!B3: esperado 84630, veio 84631" in corpo
    assert "## Formulários do site" not in corpo                      # passou: sem seção
    assert "## Executável (.exe)" in corpo and "Sem relatório" in corpo  # falhou sem relatório
    assert "<details><summary>Registro completo</summary>" in corpo
    assert "### O que fazer" in corpo and "--gravar" in corpo


def test_registro_longo_e_cortado(tmp_path):
    (tmp_path / "relatorio-formularios.txt").write_text("x\n" * 20000, encoding="utf-8")
    corpo = ir.montar_corpo({"formularios": {"result": "failure"}}, tmp_path, "u", QUANDO)
    assert len(corpo) < 20000 and "…" in corpo


def test_saida_do_script(tmp_path, capsys):
    ir.main(["--resultados", '{"coleta": {"result": "failure"}}', "--relatorios", str(tmp_path), "--url", "u",
             "--saida", str(tmp_path / "corpo.md")])
    assert capsys.readouterr().out.startswith("titulo=Regressão falhou em ")
    assert (tmp_path / "corpo.md").read_text(encoding="utf-8").startswith("A regressão contra o site")
