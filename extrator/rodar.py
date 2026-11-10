"""
Execução completa e sem supervisão de um pedido:
  1. coleta todas as consultas (se cair por instabilidade do site, espera e continua de onde parou);
  2. monta a planilha;
  3. roda a conferência independente pelos PDFs;
  4. grava RELATÓRIO.txt e status.json ("concluido" só com 0 erros na conferência).
"""
import sys
import time
from datetime import datetime
from pathlib import Path

from . import coleta, conferencia, planilha
from .pedido import carregar, planejar


class Log:
    def __init__(self, arquivo):
        self.arquivo = Path(arquivo)
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg=""):
        linha = f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {msg}"
        print(linha, flush=True)
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")


def rodar(caminho_pedido, headless=True, limite_horas=72, espera_falha=300):
    """Executa o pedido. Nunca roda junto com outra coleta: se já houver uma em andamento, recusa
    (código 3) e sugere a fila."""
    from .fila import Ocupado, trava, trava_coleta

    pedido = carregar(caminho_pedido)
    try:
        with trava(trava_coleta(), f"{pedido['nome']} ({coleta.pasta_saida(pedido)})"):
            return _rodar(pedido, headless, limite_horas, espera_falha)
    except Ocupado as e:
        print(f"Já existe uma coleta em andamento: {e}. Só uma coleta roda por vez.\n"
              f"Para colocar este pedido na fila:  python -m extrator fila adicionar \"{caminho_pedido}\"")
        return 3


def _rodar(pedido, headless, limite_horas, espera_falha):
    plano = planejar(pedido)
    pasta = coleta.pasta_saida(pedido)
    log = Log(pasta / "execucao.log")
    log(f"Pedido: {pedido['nome']}  ({len(plano.consultas)} consultas)  ->  {pasta}")
    for a in plano.avisos:
        log(f"AVISO: {a}")

    inicio = time.time()
    while True:
        try:
            coleta.coletar(plano, pasta, headless=headless)
            break
        except (KeyboardInterrupt, coleta.Interrompida):
            log("Coleta parada a pedido. Rode de novo (ou coloque na fila) para continuar de onde parou.")
            coleta.status(pasta, fase="interrompido")
            return 130
        except Exception as e:
            if time.time() - inicio > limite_horas * 3600:
                log(f"ERRO: limite de {limite_horas} h atingido: {e}")
                coleta.status(pasta, fase="erro", motivo=f"limite de tempo: {e}")
                return 1
            log(f"Coleta interrompida ({type(e).__name__}: {str(e)[:200]}); continuo em {espera_falha // 60} min")
            coleta.status(pasta, fase="aguardando", motivo=str(e)[:300])
            time.sleep(espera_falha)
    log("Coleta completa")

    coleta.status(pasta, fase="planilha")
    dados = coleta.carregar_dados(pasta)
    r = planilha.gerar(plano, dados, pasta)
    if r["faltando"]:
        log(f"ERRO: {len(r['faltando'])} consultas sem resultado; planilha não gerada")
        coleta.status(pasta, fase="erro", motivo="consultas faltando")
        return 1
    log(f"Planilha: {r['planilha'].name}  ({r['celulas']} células, {r['sr']} SR)")

    linhas_conf = []
    erros = []
    saida = pedido.get("saida", {})
    if saida.get("conferir_pdf", True) and saida.get("evidencias", "pdf_png") != "nenhuma":
        coleta.status(pasta, fase="conferencia")
        erros = conferencia.conferir(r["planilha"], saida=linhas_conf.append)
        for lin in linhas_conf[:4]:
            log(lin)
    else:
        linhas_conf.append("Conferência pelos PDFs desligada no pedido (ou sem evidências).")

    rel = pasta / "RELATÓRIO.txt"
    rel.write_text("\n".join([
        f"Pedido: {pedido['nome']}",
        f"Gerado em {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Consultas: {len(plano.consultas)}",
        f"Planilha: {r['planilha'].name}  ({r['celulas']} células, {r['sr']} SR)",
        "",
        "Avisos do plano:", *(f"  {a}" for a in plano.avisos or ["nenhum"]),
        "",
        "Somas que não batem com o TOTAL do site (o valor da planilha é sempre o do site):",
        *(f"  {p}" for p in r["problemas"] or ["nenhuma"]),
        "",
        "Conferência independente (texto dos PDFs x planilha):", *linhas_conf, "",
    ]), encoding="utf-8")
    fase = "concluido" if not erros else "erro"
    coleta.status(pasta, fase=fase, feitas=len(plano.consultas), total=len(plano.consultas),
                  planilha=str(r["planilha"]), celulas=r["celulas"], sr=r["sr"],
                  erros_conferencia=len(erros), avisos_soma=len(r["problemas"]))
    log(f"Fim: {fase}. Erros na conferência: {len(erros)}. Relatório: {rel.name}")
    return 0 if not erros else 1


def regerar_planilha(pasta):
    pasta = Path(pasta)
    pedido = coleta.ler_pedido_da_pasta(pasta)
    plano = planejar(pedido)
    r = planilha.gerar(plano, coleta.carregar_dados(pasta), pasta)
    if r["faltando"]:
        print(f"Faltam {len(r['faltando'])} consultas; rode a coleta primeiro.")
        return 1
    print(f"Planilha: {r['planilha']}  ({r['celulas']} células, {r['sr']} SR)")
    return 0


if __name__ == "__main__":
    sys.exit(rodar(sys.argv[1]))
