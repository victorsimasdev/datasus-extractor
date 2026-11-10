import pytest

from extrator import tema


@pytest.fixture(autouse=True)
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASUS_EXTRATOR_HOME", str(tmp_path))


def test_paletas_tem_as_mesmas_cores():
    assert set(tema.PALETAS["claro"]) == set(tema.PALETAS["escuro"])


def test_resolver():
    assert tema.resolver("claro") == "claro"
    assert tema.resolver("escuro") == "escuro"
    assert tema.resolver("qualquer") == "claro"
    assert tema.resolver("auto") in ("claro", "escuro")


def test_preferencias_sao_gravadas_e_lidas():
    assert tema.preferencias() == {}
    tema.salvar_preferencia(tema="escuro")
    tema.salvar_preferencia(tamanho="1300x800")
    assert tema.preferencias() == {"tema": "escuro", "tamanho": "1300x800"}


def test_preferencia_corrompida_nao_impede_a_janela(tmp_path):
    (tmp_path / "preferencias.json").write_text("{quebrado", encoding="utf-8")
    assert tema.preferencias() == {}


def test_tema_rosa_vale_como_claro_na_janela_classica():
    from extrator import app, tema

    assert tema.resolver("rosa") == "claro"
    assert app.FUNDOS["rosa"] == "#fdf2f6"
    web = app.WEB
    assert ':root[data-theme="pink"]' in (web / "app.css").read_text(encoding="utf-8")
    assert 'data-tema="rosa"' in (web / "index.html").read_text(encoding="utf-8")
