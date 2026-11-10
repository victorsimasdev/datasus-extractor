"""
Execução sem supervisão (a noite inteira):
  1. impede o Windows de entrar em suspensão enquanto roda (sem mudar configurações);
  2. roda coletar_datasus.py até todas as 406 consultas estarem salvas — se cair
     (servidor fora do ar, internet, Chrome), espera e continua de onde parou;
  3. gera a cópia preenchida da planilha e o relatório de conferência;
  4. monta a pasta de entrega (planilha + evidências + relatório, sem código);
  5. grava status_execucao.json com o resultado.

Uso:  python rodar_noite.py
"""
import ctypes
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from coletar_datasus import MESES, UFS

PASTA = Path(__file__).resolve().parent
LOG = PASTA / "execucao.log"
STATUS = PASTA / "status_execucao.json"
ENTREGA = PASTA / "ENTREGA - FA INTERNAÇÕES DATASUS"
LIMITE_HORAS = 12


def log(msg):
    linha = f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {msg}"
    print(linha, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def status(**kw):
    kw["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    STATUS.write_text(json.dumps(kw, ensure_ascii=False, indent=1), encoding="utf-8")


def faltam():
    arq = PASTA / "dados_coletados.json"
    dados = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    chaves = [f"{uf}|{a}-{m:02d}" for uf in UFS for a, m in MESES]
    chaves += [f"BR-{l}|{a}-{m:02d}" for a, m in MESES for l in ("Unidade_da_Federação", "Região")]
    return [c for c in chaves if c not in dados], len(chaves)


def rodar(script, *args):
    with LOG.open("a", encoding="utf-8") as f:
        return subprocess.run([sys.executable, "-u", str(PASTA / script), *args], cwd=PASTA,
                              stdout=f, stderr=subprocess.STDOUT,
                              env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}).returncode


def main():
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: o PC não suspende enquanto este processo estiver vivo
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    inicio = time.time()
    log("Início da execução noturna")

    rodada = 0
    while True:
        pendentes, total = faltam()
        status(fase="coleta", feitas=total - len(pendentes), total=total)
        if not pendentes:
            break
        if time.time() - inicio > LIMITE_HORAS * 3600:
            log(f"Limite de {LIMITE_HORAS}h atingido com {len(pendentes)} consultas pendentes")
            status(fase="erro", motivo="limite de tempo", pendentes=pendentes)
            sys.exit(1)
        rodada += 1
        log(f"Rodada de coleta {rodada}: faltam {len(pendentes)} de {total}")
        if rodar("coletar_datasus.py") != 0:
            log("Coleta interrompida (provável instabilidade do DATASUS); retomando em 5 minutos")
            time.sleep(300)
    log("Coleta completa")

    status(fase="planilha")
    relatorio = PASTA / "RELATÓRIO DE CONFERÊNCIA.txt"
    with relatorio.open("w", encoding="utf-8") as f:
        f.write(f"Gerado em {datetime.now():%d/%m/%Y %H:%M:%S}\n\n")
    saida = subprocess.run([sys.executable, "-u", str(PASTA / "preencher_planilha.py")], cwd=PASTA,
                           capture_output=True, text=True, encoding="utf-8",
                           env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    with relatorio.open("a", encoding="utf-8") as f:
        f.write(saida.stdout + saida.stderr)
    log("Planilha:\n" + saida.stdout + saida.stderr)
    if saida.returncode != 0:
        status(fase="erro", motivo="falha ao gerar a planilha")
        sys.exit(1)

    status(fase="entrega")
    if ENTREGA.exists():
        shutil.rmtree(ENTREGA)
    ENTREGA.mkdir()
    shutil.copy2(PASTA / "FA - INTERNAÇÕES - preenchida.xlsx", ENTREGA)
    shutil.copy2(relatorio, ENTREGA)
    shutil.copytree(PASTA / "evidencias", ENTREGA / "evidencias")
    n_arquivos = sum(1 for p in (ENTREGA / "evidencias").rglob("*") if p.is_file())

    def numero(rotulo):
        for l in saida.stdout.splitlines():
            if l.startswith(rotulo):
                return int(l.split(":")[-1].split()[0])
        return None

    status(fase="concluido",
           consultas=total,
           arquivos_evidencia=n_arquivos,
           conferidos_identicos=numero("Estado/mês conferidos"),
           problemas_conferencia=numero("Problemas nas conferências"),
           diferencas_digitado=numero("Diferenças com o que já estava digitado"),
           pasta_entrega=str(ENTREGA))
    log(f"Concluído. Pasta de entrega: {ENTREGA.name} ({n_arquivos} arquivos de evidência)")


if __name__ == "__main__":
    main()
