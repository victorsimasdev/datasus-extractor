"""Pedido substituído na mesma pasta: só se aproveita o resultado das consultas que não mudaram."""
import contextlib
import copy
import json
import sys
import types
from pathlib import Path

from extrator import coleta, tabnet
from extrator.coleta import resultado_vale
from extrator.pedido import planejar
from extrator.planilha import montar

PEDIDO = json.loads((Path(__file__).parent / "dados" / "pedido_fa.json").read_text(encoding="utf-8"))


def pedido(**mudancas):
    p = copy.deepcopy(PEDIDO)
    p["periodos"] = p["periodos"][:1]
    p["filtros"] = {k: v for k, v in p["filtros"].items() if k == "Lista Morb  CID-10"}
    p.update(mudancas)
    return p


def salvo(consulta):
    return {"sem_registro": True, "colunas": [], "linhas": [], "problemas": [], "consulta": consulta.para_dict()}


def test_mesma_chave_com_outra_linha_ou_outro_filtro_nao_vale():
    original = planejar(pedido()).consultas[0]
    outra_linha = planejar(pedido(linha="Região")).consultas[0]
    sem_filtro = planejar(pedido(filtros={})).consultas[0]
    assert outra_linha.chave == original.chave == sem_filtro.chave  # a chave sozinha não percebe a mudança
    assert resultado_vale(original, salvo(original))
    assert not resultado_vale(outra_linha, salvo(original))
    assert not resultado_vale(sem_filtro, salvo(original))
    assert resultado_vale(original, {"sem_registro": True})  # sem a consulta salva não dá para saber: vale


def test_planilha_trata_resultado_de_consulta_que_mudou_como_nao_coletado():
    antigo = planejar(pedido())
    novo = planejar(pedido(linha="Região"))
    dados = {c.chave: salvo(c) for c in antigo.consultas}
    assert montar(antigo, dados).faltando == []
    assert sorted(montar(novo, dados).faltando) == sorted(c.chave for c in novo.consultas)


def test_coleta_refaz_so_as_consultas_que_mudaram(tmp_path, monkeypatch):
    p = pedido(conteudos=["Internações", "Óbitos"], colunas=["Sexo"])
    antigo = planejar(p)
    novo = planejar({**p, "filtros": {}})  # tirou o filtro fixo: todas as consultas mudam
    assert {c.chave for c in antigo.consultas} == {c.chave for c in novo.consultas}
    pasta = tmp_path / "saida"
    pasta.mkdir()
    dados = {c.chave: salvo(c) for c in antigo.consultas}
    manter = novo.consultas[0]
    dados[manter.chave] = salvo(manter)  # esta já foi coletada como está no pedido novo
    (pasta / "dados.json").write_text(json.dumps(dados), encoding="utf-8")

    consultadas = []

    class Coletor:
        def __init__(self, *a, **k):
            pass

        def consultar(self, consulta, destino):
            consultadas.append(consulta["chave"])
            return {"sem_registro": True, "colunas": [], "linhas": [], "problemas": []}

        def fechar(self):
            pass

    falso = types.ModuleType("playwright.sync_api")
    falso.sync_playwright = lambda: contextlib.nullcontext(None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", falso)
    monkeypatch.setattr(tabnet, "Coletor", Coletor)
    monkeypatch.setattr(coleta, "impedir_suspensao", lambda: None)

    feitas, total = coleta.coletar(novo, pasta)
    assert sorted(consultadas) == sorted(c.chave for c in novo.consultas[1:])
    assert (feitas, total) == (len(novo.consultas) - 1, len(novo.consultas))
    gravados = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
    assert all(resultado_vale(c, gravados[c.chave]) for c in novo.consultas)
    assert coleta.coletar(novo, pasta) == (0, total)  # nada mais a refazer
