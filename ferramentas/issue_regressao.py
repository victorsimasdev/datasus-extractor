"""
Monta o texto da issue quando o workflow de regressão falha (usado por .github/workflows/regressao.yml).

Lê o resultado de cada job (JSON de `needs` do GitHub Actions) e os relatórios que os jobs guardaram
(saída completa de ferramentas/regressao.py e ferramentas/verificar_formularios.py) e escreve um
Markdown com: o que falhou, os trechos que importam (células diferentes, formulários mudados), o que
fazer e o registro completo.

Uso:
  python ferramentas/issue_regressao.py --resultados '<json de needs>' --relatorios PASTA --url URL \
      --saida corpo.md
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOBS = {
    "coleta": ("Coleta no site", "relatorio-coleta"),
    "formularios": ("Formulários do site", "relatorio-formularios"),
    "executavel": ("Executável (.exe)", "relatorio-executavel"),
}
ICONES = {"success": "✅ passou", "failure": "❌ falhou", "cancelled": "⚠️ cancelado", "skipped": "➖ não rodou"}
MARCAS = re.compile(r"^(FALHOU|DIFERENÇA |SEM ESPERADO|FALHA AO LER|Traceback)")
LIMITE_REGISTRO = 15000  # caracteres por relatório (o corpo da issue aceita até 65 mil)

O_QUE_FAZER = """### O que fazer

1. Abra o registro completo de cada job com problema (abaixo ou no link da execução).
2. Identifique o caso:
   - **Site fora do ar ou lento** (tentativas esgotadas, timeout): rode de novo pela aba Actions → Regressão → *Run workflow*. Se passar, feche esta issue.
   - **DATASUS revisou um dado antigo** (poucas células diferentes, o resto igual): confira o valor no site e, se estiver certo, rode `python ferramentas/regressao.py --gravar`, revise o diff de `tests/regressao/esperado` e abra um PR `test:`.
   - **O site mudou** (formulário com campos ou opções diferentes, coleta sem planilha): rode `python -m extrator atualizar-opcoes` e `python ferramentas/verificar_formularios.py`; se a leitura quebrou, corrija em `extrator/` com um PR `fix:` (gera versão de correção).
   - **Executável quebrado** e coleta normal passando: problema no empacotamento (`empacotamento/`, `requirements-build.txt`).
3. Feche a issue quando a regressão voltar a passar."""


def trechos_importantes(texto, limite=40):
    """Linhas marcadas (FALHOU, DIFERENÇA...) com as linhas recuadas logo abaixo delas."""
    linhas = texto.splitlines()
    out, dentro = [], False
    for linha in linhas:
        if MARCAS.match(linha.strip()):
            out.append(linha.rstrip())
            dentro = True
        elif dentro and (linha.startswith((" ", "\t")) and linha.strip()):
            out.append(linha.rstrip())
        else:
            dentro = False
        if len(out) >= limite:
            out.append("…")
            break
    resumo = [linha for linha in linhas if linha.startswith(("Pedidos:", "DIFERENÇAS:", "Formulários conferidos:"))]
    return out + resumo


def ler_relatorio(pasta, nome):
    arquivos = sorted(Path(pasta).glob(f"{nome}/*.txt")) + sorted(Path(pasta).glob(f"{nome}.txt"))
    return "\n".join(a.read_text(encoding="utf-8", errors="replace") for a in arquivos)


def montar_corpo(resultados, pasta, url, quando):
    linhas = [f"A regressão contra o site do TabNet falhou em **{quando:%d/%m/%Y às %H:%M}** (horário de Brasília).",
              "", f"Execução: {url}", "", "| Teste | Resultado |", "|---|---|"]
    for job, (titulo, _) in JOBS.items():
        r = resultados.get(job, {}).get("result", "skipped")
        linhas.append(f"| {titulo} | {ICONES.get(r, r)} |")
    for job, (titulo, relatorio) in JOBS.items():
        r = resultados.get(job, {}).get("result")
        if r in ("success", "skipped", None):
            continue
        texto = ler_relatorio(pasta, relatorio)
        linhas += ["", f"## {titulo}", ""]
        if not texto.strip():
            linhas.append("Sem relatório: o job parou antes de rodar o teste (instalação, timeout ou cancelamento). "
                          "Veja o registro na execução.")
            continue
        trechos = trechos_importantes(texto)
        if trechos:
            linhas += ["O que deu errado:", "", "```", *trechos, "```"]
        registro = texto if len(texto) <= LIMITE_REGISTRO else "…\n" + texto[-LIMITE_REGISTRO:]
        linhas += ["", "<details><summary>Registro completo</summary>", "", "```", registro.rstrip(), "```", "",
                   "</details>"]
    linhas += ["", O_QUE_FAZER]
    return "\n".join(linhas) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultados", required=True, help="JSON de needs do GitHub Actions")
    p.add_argument("--relatorios", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--saida", default="corpo.md")
    a = p.parse_args(argv)
    quando = datetime.now(timezone(timedelta(hours=-3)))
    corpo = montar_corpo(json.loads(a.resultados), a.relatorios, a.url, quando)
    Path(a.saida).write_text(corpo, encoding="utf-8")
    print(f"titulo=Regressão falhou em {quando:%d/%m/%Y}")


if __name__ == "__main__":
    main()
