import pytest

from extrator.__main__ import main


def test_ajuda(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    assert "rodar" in capsys.readouterr().out


def test_conferir_planilha_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        main(["conferir", str(tmp_path / "nao_existe.xlsx")])
