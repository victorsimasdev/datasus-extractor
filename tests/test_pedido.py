import copy
import json
from pathlib import Path

import pytest

from extrator.formularios import NAO_ATIVA
from extrator.pedido import PedidoInvalido, chave_linha, planejar

PEDIDO_FA = json.loads((Path(__file__).parent / "dados" / "pedido_fa.json").read_text(encoding="utf-8"))


def item(nome, valores, tipo="separada"):
    return {"tipo": tipo, "nome": nome, "valores": valores}


@pytest.mark.parametrize("rotulo, chave", [
    ("12 Acre", "acre"), ("Acre", "acre"), ("1 Região Norte", "norte"), ("NORTE", "norte"),
    ("120001 ACRELANDIA", "acrelandia"), ("TOTAL", "total"), ("São Paulo", "sao paulo"),
])
def test_chave_linha(rotulo, chave):
    assert chave_linha(rotulo) == chave


def test_planilha_fa_gera_112_consultas():
    pl = planejar(PEDIDO_FA)
    assert len(pl.consultas) == 14 * 4 * 2  # 14 meses x (total + 3 blocos) x (estados + regiões)
    assert len({c.chave for c in pl.consultas}) == len(pl.consultas)
    assert pl.avisos == []


def test_planilha_fa_usa_coluna_e_filtro_no_mesmo_campo():
    pl = planejar(PEDIDO_FA)
    sexo = next(c for c in pl.consultas if "bloco:Sexo" in c.chave and c.linha_tipo == "principal")
    assert sexo.coluna == "Sexo"
    assert sexo.filtros["SSexo"] == ["1", "2"]
    assert sexo.incrementos == ["Internações"]  # coluna ativa: um conteúdo só
    assert sexo.papel["mapa"] == {"masc": "Masculino", "fem": "Feminino"}


def test_planilha_fa_linhas_e_colunas():
    pl = planejar(PEDIDO_FA)
    rotulos = [linha.rotulo for linha in pl.linhas]
    assert rotulos[0] == "ACRE" and "IGNORADO/EXTERIOR" not in rotulos
    assert rotulos[-7:] == ["", "BRASIL - TOTAL", "NORTE", "NORDESTE", "CENTRO-OESTE", "SUDESTE", "SUL"]
    cab = [(c.grupo, c.subcoluna) for c in pl.colunas]
    assert cab[:5] == [(None, "Internações"), (None, "Valor médio intern"), (None, "Óbitos"),
                       (None, "Média permanência"), ("=TOTAL", "INTERNAÇÕES")]
    assert [g for g, _ in cab[5:]] == ["SEXO"] * 2 + ["IDADE"] * 7 + ["RAÇA"] * 5


def test_regioes_nao_recebem_restricao_de_linhas():
    pl = planejar(PEDIDO_FA)
    reg = next(c for c in pl.consultas if c.linha_tipo == "regioes")
    assert reg.linha == "Região" and "SUnidade_da_Federação" not in reg.filtros


def test_grupos_e_campo_sem_coluna_viram_uma_consulta_cada():
    p = copy.deepcopy(PEDIDO_FA)
    p["periodos"] = p["periodos"][:1]
    p["filtros"]["Faixa Etária 1"].append(item("60 ou mais", ["10", "11", "12"], "grupo"))
    p["filtros"]["Lista Morb  CID-10"] = [item("Arritmias", ["174"]), item("Cólera", ["1"])]
    pl = planejar(p)
    principais = [c for c in pl.consultas if c.linha_tipo == "principal"]
    grupo = next(c for c in principais if "60 ou mais" in c.chave)
    assert grupo.coluna == NAO_ATIVA and grupo.filtros["SFaixa_Etária_1"] == ["10", "11", "12"]
    cid = [c for c in principais if "Lista Morb" in c.chave]
    assert len(cid) == 2 and all(c.coluna == NAO_ATIVA for c in cid)  # Lista Morb não é coluna no nacional


def test_cruzar_campos():
    p = copy.deepcopy(PEDIDO_FA)
    p["periodos"] = p["periodos"][:1]
    p["combinar_filtros"] = "cruzar"
    pl = planejar(p)
    cruz = [c for c in pl.consultas if "|cruz:" in c.chave and c.linha_tipo == "principal"]
    assert len(cruz) == 2 * 7 * 5
    assert any(c.subcoluna == "Masculino · 20 a 29 anos · Branca" for c in pl.colunas)


def test_periodo_somado_usa_varios_arquivos():
    p = copy.deepcopy(PEDIDO_FA)
    p["periodos"] = [item("1º tri/2026", ["Jan/2026", "Fev/2026", "Mar/2026"], "grupo")]
    c = planejar(p).consultas[0]
    assert c.arquivos == ["niuf2601.dbf", "niuf2602.dbf", "niuf2603.dbf"]


def test_estadual_filtro_de_outro_estado_pula_o_estado():
    p = copy.deepcopy(PEDIDO_FA)
    p.update(abrangencia="estadual", estados=["ac", "al"], linha="Município", filtros={
        "Município": [item("AC · 120001 ACRELANDIA", ["ac|2"])]}, ordem_dos_blocos=[])
    p["periodos"] = p["periodos"][:1]
    pl = planejar(p)
    assert {c.uf for c in pl.consultas} == {"ac"}
    assert any("nenhum filtro escolhido existe neste estado" in a for a in pl.avisos)
    assert [lin.rotulo for lin in pl.linhas if lin.uf == "ac" and lin.tipo == "principal"] == \
        ["AC · 120001 ACRELANDIA", "AC · TOTAL"]


def test_pedido_invalido():
    with pytest.raises(PedidoInvalido):
        planejar({"nome": "x"})
    p = copy.deepcopy(PEDIDO_FA)
    p["linha"] = "Linha que não existe"
    with pytest.raises(PedidoInvalido):
        planejar(p)
