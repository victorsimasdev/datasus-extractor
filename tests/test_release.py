import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
import release  # noqa: E402


@pytest.mark.parametrize("assunto, corpo, esperado", [
    ("feat: nova base", "", "menor"),
    ("feat(planilha): formato longo", "", "menor"),
    ("fix: tela tremia", "", "correcao"),
    ("release: nova geração", "", "maior"),
    ("feat!: pedido em formato novo", "", "maior"),
    ("refactor(fila)!: troca a trava", "", "maior"),
    ("fix: muda o pedido", "explica\n\nBREAKING CHANGE: pedidos antigos não abrem", "maior"),
    ("docs: README", "", None),
    ("chore: dependências", "", None),
    ("ci: workflow", "", None),
    ("test: casos novos", "", None),
    ("Merge pull request #6 from x/y", "", None),
    ("ajusta coisa", "", None),
])
def test_classificar(assunto, corpo, esperado):
    assert release.classificar(assunto, corpo) == esperado


@pytest.mark.parametrize("nivel, esperado", [
    ("maior", "3.0.0"), ("menor", "2.5.0"), ("correcao", "2.4.4"), (None, None)])
def test_proxima_zera_a_direita(nivel, esperado):
    assert release.proxima("2.4.3", nivel) == esperado


def test_release_sobe_uma_vez_pela_mudanca_mais_forte():
    commits = [("feat: a", ""), ("feat: b", ""), ("feat: c", ""), ("fix: d", ""), ("fix: e", ""), ("docs: f", "")]
    assert release.proxima("2.0.0", release.nivel_da_release(commits)) == "2.1.0"
    assert release.nivel_da_release([("fix: a", ""), ("fix: b", "")]) == "correcao"
    assert release.nivel_da_release([("docs: a", ""), ("chore: b", "")]) is None
    assert release.nivel_da_release([]) is None


def test_notas_agrupadas_so_com_o_que_sobe_versao():
    notas = release.notas_dos_commits([
        ("feat: coleta do SIA", ""), ("fix(tabnet): https", ""), ("docs: README", ""), ("release: versão 3", "")])
    assert notas == ("### Mudanças incompatíveis\n- Versão 3\n\n### Adicionado\n- Coleta do SIA\n\n"
                     "### Corrigido\n- Https")


CHANGELOG = """# Changelog

Texto de abertura.

## [Não lançado]

## [2.0.0] - 2026-11-10

### Adicionado
- Algo

## [1.0.0] - 2026-01-01
"""


def test_changelog_gerado_dos_commits():
    texto, notas = release.atualizar_changelog(CHANGELOG, "2.1.0", [("feat: nova base", ""), ("ci: x", "")],
                                               date(2026, 12, 1))
    assert notas == "### Adicionado\n- Nova base"
    assert texto.index("## [Não lançado]") < texto.index("## [2.1.0] - 2026-12-01") < texto.index("## [2.0.0]")
    assert texto.count("## [Não lançado]") == 1
    assert texto.startswith("# Changelog\n\nTexto de abertura.\n\n## [Não lançado]\n\n## [2.1.0]")


def test_changelog_usa_o_que_foi_escrito_a_mao():
    base = CHANGELOG.replace("## [Não lançado]\n", "## [Não lançado]\n\n### Alterado\n- Escrito à mão\n")
    texto, notas = release.atualizar_changelog(base, "2.1.0", [("feat: outra coisa", "")], date(2026, 12, 1))
    assert notas == "### Alterado\n- Escrito à mão"
    assert "outra coisa" not in texto
    assert texto.index("## [Não lançado]\n\n## [2.1.0] - 2026-12-01\n\n### Alterado\n- Escrito à mão") > 0


def test_changelog_junta_secao_pronta_e_nao_lancado():
    base = ("# Changelog\n\n## [Não lançado]\n\n### Adicionado\n- Interface nova\n\n"
            "## [2.0.0] - não lançada\n\nColeta genérica.\n\n## [1.0.0] - 2026-01-01\n")
    texto, notas = release.atualizar_changelog(base, "2.0.0", [], date(2026, 11, 10))
    assert notas == "### Adicionado\n- Interface nova\n\nColeta genérica."
    assert "não lançada" not in texto
    assert texto.count("## [2.0.0]") == 1
    assert "## [2.0.0] - 2026-11-10" in texto and texto.index("## [2.0.0]") < texto.index("## [1.0.0]")


def test_versao_forcada_invalida():
    with pytest.raises(SystemExit):
        release.calcular("2.0")
    assert release.calcular("2.0.0") == "2.0.0"


@pytest.mark.parametrize("ultima, calculada, codigo, esperado", [
    ("1.0.0", "1.1.0", "2.0.0", "2.0.0"),   # versão subida à mão no código vence
    ("2.0.0", "2.1.0", "2.0.0", "2.1.0"),   # código igual à tag: vale o cálculo
    ("2.0.0", None, "2.0.0", ""),           # nada sobe a versão: sem release
    ("2.0.0", None, "2.0.1", "2.0.1"),      # só a subida manual
    ("2.0.0", "3.0.0", "2.1.0", "3.0.0"),
])
def test_escolher(ultima, calculada, codigo, esperado):
    assert release.escolher(ultima, calculada, codigo) == esperado


@pytest.mark.parametrize("assunto, arquivos, esperado", [
    ("chore: bump pypdf from 6.21.4 to 7.0.0", ("requirements.txt",), "dependencias"),
    ("chore(deps): bump pywebview from 6.1 to 6.2.1", ("requirements.txt",), "dependencias"),
    ("chore: atualiza o playwright", ("requirements.txt", "README.md"), "dependencias"),
    ("chore(deps-dev): bump ruff from 0.17.4 to 0.18.0", ("requirements-dev.txt",), None),
    ("ci: bump actions/checkout from 4 to 7", (".github/workflows/testes.yml",), None),
    ("feat: nova base", ("requirements.txt", "extrator/pedido.py"), "menor"),   # o mais forte vale
])
def test_dependencias_do_programa_sobem_o_ultimo(assunto, arquivos, esperado):
    assert release.classificar(assunto, "", arquivos) == esperado


def test_release_so_com_dependencias():
    commits = [("chore: bump pypdf from 6.21.4 to 7.0.0", "", ("requirements.txt",)),
               ("ci: bump actions/checkout from 4 to 7", "", (".github/workflows/testes.yml",))]
    assert release.proxima("2.0.0", release.nivel_da_release(commits)) == "2.0.1"
    assert release.notas_dos_commits(commits) == "### Dependências\n- pypdf 6.21.4 → 7.0.0"


def test_notas_com_correcao_e_dependencia():
    commits = [("fix: período errado", "", ("extrator/tabnet.py",)),
               ("chore(deps): bump pywebview from 6.1 to 6.2.1", "", ("requirements.txt",))]
    assert release.notas_dos_commits(commits) == ("### Corrigido\n- Período errado\n\n"
                                                  "### Dependências\n- pywebview 6.1 → 6.2.1")


def test_commits_desde_traz_os_arquivos(tmp_path, monkeypatch):
    import subprocess

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    git("init", "-q")
    (tmp_path / "README.md").write_text("a", encoding="utf-8")
    git("add", "."); git("commit", "-q", "-m", "docs: início"); git("tag", "v2.0.0")
    (tmp_path / "requirements.txt").write_text("pypdf==7.0.0", encoding="utf-8")
    git("add", "."); git("commit", "-q", "-m", "chore: bump pypdf from 6.21.4 to 7.0.0", "-m", "corpo")
    monkeypatch.setattr(release, "RAIZ", tmp_path)
    assert release.ultima_tag() == "v2.0.0"
    assert release.commits_desde("v2.0.0") == [("chore: bump pypdf from 6.21.4 to 7.0.0", "corpo",
                                               ("requirements.txt",))]
