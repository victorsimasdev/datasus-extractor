"""
Teste de regressão contra o site de verdade: roda os pedidos de tests/regressao/pedidos (um pequeno por
base, em períodos antigos e já fechados no DATASUS) e compara cada célula da planilha com o resultado
conferido guardado em tests/regressao/esperado.

Pega: mudança no site que quebra a coleta, erro novo na leitura dos números, na montagem da planilha
ou na conferência pelos PDFs, e executável (.exe) quebrado.

Uso:
  python ferramentas/regressao.py                       roda e compara (código 1 se algo mudou)
  python ferramentas/regressao.py --exe dist/ExtratorDATASUS.exe   o mesmo, pelo executável
  python ferramentas/regressao.py --gravar              roda e grava o resultado como o novo esperado
  python ferramentas/regressao.py --so sih,sim          só alguns pedidos
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PEDIDOS = RAIZ / "tests" / "regressao" / "pedidos"
ESPERADO = RAIZ / "tests" / "regressao" / "esperado"
ABAS_DE_APOIO = {"EVIDÊNCIAS", "_MAPA"}


def ler_planilha(arquivo):
    """{aba: [[valores da linha], ...]} das abas de dados (sem EVIDÊNCIAS e _MAPA)."""
    import openpyxl

    wb = openpyxl.load_workbook(arquivo, data_only=True)
    saida = {}
    for ws in wb.worksheets:
        if ws.title in ABAS_DE_APOIO:
            continue
        linhas = [[c for c in linha] for linha in ws.iter_rows(values_only=True)]
        while linhas and not any(v not in (None, "") for v in linhas[-1]):
            linhas.pop()
        saida[ws.title] = linhas
    return saida


def diferencas(esperado, obtido, limite=10):
    """Lista legível das células diferentes (no máximo `limite`)."""
    out = []
    for aba in sorted(set(esperado) | set(obtido)):
        if aba not in obtido:
            out.append(f"aba {aba!r} sumiu")
            continue
        if aba not in esperado:
            out.append(f"aba nova {aba!r}")
            continue
        a, b = esperado[aba], obtido[aba]
        for i in range(max(len(a), len(b))):
            la = a[i] if i < len(a) else []
            lb = b[i] if i < len(b) else []
            for j in range(max(len(la), len(lb))):
                va = la[j] if j < len(la) else None
                vb = lb[j] if j < len(lb) else None
                if va != vb:
                    out.append(f"{aba}!{_coluna(j)}{i + 1}: esperado {va!r}, veio {vb!r}")
                    if len(out) >= limite:
                        return out
    return out


def _coluna(j):
    nome = ""
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        nome = chr(65 + r) + nome
    return nome


def rodar_pedido(arquivo, pasta, exe=None):
    """Roda um pedido numa pasta isolada. Devolve (código de saída, planilha ou None, fim do log)."""
    pedido = json.loads(arquivo.read_text(encoding="utf-8"))
    pedido["saida"]["pasta"] = str(pasta / "saida")
    copia = pasta / arquivo.name
    copia.write_text(json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
    cmd = [str(exe), "rodar", str(copia)] if exe else [sys.executable, "-m", "extrator", "rodar", str(copia)]
    env = {**os.environ, "DATASUS_EXTRATOR_HOME": str(pasta / "home"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
    planilhas = sorted((pasta / "saida").glob("*/*.xlsx"))
    log = (r.stdout + r.stderr).strip().splitlines()[-6:]
    return r.returncode, (planilhas[0] if planilhas else None), log


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gravar", action="store_true", help="grava o resultado como o novo esperado")
    p.add_argument("--exe", help="caminho do ExtratorDATASUS.exe (em vez de python -m extrator)")
    p.add_argument("--so", help="só estes pedidos, separados por vírgula (ex.: sih,sim)")
    a = p.parse_args(argv)
    if a.exe:
        a.exe = Path(a.exe).resolve()
        if not a.exe.is_file():
            sys.exit(f"Executável não encontrado: {a.exe}")
    escolhidos = set(a.so.split(",")) if a.so else None
    pedidos = [f for f in sorted(PEDIDOS.glob("*.json")) if not escolhidos or f.stem in escolhidos]
    if not pedidos:
        sys.exit("Nenhum pedido de regressão encontrado.")
    falhas = 0
    with tempfile.TemporaryDirectory(prefix="regressao-") as tmp:
        for arquivo in pedidos:
            pasta = Path(tmp) / arquivo.stem
            pasta.mkdir()
            codigo, planilha, log = rodar_pedido(arquivo, pasta, a.exe)
            if codigo != 0 or not planilha:
                falhas += 1
                print(f"FALHOU      {arquivo.stem}: código {codigo}" + ("" if planilha else ", sem planilha"))
                for linha in log:
                    print("            ", linha)
                continue
            obtido = ler_planilha(planilha)
            esperado_arq = ESPERADO / f"{arquivo.stem}.json"
            if a.gravar:
                ESPERADO.mkdir(parents=True, exist_ok=True)
                esperado_arq.write_text(json.dumps(obtido, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                print(f"GRAVADO     {arquivo.stem}: {sum(len(v) for v in obtido.values())} linhas")
                continue
            if not esperado_arq.is_file():
                falhas += 1
                print(f"SEM ESPERADO {arquivo.stem}: rode com --gravar")
                continue
            dif = diferencas(json.loads(esperado_arq.read_text(encoding="utf-8")), obtido)
            if dif:
                falhas += 1
                print(f"DIFERENÇA   {arquivo.stem}")
                for d in dif:
                    print("            ", d)
            else:
                print(f"OK          {arquivo.stem}")
    print(f"\nPedidos: {len(pedidos)}; com problema: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
