"""
Executa o plano de coleta: cada consulta no site, com evidências, gravando o resultado assim que
termina. Rodar de novo continua de onde parou (consultas já salvas são puladas).

Estrutura da pasta de saída:
  pedido.json        o pedido que gerou a coleta
  dados.json         resultado de cada consulta (texto exato de cada célula + caminho das evidências)
  status.json        fase e progresso (lido pela janela e por quem acompanha)
  evidencias/        PDF e PNG de cada consulta, uma pasta por aba
"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .comum import DadosCorrompidos, gravar_json, impedir_suspensao, ler_json


def slug(texto, tamanho=60):
    s = unicodedata.normalize("NFKD", texto)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s.-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:tamanho] or "x"


def pasta_saida(pedido):
    return Path(pedido.get("saida", {}).get("pasta") or "saida") / slug(pedido["nome"])


def destino_evidencia(pasta, consulta):
    h = hashlib.sha1(consulta.chave.encode("utf-8")).hexdigest()[:6]
    papel = consulta.chave.split("|")[3]
    nome = f"{consulta.uf or 'BR'} - {consulta.linha_tipo} - {slug(papel, 50)} - {slug('+'.join(consulta.conteudos), 30)} - {h}"
    return pasta / "evidencias" / slug(consulta.aba) / nome


def status(pasta, **kw):
    kw["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    gravar_json(Path(pasta) / "status.json", kw)


def carregar_dados(pasta):
    try:
        return ler_json(Path(pasta) / "dados.json", {})
    except DadosCorrompidos as e:
        raise SystemExit(f"ERRO: {e}. Restaure uma cópia de segurança antes de continuar.") from e


def coletar(plano, pasta, headless=True, limite=None):
    """Executa as consultas que faltam. Devolve (feitas agora, total)."""
    from playwright.sync_api import sync_playwright

    from .tabnet import Coletor

    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    gravar_json(pasta / "pedido.json", plano.pedido)
    arq = pasta / "dados.json"
    dados = carregar_dados(pasta)
    pendentes = [c for c in plano.consultas if c.chave not in dados]
    total = len(plano.consultas)
    if limite is not None:
        pendentes = pendentes[:limite]
    status(pasta, fase="coleta", feitas=total - len(pendentes) if limite is None else len(dados), total=total)
    if not pendentes:
        return 0, total
    impedir_suspensao()
    evid = plano.pedido.get("saida", {}).get("evidencias", "pdf_png")
    feitas = 0
    with sync_playwright() as pw:
        col = Coletor(pw, pasta, evidencias=evid, headless=headless)
        try:
            for c in pendentes:
                n = len(dados) + 1
                print(f"[{n}/{total}] {c.aba} | {c.uf or 'Brasil'} | {c.linha_tipo} | {c.chave.split('|')[3]}",
                      flush=True)
                r = col.consultar(c.para_dict(), destino_evidencia(pasta, c))
                r["consulta"] = c.para_dict()
                dados[c.chave] = r
                gravar_json(arq, dados)
                feitas += 1
                status(pasta, fase="coleta", feitas=len(dados), total=total, ultima=c.chave)
                if r["sem_registro"]:
                    print("      Nenhum registro selecionado -> SR", flush=True)
                else:
                    print(f"      {len(r['linhas'])} linhas" + (f"; ATENÇÃO: {r['problemas']}" if r["problemas"] else ""),
                          flush=True)
        finally:
            col.fechar()
    return feitas, total


def resumo_dados(pasta):
    dados = carregar_dados(pasta)
    return {"consultas": len(dados), "sem_registro": sum(r["sem_registro"] for r in dados.values()),
            "problemas": [p for r in dados.values() for p in r.get("problemas", [])]}


def ler_pedido_da_pasta(pasta):
    return json.loads((Path(pasta) / "pedido.json").read_text(encoding="utf-8"))
