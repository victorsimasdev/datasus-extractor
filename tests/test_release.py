import sys
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


def test_o_que_mudou_agrupa_todos_os_commits_pelo_tipo():
    notas = release.notas_dos_commits([
        ("feat: coleta do SIA", ""), ("fix(tabnet): https", ""), ("docs: README", ""), ("release: versão 3", ""),
        ("test: casos novos", ""), ("ci: workflow", ""), ("refactor: fila", ""), ("chore: limpeza", ""),
        ("ajusta coisa", ""), ("Merge pull request #9 from x/y", "")])
    assert notas == ("### Mudanças incompatíveis\n- Versão 3\n\n### Adicionado\n- Coleta do SIA\n\n"
                     "### Corrigido\n- Https\n\n### Melhorias internas\n- Fila\n\n### Documentação\n- README\n\n"
                     "### Testes e automação\n- Casos novos\n- Workflow\n\n### Manutenção\n- Limpeza\n\n"
                     "### Outros\n- Ajusta coisa")


MODELO = "Descrição fixa da {versao}.\n\n[issue](https://github.com/{repo}/issues/new)\n\n## O que mudou\n\n{notas}\n\n{comparar}\n"


def test_pagina_da_release_com_modelo_e_comparacao():
    pagina = release.pagina_da_release("2.1.0", "### Adicionado\n- Tema rosa", "v2.0.0", MODELO, "dono/repo")
    assert pagina == ("Descrição fixa da 2.1.0.\n\n[issue](https://github.com/dono/repo/issues/new)\n\n"
                      "## O que mudou\n\n### Adicionado\n- Tema rosa\n\n"
                      "**Todas as mudanças:** [v2.0.0...v2.1.0](https://github.com/dono/repo/compare/v2.0.0...v2.1.0)\n")


def test_pagina_da_primeira_release_sem_comparacao():
    pagina = release.pagina_da_release("1.0.0", "", None, MODELO, "dono/repo")
    assert "Sem mudanças registradas." in pagina and "Todas as mudanças" not in pagina


def test_modelo_do_repositorio_tem_os_campos():
    modelo = release.MODELO.read_text(encoding="utf-8")
    assert all(c in modelo for c in ("{versao}", "{notas}", "{comparar}", "{repo}", "## O que mudou"))


def test_carimbar_versao(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n', encoding="utf-8")
    (tmp_path / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(release, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(release, "INIT", tmp_path / "__init__.py")
    release.main(["carimbar", "2.1.3"])
    assert 'version = "2.1.3"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (tmp_path / "__init__.py").read_text(encoding="utf-8") == '__version__ = "2.1.3"\n'
    with pytest.raises(SystemExit):
        release.main(["carimbar", "2.1"])


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
    assert release.notas_dos_commits(commits) == ("### Dependências\n- pypdf 6.21.4 → 7.0.0\n\n"
                                                  "### Testes e automação\n- actions/checkout 4 → 7")


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
