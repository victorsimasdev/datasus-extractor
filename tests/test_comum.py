import pytest

from comum import DadosCorrompidos, copia_identica, gravar_json, impedir_suspensao, ler_json, sha256


def test_gravar_e_ler_json_preserva_acentos(tmp_path):
    arq = tmp_path / "dados.json"
    dados = {"sp|2025-07": {"periodo": "Jul/2025", "texto_site": ["1.234", "6.252,36"]}, "uf": "São Paulo"}
    gravar_json(arq, dados)
    assert ler_json(arq) == dados
    assert "São Paulo" in arq.read_text(encoding="utf-8")


def test_gravar_json_nao_deixa_temporario(tmp_path):
    arq = tmp_path / "dados.json"
    gravar_json(arq, {"a": 1})
    gravar_json(arq, {"a": 2})
    assert [p.name for p in tmp_path.iterdir()] == ["dados.json"]
    assert ler_json(arq) == {"a": 2}


def test_ler_json_ausente_devolve_padrao(tmp_path):
    assert ler_json(tmp_path / "nao_existe.json", {}) == {}
    assert ler_json(tmp_path / "nao_existe.json") is None


def test_ler_json_corrompido_levanta_erro(tmp_path):
    arq = tmp_path / "dados.json"
    arq.write_text('{"sp|2025-07": {"periodo": "Jul', encoding="utf-8")  # gravação interrompida
    with pytest.raises(DadosCorrompidos):
        ler_json(arq, {})


def test_copia_identica(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(b"conteudo-1")
    assert not copia_identica(a, b)  # destino ausente
    b.write_bytes(b"conteudo-1")
    assert copia_identica(a, b)
    b.write_bytes(b"conteudo-2")  # mesmo tamanho, conteúdo diferente
    assert not copia_identica(a, b)
    b.write_bytes(b"curto")
    assert not copia_identica(a, b)


def test_sha256_conhecido(tmp_path):
    arq = tmp_path / "x.txt"
    arq.write_bytes(b"abc")
    assert sha256(arq) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_impedir_suspensao_nao_quebra():
    impedir_suspensao()
