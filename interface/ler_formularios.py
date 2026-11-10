"""
Lê no TabNet os formulários nacionais e os 27 estaduais de cada base e grava as opções de cada
campo em opcoes_formularios.json, que a janela de pedido usa.

Uso:  python ler_formularios.py [arquivo de saída]
"""
import html, json, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UFS = "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to".split()
BASES = {
    "sih": ("Internações hospitalares", "SIH/SUS - Morbidade hospitalar, por local de internação", "sih/cnv/niuf.def", "sih/cnv/ni{uf}.def"),
    "sim": ("Mortalidade", "SIM - Óbitos por residência ou ocorrência (CID-10, desde 1996)", "sim/cnv/obt10uf.def", "sim/cnv/obt10{uf}.def"),
    "sinasc": ("Nascidos vivos", "SINASC - Nascimentos por residência da mãe ou ocorrência", "sinasc/cnv/nvuf.def", "sinasc/cnv/nv{uf}.def"),
    "sia": ("Produção ambulatorial", "SIA/SUS - Procedimentos ambulatoriais, por local de atendimento", "sia/cnv/qauf.def", "sia/cnv/qa{uf}.def"),
}

def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()

def ler(d):
    for tentativa in range(5):
        try:
            req = urllib.request.Request("http://tabnet.datasus.gov.br/cgi/deftohtm.exe?" + d, headers={"User-Agent": "Mozilla/5.0"})
            t = urllib.request.urlopen(req, timeout=180).read().decode("windows-1252", "replace")
            break
        except Exception as e:
            print("  tentativa", tentativa + 1, d, e, flush=True)
            time.sleep(5 * (tentativa + 1))
    else:
        raise RuntimeError(d)
    campos = {}
    for attrs, corpo in re.findall(r"<select([^>]*)>(.*?)</select>", t, re.S | re.I):
        m = re.search(r'name="([^"]+)"', attrs, re.I)
        if m and not m.group(1).startswith("listahidden"):
            campos[html.unescape(m.group(1))] = [[v, limpa(l)] for v, l in re.findall(
                r'<option[^>]*value="([^"]*)"[^>]*>(.*?)(?=<option|$)', corpo, re.S | re.I)]
    if "Linha" not in campos:
        raise RuntimeError(f"formulário sem campos: {d}")
    return campos

saida = {}
with ThreadPoolExecutor(4) as ex:
    for k, (nome, desc, d_nac, d_uf) in BASES.items():
        nac = ler(d_nac)
        estados = dict(zip(UFS, ex.map(lambda uf: ler(d_uf.format(uf=uf)), UFS)))
        nomes = []
        for c in estados.values():
            nomes += [n for n in c if n not in nomes]
        comuns, por_uf = {}, {uf: {} for uf in UFS}
        for n in nomes:
            vals = [estados[uf].get(n) for uf in UFS]
            if all(v == vals[0] for v in vals):
                comuns[n] = vals[0]
            else:
                for uf in UFS:
                    if estados[uf].get(n) is not None:
                        por_uf[uf][n] = estados[uf][n]
        saida[k] = {"nome": nome, "descricao": desc,
                    "nacional": {"def": d_nac, "campos": nac},
                    "estadual": {"def": d_uf, "ordem": nomes, "comuns": comuns, "por_uf": por_uf}}
        print(k, "nacional:", len(nac), "campos | estadual:", len(nomes), "campos,",
              len(comuns), "iguais em todos os estados", flush=True)

destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "opcoes_formularios.json"
destino.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
print("gravado", destino, destino.stat().st_size // 1024, "KB")
