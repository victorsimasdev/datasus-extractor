"""
Verifica se a janela mostra TODOS os campos e TODAS as opções de cada formulário do TabNet.

Para cada base (4) e cada formulário (nacional + 27 estados = 112 formulários):
  1. lê o formulário AGORA no site (selects e demais controles);
  2. confere que o site é igual ao que está em opcoes_formularios.json;
  3. monta o formulário como a janela monta (Formulario) e confere, campo a campo, que
     linhas, colunas, conteúdos, períodos e cada filtro têm exatamente as mesmas opções.
"""
import html
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extrator import janela as jp  # noqa: E402

OP = jp.OPCOES
CONTROLES_CONHECIDOS = {"opcoes", "zeradas", "formato", "mostre", "limpa"}


def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def ler(d):
    for t in range(5):
        try:
            req = urllib.request.Request("http://tabnet.datasus.gov.br/cgi/deftohtm.exe?" + d,
                                         headers={"User-Agent": "Mozilla/5.0"})
            txt = urllib.request.urlopen(req, timeout=180).read().decode("windows-1252", "replace")
            break
        except Exception:
            time.sleep(5 * (t + 1))
    else:
        return None, None
    selects = {}
    for attrs, corpo in re.findall(r"<select([^>]*)>(.*?)</select>", txt, re.S | re.I):
        m = re.search(r'name="([^"]+)"', attrs, re.I)
        if m and not m.group(1).startswith("listahidden"):
            selects[html.unescape(m.group(1))] = [[v, limpa(lbl)] for v, lbl in re.findall(
                r'<option[^>]*value="([^"]*)"[^>]*>(.*?)(?=<option|$)', corpo, re.S | re.I)]
    entradas = set()
    for tag in re.findall(r"<input[^>]*>", txt, re.I):
        m = re.search(r'name="?([^"\s>]+)', tag, re.I)
        if m and not re.match(r"(pesqmes|bt_selecionar)\d+", m.group(1)):
            entradas.add(m.group(1))
    return selects, entradas


def campos_json(base, uf):
    if uf is None:
        return OP[base]["nacional"]["campos"]
    e = OP[base]["estadual"]
    return {n: (e["comuns"][n] if n in e["comuns"] else e["por_uf"][uf][n])
            for n in e["ordem"] if n in e["comuns"] or n in e["por_uf"][uf]}


def conferir_janela(base, uf, campos):
    """A janela (Formulario) tem exatamente os campos e opções do formulário?"""
    dados = next(b for b in jp.BASES if b.chave == base)
    f = dados.nacional if uf is None else dados.estadual([uf])
    erros = []
    esperado = {
        "Linha": f.linhas, "Coluna": f.colunas, "Incremento": f.conteudos,
    }
    for nome, lista in esperado.items():
        site = [lbl for _, lbl in campos[nome]]
        if site != lista:
            erros.append(f"{nome}: site {len(site)} x janela {len(lista)}")
    site_per = sorted({lbl for _, lbl in campos["Arquivos"]}, key=jp.chave_periodo)
    if site_per != f.periodos:
        erros.append(f"Arquivos: site {len(site_per)} x janela {len(f.periodos)}")
    filtros_site = {jp.rotulo_filtro(n): ops for n, ops in campos.items() if n.startswith("S")}
    if set(filtros_site) != set(f.filtros):
        erros.append(f"filtros diferentes: só no site {set(filtros_site) - set(f.filtros)}, "
                     f"só na janela {set(f.filtros) - set(filtros_site)}")
    for nome, ops in filtros_site.items():
        site = [lbl for v, lbl in ops if v != jp.TODAS]
        jan = [lbl.split(" · ", 1)[-1] for _, lbl in f.filtros.get(nome, [])]
        if site != jan:
            erros.append(f"filtro {nome}: site {len(site)} opções x janela {len(jan)}")
    n_opcoes = sum(len(v) for k, v in campos.items())
    return erros, len(campos), n_opcoes


def main():
    trabalhos = []
    for base in OP:
        trabalhos.append((base, None, OP[base]["nacional"]["def"]))
        for uf in jp.UFS:
            trabalhos.append((base, uf, OP[base]["estadual"]["def"].format(uf=uf)))
    with ThreadPoolExecutor(4) as ex:
        lidos = list(ex.map(lambda t: ler(t[2]), trabalhos))

    total_erros, campos_total, opcoes_total = 0, 0, 0
    entradas_vistas = set()
    for (base, uf, d), (site, entradas) in zip(trabalhos, lidos):
        onde = f"{base:6s} {('BR' if uf is None else uf.upper()):2s} {d}"
        if site is None:
            print(f"FALHA AO LER  {onde}")
            total_erros += 1
            continue
        entradas_vistas |= entradas
        erros = []
        if site != campos_json(base, uf):
            mud = [n for n in set(site) | set(campos_json(base, uf)) if site.get(n) != campos_json(base, uf).get(n)]
            erros.append(f"site mudou desde o download em: {mud}")
        e2, nc, no = conferir_janela(base, uf, site)
        erros += e2
        campos_total += nc
        opcoes_total += no
        if erros:
            total_erros += len(erros)
            print(f"DIFERENÇA     {onde}")
            for e in erros:
                print("      ", e)
    print()
    print(f"Formulários conferidos: {len(trabalhos)}")
    print(f"Campos de lista conferidos: {campos_total}; opções conferidas: {opcoes_total:,}".replace(",", "."))
    print(f"Outros controles encontrados no site: {sorted(entradas_vistas)}")
    desconhecidos = entradas_vistas - CONTROLES_CONHECIDOS
    print(f"Controles que a janela não conhece: {sorted(desconhecidos) or 'nenhum'}")
    print(f"DIFERENÇAS: {total_erros}")
    return 1 if total_erros or desconhecidos else 0


if __name__ == "__main__":
    sys.exit(main())
