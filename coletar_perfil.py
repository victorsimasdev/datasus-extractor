"""
Coleta de Internações por perfil (sexo, faixa etária e cor/raça), com evidências (PDF + PNG).

Mesmo site e mesmos filtros de coletar_datasus.py (formulário de cada estado, Linha = Município,
Coluna = Não ativa, um mês por consulta, Lista Morb CID-10 = Transtornos de condução e arritmias
cardíacas), mas:
  Conteúdo = só Internações
  + UMA categoria de um filtro extra por consulta:
    processo 1 - Sexo:           Fem, Masc
    processo 2 - Faixa Etária 1: 20 a 29 ... 80 anos e mais (7 faixas)
    processo 3 - Cor/raça:       Branca, Preta, Parda, Amarela, Indígena
Cada consulta = 1 estado x 1 mês x 1 categoria  ->  27 x 14 x 14 = 5.292 consultas,
mais o nacional por Região (linhas NORTE ... SUL e BRASIL - TOTAL) e por UF (conferência
cruzada de cada estado), com os mesmos filtros: 2 x 14 x 14 = 392  ->  5.684 no total.

Uso:
  python coletar_perfil.py --demo   -> alguns exemplos de cada processo, em evidencias_perfil_demo/
  python coletar_perfil.py          -> tudo, em evidencias_perfil/
Se for interrompido, rodar de novo continua de onde parou (chaves "{uf}|AAAA-MM|{processo}|{categoria}").
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from coletar_datasus import ABA, MESES, PASTA_NACIONAL, ROTULO_MES, UFS, Coletor

PASTA = Path(__file__).resolve().parent

# processo -> (pasta, select do formulário, rótulo no resultado, [(valor, categoria), ...])
PROCESSOS = {
    "sexo": ("1 - SEXO", "SSexo", "Sexo", [("2", "Fem"), ("1", "Masc")]),
    "faixa": ("2 - FAIXA ETÁRIA", "SFaixa_Etária_1", "Faixa Etária 1",
              [("6", "20 a 29 anos"), ("7", "30 a 39 anos"), ("8", "40 a 49 anos"), ("9", "50 a 59 anos"),
               ("10", "60 a 69 anos"), ("11", "70 a 79 anos"), ("12", "80 anos e mais")]),
    "raca": ("3 - COR-RAÇA", "SCor/raça", "Cor/raça",
             [("1", "Branca"), ("2", "Preta"), ("3", "Parda"), ("4", "Amarela"), ("5", "Indígena")]),
}

CASOS_DEMO = [
    ("sexo", "Fem", "df", 2025, 8), ("sexo", "Masc", "df", 2025, 8), ("sexo", "Fem", "ac", 2025, 7),
    ("faixa", "60 a 69 anos", "df", 2025, 8), ("faixa", "80 anos e mais", "sp", 2026, 8),
    ("raca", "Parda", "df", 2025, 8), ("raca", "Indígena", "ac", 2026, 8),
]


def todos_casos():
    return [(p, cat, uf, a, m) for p, (_, _, _, cats) in PROCESSOS.items() for _, cat in cats
            for uf in UFS for a, m in MESES]


def todos_nacionais():
    """Mesmos filtros no TabNet nacional: por Região (linhas NORTE ... SUL e BRASIL - TOTAL)
    e por UF (conferência cruzada de cada estado)."""
    return [(p, cat, linha, a, m) for p, (_, _, _, cats) in PROCESSOS.items() for _, cat in cats
            for a, m in MESES for linha in LINHAS_NACIONAIS]


LINHAS_NACIONAIS = {"Região": "por Região", "Unidade_da_Federação": "por UF"}
NACIONAL_DEMO = [("sexo", "Fem", "Região", 2025, 8), ("sexo", "Fem", "Unidade_da_Federação", 2025, 8)]


def chave(p, cat, uf, a, m):
    """uf = sigla do estado, ou a Linha da consulta nacional ("Região" / "Unidade_da_Federação")."""
    if uf in LINHAS_NACIONAIS:
        uf = f"BR-{uf}"
    return f"{uf}|{a}-{m:02d}|{p}|{cat}"


def main():
    demo = "--demo" in sys.argv
    pasta_evid = PASTA / ("evidencias_perfil_demo" if demo else "evidencias_perfil")
    arq_dados = PASTA / ("dados_perfil_demo.json" if demo else "dados_perfil.json")
    dados = json.loads(arq_dados.read_text(encoding="utf-8")) if arq_dados.exists() else {}
    casos = (CASOS_DEMO + NACIONAL_DEMO) if demo else (todos_casos() + todos_nacionais())

    def salvar():  # grava num temporário e troca, para uma interrupção nunca deixar o JSON pela metade
        tmp = arq_dados.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(arq_dados)

    with sync_playwright() as pw:
        col = Coletor(pw, pasta_evid, conteudos=["Internações"], cabecalho=["Internações"],
                      campos=["internacoes"])
        for i, (p, cat, uf, ano, mes) in enumerate(casos, start=1):
            k = chave(p, cat, uf, ano, mes)
            if k in dados:
                continue
            pasta_proc, select, rotulo, cats = PROCESSOS[p]
            valor = next(v for v, c in cats if c == cat)
            if uf in LINHAS_NACIONAIS:
                linha, titulo, sigla = uf, "Brasil", "uf"
                pasta_nome = PASTA_NACIONAL
                nome = f"BRASIL {LINHAS_NACIONAIS[uf]}"
            else:
                linha, sigla = "Município", uf
                titulo, pasta_nome = UFS[uf]
                nome = pasta_nome
            destino = (pasta_evid / pasta_proc / pasta_nome /
                       f"{ano}-{mes:02d} - {ABA[mes]} {ano} - {nome} - {cat}")
            print(f"[{i}/{len(casos)}] {nome} {ROTULO_MES[mes]}/{ano} - {rotulo}: {cat}...", flush=True)
            r = col.consultar(f"sih/cnv/ni{sigla}.def", f"ni{sigla}{ano % 100:02d}{mes:02d}.dbf",
                              linha, titulo, destino, filtro=(select, valor, f"{rotulo}: {cat}"))
            r.update(uf=uf, processo=p, categoria=cat)
            dados[k] = r
            salvar()
            if r["sem_registro"]:
                print("      Nenhum registro selecionado -> SR", flush=True)
            else:
                t = next(v for k2, v in r["tabela"].items() if k2.upper() == "TOTAL")
                print(f"      TOTAL Internações: {t['texto_site'][0]}", flush=True)
    print("Concluído.")


if __name__ == "__main__":
    main()
