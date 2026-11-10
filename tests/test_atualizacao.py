import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from extrator import app, atualizacao, fila


def _release(tag="v2.1.0", digest=""):
    zip_ = {"name": f"datasus-extractor-{tag[1:]}-windows.zip", "size": 10,
            "browser_download_url": f"https://github.com/x/releases/download/{tag}/x.zip"}
    if digest:
        zip_["digest"] = digest
    return {"tag_name": tag, "html_url": f"https://github.com/x/releases/tag/{tag}", "assets": [zip_]}


def _zip_com(nome, conteudo=b"exe novo"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(nome, conteudo)
    return buf.getvalue()


class _Resposta(io.BytesIO):
    def __init__(self, dados):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}


@pytest.fixture(autouse=True)
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASUS_EXTRATOR_HOME", str(tmp_path / "app"))
    monkeypatch.delenv("EXTRATOR_VERIFICAR_ATUALIZACAO", raising=False)


def test_versao_tupla():
    assert atualizacao.versao_tupla("v2.10.0") == (2, 10, 0) > atualizacao.versao_tupla("2.9.3")
    assert atualizacao.versao_tupla("qualquer") is None


def test_nova_versao_so_quando_mais_nova_e_com_zip():
    info = atualizacao.nova_versao(_release(digest="sha256:ABC"), atual="2.0.0")
    assert info["versao"] == "2.1.0" and info["zip"].endswith("x.zip") and info["sha256"] == "abc"
    assert atualizacao.nova_versao(_release("v2.0.0"), atual="2.0.0") is None
    assert atualizacao.nova_versao(_release("v1.9.0"), atual="2.0.0") is None
    assert atualizacao.nova_versao({**_release(), "assets": []}, atual="2.0.0") is None
    assert atualizacao.nova_versao({**_release(), "prerelease": True}, atual="2.0.0") is None


def test_verificar_so_no_executavel_e_sem_quebrar_sem_internet(monkeypatch):
    chamadas = []
    monkeypatch.setattr(atualizacao.urllib.request, "urlopen", lambda *a, **k: chamadas.append(a) or 1 / 0)
    assert atualizacao.verificar() is None and chamadas == []  # pelo código-fonte não consulta
    monkeypatch.setenv("EXTRATOR_VERIFICAR_ATUALIZACAO", "1")
    assert atualizacao.verificar() is None and len(chamadas) == 1  # erro de rede vira "sem versão nova"
    monkeypatch.setattr(atualizacao.urllib.request, "urlopen",
                        lambda *a, **k: _Resposta(json.dumps(_release("v99.0.0")).encode()))
    assert atualizacao.verificar()["versao"] == "99.0.0"


def test_baixar_confere_o_sha256(monkeypatch, tmp_path):
    dados = _zip_com(atualizacao.NOME_EXE)
    monkeypatch.setattr(atualizacao.urllib.request, "urlopen", lambda *a, **k: _Resposta(dados))
    info = atualizacao.nova_versao(_release(digest="sha256:" + hashlib.sha256(dados).hexdigest()), atual="2.0.0")
    progresso = []
    atualizacao.baixar(info, tmp_path / "a.zip", lambda feito, total: progresso.append((feito, total)))
    assert (tmp_path / "a.zip").read_bytes() == dados and progresso[-1] == (len(dados), len(dados))
    with pytest.raises(ValueError, match="não confere"):
        atualizacao.baixar({**info, "sha256": "0" * 64}, tmp_path / "b.zip")


def test_extrair_exe(tmp_path):
    (tmp_path / "ok.zip").write_bytes(_zip_com(atualizacao.NOME_EXE))
    atualizacao.extrair_exe(tmp_path / "ok.zip", tmp_path / "novo")
    assert (tmp_path / "novo").read_bytes() == b"exe novo"
    (tmp_path / "ruim.zip").write_bytes(_zip_com("outro.exe"))
    with pytest.raises(ValueError):
        atualizacao.extrair_exe(tmp_path / "ruim.zip", tmp_path / "novo2")


def test_instalar_deixa_o_exe_novo_e_inicia_o_script(monkeypatch, tmp_path):
    exe = tmp_path / "Pasta com espaço" / atualizacao.NOME_EXE
    exe.parent.mkdir()
    exe.write_bytes(b"exe antigo")
    monkeypatch.setattr(atualizacao, "executavel", lambda: exe)
    monkeypatch.setattr(atualizacao.urllib.request, "urlopen",
                        lambda *a, **k: _Resposta(_zip_com(atualizacao.NOME_EXE)))
    monkeypatch.setattr(atualizacao.tempfile, "gettempdir", lambda: str(tmp_path))
    iniciados = []
    monkeypatch.setattr(atualizacao.subprocess, "Popen", lambda cmd, **k: iniciados.append((cmd, k)))
    atualizacao.instalar(atualizacao.nova_versao(_release(), atual="2.0.0"))
    assert exe.read_bytes() == b"exe antigo"  # a troca é do script, depois que o programa fecha
    assert exe.with_name(exe.name + ".novo").read_bytes() == b"exe novo"
    cmd, k = iniciados[0]
    assert cmd.startswith('cmd /s /c "') and f'"{exe}"' in cmd
    assert k["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    script = next(Path(tmp_path).glob("datasus-atualizacao-*.cmd")).read_text(encoding="ascii")
    assert "move /Y" in script and 'start "" "%~1"' in script


def test_api_nao_instala_com_coleta_rodando(monkeypatch):
    monkeypatch.setattr(atualizacao, "verificar", lambda: atualizacao.nova_versao(_release(), atual="2.0.0"))
    api = app.Api()
    n = api.verificar_atualizacao()
    assert n["versao"] == "2.1.0" and not n["pode_instalar"] and not n["coleta_rodando"]
    monkeypatch.setattr(fila, "fila_rodando", lambda: True)
    assert "coleta em andamento" in api.instalar_atualizacao()["erro"]
    assert not api.estado_atualizacao()["ativo"]
