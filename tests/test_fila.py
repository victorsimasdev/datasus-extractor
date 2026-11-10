import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from extrator import fila

PEDIDO = json.loads((Path(__file__).parent / "dados" / "pedido_fa.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASUS_EXTRATOR_HOME", str(tmp_path / "app"))
    return tmp_path


def pedido(tmp_path, nome):
    p = copy.deepcopy(PEDIDO)
    p["nome"] = nome
    p["saida"]["pasta"] = str(tmp_path / "saida")
    arq = tmp_path / f"{nome}.json"
    arq.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return arq


def test_fila_em_ordem_e_sem_duplicar(tmp_path):
    a, pos_a = fila.adicionar(pedido(tmp_path, "A"))
    b, pos_b = fila.adicionar(pedido(tmp_path, "B"))
    assert (pos_a, pos_b) == (1, 2)
    with pytest.raises(fila.JaNaFila):
        fila.adicionar(pedido(tmp_path, "A"))
    assert [e["nome"] for e in fila.listar()] == ["A", "B"]
    assert all(e["situacao"] == fila.NA_FILA for e in fila.listar())


def test_mover_e_remover(tmp_path):
    a, _ = fila.adicionar(pedido(tmp_path, "A"))
    b, _ = fila.adicionar(pedido(tmp_path, "B"))
    assert fila.mover(b["id"], -1)
    assert [e["nome"] for e in fila.listar()] == ["B", "A"]
    assert not fila.mover(b["id"], -1)  # já é o primeiro
    assert fila.remover(a["id"])
    assert [e["nome"] for e in fila.listar()] == ["B"]


def test_executor_roda_um_de_cada_vez(tmp_path):
    for n in ("A", "B", "C"):
        fila.adicionar(pedido(tmp_path, n))
    ordem, simultaneas = [], []

    def falso_rodar(caminho):
        simultaneas.append(fila.coleta_em_andamento() is None)  # o executor não segura a trava de coleta
        em_andamento = [e for e in fila.listar() if e["situacao"] == fila.EM_ANDAMENTO]
        assert len(em_andamento) == 1
        ordem.append(Path(caminho).stem)
        return {"A": 0, "B": 1, "C": 130}[Path(caminho).stem]

    assert fila.executar_fila(rodar=falso_rodar, saida=lambda *a: None) == 0
    assert ordem == ["A", "B", "C"]
    assert [e["situacao"] for e in fila.listar()] == [fila.CONCLUIDO, fila.ERRO, fila.INTERROMPIDO]


def test_reenfileirar_coleta_interrompida(tmp_path):
    e, _ = fila.adicionar(pedido(tmp_path, "A"))
    fila.atualizar(e["id"], situacao=fila.INTERROMPIDO)
    assert fila.reenfileirar(e["id"])
    assert fila.listar()[0]["situacao"] == fila.NA_FILA


def test_trava_exclusiva(tmp_path):
    caminho = tmp_path / "x.lock"
    with fila.trava(caminho, "primeira"):
        with pytest.raises(fila.Ocupado) as ex:
            with fila.trava(caminho, "segunda"):
                pass
        assert ex.value.info["descricao"] == "primeira"
    with fila.trava(caminho, "depois"):  # liberada ao sair
        pass


def test_trava_de_processo_morto_e_retomada(tmp_path):
    caminho = tmp_path / "x.lock"
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    caminho.write_text(json.dumps({"pid": proc.pid, "descricao": "morto"}), encoding="utf-8")
    assert fila.dono_da_trava(caminho) is None
    with fila.trava(caminho, "nova"):
        assert fila.dono_da_trava(caminho)["pid"] == os.getpid()


def test_rodar_recusa_quando_ja_ha_coleta(tmp_path, capsys):
    from extrator.rodar import rodar

    with fila.trava(fila.trava_coleta(), "outra coleta"):
        assert rodar(pedido(tmp_path, "A")) == 3
    assert "Só uma coleta roda por vez" in capsys.readouterr().out


def test_pedir_parada_cria_arquivo(tmp_path):
    e, _ = fila.adicionar(pedido(tmp_path, "A"))
    assert not fila.pedir_parada(e["id"])  # ainda na fila
    fila.atualizar(e["id"], situacao=fila.EM_ANDAMENTO)
    Path(e["pasta"]).mkdir(parents=True)
    assert fila.pedir_parada(e["id"]) and Path(e["pasta"], "PARAR").exists()


def test_executor_no_exe_roda_o_proprio_programa(monkeypatch, tmp_path):
    import subprocess
    import sys

    from extrator import fila

    chamadas = []
    monkeypatch.setattr(fila, "fila_rodando", lambda: False)
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: chamadas.append((args, kw)))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ExtratorDATASUS.exe"))
    assert fila.iniciar_executor() is True
    args, kw = chamadas[0]
    assert args == [str(tmp_path / "ExtratorDATASUS.exe"), "fila"]
    assert kw["cwd"] == tmp_path
    assert kw["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
