"""
Execução sem supervisão da coleta por perfil (sexo, faixa etária, cor/raça):
  1. impede o Windows de entrar em suspensão enquanto roda (sem mudar configurações);
  2. roda coletar_perfil.py até todas as 5.684 consultas estarem salvas — se cair
     (servidor fora do ar, internet, Chrome), espera e continua de onde parou;
  3. monta a pasta de entrega (entrega anterior + evidências novas) e grava nela a planilha
     com as colunas F-S (preencher_perfil.py);
  4. roda as conferências independentes pelos PDFs (conferir_perfil.py e conferir_evidencias.py);
  5. grava status_perfil.json com o resultado.

Uso:  python rodar_perfil.py
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from coletar_perfil import chave, todos_casos, todos_nacionais
from comum import DadosCorrompidos, gravar_json, impedir_suspensao, ler_json

PASTA = Path(__file__).resolve().parent
LOG = PASTA / "execucao_perfil.log"
STATUS = PASTA / "status_perfil.json"
ENTREGA = PASTA / "ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS"
ANTERIOR = PASTA / "ENTREGA ANTERIOR (Jul-2025 a Ago-2026)"
LIMITE_HORAS = 120
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def log(msg):
    linha = f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {msg}"
    print(linha, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def status(**kw):
    kw["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    gravar_json(STATUS, kw)


def faltam():
    # um JSON corrompido NÃO é tratado como vazio: levanta DadosCorrompidos e a execução para
    dados = ler_json(PASTA / "dados_perfil.json", {})
    chaves = [chave(*c) for c in todos_casos() + todos_nacionais()]
    return [c for c in chaves if c not in dados], len(chaves)


def rodar(script, *args):
    with LOG.open("a", encoding="utf-8") as f:
        return subprocess.run([sys.executable, "-u", str(PASTA / script), *args], cwd=PASTA,
                              stdout=f, stderr=subprocess.STDOUT, env=ENV).returncode


def rodar_capturando(script, *args):
    s = subprocess.run([sys.executable, "-u", str(PASTA / script), *args], cwd=PASTA,
                       capture_output=True, text=True, encoding="utf-8", env=ENV)
    return s.returncode, s.stdout + s.stderr


def main():
    impedir_suspensao()
    inicio = time.time()
    log("Início da execução (coleta por perfil)")

    rodada = 0
    while True:
        try:
            pendentes, total = faltam()
        except DadosCorrompidos as e:
            log(f"ERRO: {e}. Execução interrompida para não sobrescrever a coleta.")
            status(fase="erro", motivo=str(e))
            sys.exit(1)
        status(fase="coleta", feitas=total - len(pendentes), total=total)
        if not pendentes:
            break
        if time.time() - inicio > LIMITE_HORAS * 3600:
            log(f"Limite de {LIMITE_HORAS}h atingido com {len(pendentes)} consultas pendentes")
            status(fase="erro", motivo="limite de tempo", pendentes=len(pendentes))
            sys.exit(1)
        rodada += 1
        log(f"Rodada de coleta {rodada}: faltam {len(pendentes)} de {total}")
        if rodar("coletar_perfil.py") != 0:
            log("Coleta interrompida (provável instabilidade do DATASUS); retomando em 5 minutos")
            time.sleep(300)
    log("Coleta completa")

    # entrega = entrega anterior (planilha B-E + evidências) + evidências novas; a planilha é regravada com F-S
    status(fase="entrega")
    if ENTREGA.exists():
        shutil.rmtree(ENTREGA)
    shutil.copytree(ANTERIOR, ENTREGA, ignore=shutil.ignore_patterns("desktop.ini"))
    shutil.copytree(PASTA / "evidencias_perfil", ENTREGA / "evidencias_perfil")

    status(fase="planilha")
    relatorio = ENTREGA / "RELATÓRIO DE CONFERÊNCIA - PERFIL.txt"
    cod, saida = rodar_capturando("preencher_perfil.py")
    relatorio.write_text(f"Gerado em {datetime.now():%d/%m/%Y %H:%M:%S}\n\n"
                         f"== Geração das colunas H-U ==\n{saida}\n", encoding="utf-8")
    log("Planilha:\n" + saida)
    if cod != 0:
        status(fase="erro", motivo="falha ou problema ao gerar a planilha (ver relatório)")
        sys.exit(1)

    status(fase="conferencia")
    erros = {}
    for script, rotulo in (("conferir_perfil.py", "colunas H-U"), ("conferir_evidencias.py", "colunas B-E")):
        cod, conf = rodar_capturando(script, str(ENTREGA))
        with relatorio.open("a", encoding="utf-8") as f:
            f.write(f"== Conferência independente {rotulo} (texto dos PDFs x planilha entregue) ==\n{conf}\n")
        log(f"Conferência {rotulo}:\n" + conf)
        erros[rotulo] = next((int(l.split(":")[1]) for l in conf.splitlines() if l.startswith("ERROS:")), None)
        if cod != 0:
            erros[rotulo] = erros[rotulo] or -1
    n_arquivos = sum(1 for p in (ENTREGA / "evidencias_perfil").rglob("*") if p.is_file())
    ok = all(e == 0 for e in erros.values())
    status(fase="concluido" if ok else "erro", motivo=None if ok else f"conferência com erros: {erros}",
           consultas=total, arquivos_evidencia_novos=n_arquivos, erros_conferencia=erros,
           pasta_entrega=str(ENTREGA))
    log(f"Fim. Erros nas conferências: {erros}. Pasta de entrega: {ENTREGA.name}")


if __name__ == "__main__":
    main()
