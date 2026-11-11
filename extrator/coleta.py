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


def _assinatura(consulta):
    """O que define o resultado de uma consulta no site. A chave (aba, UF, papel, conteúdos) serve para retomar,
    mas não muda quando o pedido é substituído com outra linha, outros filtros fixos ou outros períodos na aba."""
    return (consulta.get("caminho_def"), consulta.get("linha"), consulta.get("coluna"),
            sorted(consulta.get("incrementos") or []), sorted(consulta.get("arquivos") or []),
            sorted((k, sorted(v)) for k, v in (consulta.get("filtros") or {}).items()))


def resultado_vale(consulta, resultado):
    """True se o resultado salvo é da consulta como ela está no plano agora (e pode ser aproveitado)."""
    salva = resultado.get("consulta")
    return salva is None or _assinatura(salva) == _assinatura(consulta.para_dict())


def resultados_validos(plano, dados):
    """Só os resultados das consultas do plano que não mudaram desde que foram coletados."""
    return {c.chave: dados[c.chave] for c in plano.consultas if c.chave in dados and resultado_vale(c, dados[c.chave])}


class Interrompida(Exception):
    """A coleta foi parada a pedido (arquivo PARAR na pasta)."""


def coletar(plano, pasta, headless=True, limite=None):
    """Executa as consultas que faltam. Devolve (feitas agora, total)."""
    from playwright.sync_api import sync_playwright

    from .tabnet import Coletor

    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    gravar_json(pasta / "pedido.json", plano.pedido)
    arq = pasta / "dados.json"
    dados = carregar_dados(pasta)
    validos = resultados_validos(plano, dados)
    pendentes = [c for c in plano.consultas if c.chave not in validos]
    mudaram = sum(1 for c in pendentes if c.chave in dados)
    if mudaram:  # pedido substituído: estas consultas mudaram e o resultado antigo não vale mais
        print(f"{mudaram} consultas mudaram no pedido desde a última coleta e serão refeitas", flush=True)
    total = len(plano.consultas)
    if limite is not None:
        pendentes = pendentes[:limite]
    status(pasta, fase="coleta", feitas=len(validos), total=total)
    if not pendentes:
        return 0, total
    if (pasta / "PARAR").exists():
        (pasta / "PARAR").unlink()  # pedido de parada antigo: não vale para esta execução
    impedir_suspensao()
    evid = plano.pedido.get("saida", {}).get("evidencias", "pdf_png")
    feitas = 0
    with sync_playwright() as pw:
        col = Coletor(pw, pasta, evidencias=evid, headless=headless)
        try:
            for c in pendentes:
                if (pasta / "PARAR").exists():  # pedido de parada: termina aqui, com tudo salvo
                    (pasta / "PARAR").unlink()
                    raise Interrompida("parada pedida pelo usuário")
                n = len(validos) + feitas + 1
                print(f"[{n}/{total}] {c.aba} | {c.uf or 'Brasil'} | {c.linha_tipo} | {c.chave.split('|')[3]}",
                      flush=True)
                r = col.consultar(c.para_dict(), destino_evidencia(pasta, c))
                r["consulta"] = c.para_dict()
                dados[c.chave] = r
                gravar_json(arq, dados)
                feitas += 1
                status(pasta, fase="coleta", feitas=n, total=total, ultima=c.chave)
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
