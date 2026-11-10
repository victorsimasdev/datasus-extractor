"""
Formulários do TabNet: leitura das opções no site e acesso a elas pelo restante do extrator.

As opções de todos os campos (linhas, colunas, conteúdos, períodos e filtros) de cada base ficam
em opcoes_formularios.json, gravado por `python -m extrator atualizar-opcoes`. Campos que só
existem no formulário de cada estado (município, região de saúde...) ficam separados por estado.
"""
import html
import json
import re
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ARQUIVO_OPCOES = Path(__file__).resolve().parent / "opcoes_formularios.json"
URL = "http://tabnet.datasus.gov.br/cgi"
TODAS = "TODAS_AS_CATEGORIAS__"
NAO_ATIVA = "--Não-Ativa--"
UFS = {"ac": "Acre", "al": "Alagoas", "am": "Amazonas", "ap": "Amapá", "ba": "Bahia", "ce": "Ceará",
       "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás", "ma": "Maranhão", "mg": "Minas Gerais",
       "ms": "Mato Grosso do Sul", "mt": "Mato Grosso", "pa": "Pará", "pb": "Paraíba", "pe": "Pernambuco",
       "pi": "Piauí", "pr": "Paraná", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte", "ro": "Rondônia",
       "rr": "Roraima", "rs": "Rio Grande do Sul", "sc": "Santa Catarina", "se": "Sergipe", "sp": "São Paulo",
       "to": "Tocantins"}
BASES = {
    "sih": ("Internações hospitalares", "SIH/SUS - Morbidade hospitalar, por local de internação",
            "sih/cnv/niuf.def", "sih/cnv/ni{uf}.def"),
    "sim": ("Mortalidade", "SIM - Óbitos por residência ou ocorrência (CID-10, desde 1996)",
            "sim/cnv/obt10uf.def", "sim/cnv/obt10{uf}.def"),
    "sinasc": ("Nascidos vivos", "SINASC - Nascimentos por residência da mãe ou ocorrência",
               "sinasc/cnv/nvuf.def", "sinasc/cnv/nv{uf}.def"),
    "sia": ("Produção ambulatorial", "SIA/SUS - Procedimentos ambulatoriais, por local de atendimento",
            "sia/cnv/qauf.def", "sia/cnv/qa{uf}.def"),
}


def limpa(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def normaliza(s):
    """Para comparar rótulos: sem acentos, minúsculo, espaços simples."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def rotulo_filtro(nome_select):
    """'SFaixa_Etária_1' -> 'Faixa Etária 1' (o nome que aparece para o usuário e no resultado)."""
    return re.sub(r"\s+", " ", nome_select[1:].replace("_", " ")).strip()


# ---------------------------------------------------------------- leitura no site
def ler_formulario(caminho_def, tentativas=5):
    """Lê um formulário (deftohtm.exe?caminho) e devolve {nome do select: [[valor, rótulo], ...]}."""
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(f"{URL}/deftohtm.exe?{caminho_def}", headers={"User-Agent": "Mozilla/5.0"})
            texto = urllib.request.urlopen(req, timeout=180).read().decode("windows-1252", "replace")
            break
        except Exception as e:
            print(f"  tentativa {tentativa + 1} em {caminho_def}: {e}", flush=True)
            time.sleep(5 * (tentativa + 1))
    else:
        raise RuntimeError(f"não consegui ler {caminho_def}")
    campos = {}
    for attrs, corpo in re.findall(r"<select([^>]*)>(.*?)</select>", texto, re.S | re.I):
        m = re.search(r'name="([^"]+)"', attrs, re.I)
        if m and not m.group(1).startswith("listahidden"):
            campos[html.unescape(m.group(1))] = [[v, limpa(lbl)] for v, lbl in re.findall(
                r'<option[^>]*value="([^"]*)"[^>]*>(.*?)(?=<option|$)', corpo, re.S | re.I)]
    if "Linha" not in campos:
        raise RuntimeError(f"formulário sem campos: {caminho_def}")
    return campos


def atualizar_opcoes(destino=ARQUIVO_OPCOES):
    """Lê no site os formulários nacional e dos 27 estados de cada base e grava o JSON de opções."""
    from .comum import gravar_json

    saida = {}
    with ThreadPoolExecutor(4) as ex:
        for k, (nome, desc, d_nac, d_uf) in BASES.items():
            nac = ler_formulario(d_nac)
            estados = dict(zip(UFS, ex.map(lambda uf: ler_formulario(d_uf.format(uf=uf)), UFS)))
            ordem = []
            for c in estados.values():
                ordem += [n for n in c if n not in ordem]
            comuns, por_uf = {}, {uf: {} for uf in UFS}
            for n in ordem:
                vals = [estados[uf].get(n) for uf in UFS]
                if all(v == vals[0] for v in vals):
                    comuns[n] = vals[0]
                else:
                    for uf in UFS:
                        if estados[uf].get(n) is not None:
                            por_uf[uf][n] = estados[uf][n]
            saida[k] = {"nome": nome, "descricao": desc,
                        "nacional": {"def": d_nac, "campos": nac},
                        "estadual": {"def": d_uf, "ordem": ordem, "comuns": comuns, "por_uf": por_uf}}
            print(f"{k}: nacional {len(nac)} campos | estadual {len(ordem)} campos", flush=True)
    gravar_json(destino, saida)
    return destino


# ---------------------------------------------------------------- acesso às opções
_cache = None


def carregar_opcoes(caminho=ARQUIVO_OPCOES):
    global _cache
    if _cache is None or caminho != ARQUIVO_OPCOES:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if caminho != ARQUIVO_OPCOES:
            return dados
        _cache = dados
    return _cache


class Formulario:
    """Um formulário concreto do TabNet: o nacional de uma base, ou o de um estado."""

    def __init__(self, base, uf=None, opcoes=None):
        op = (opcoes or carregar_opcoes())[base]
        self.base, self.uf = base, uf
        if uf is None:
            self.caminho_def = op["nacional"]["def"]
            self.campos = op["nacional"]["campos"]
        else:
            e = op["estadual"]
            self.caminho_def = e["def"].format(uf=uf)
            self.campos = {n: (e["comuns"][n] if n in e["comuns"] else e["por_uf"][uf][n])
                           for n in e["ordem"] if n in e["comuns"] or n in e["por_uf"][uf]}
        self.filtros = {rotulo_filtro(n): n for n in self.campos if n.startswith("S")}

    def _valor(self, campo, rotulo):
        for v, lbl in self.campos[campo]:
            if normaliza(lbl) == normaliza(rotulo):
                return v
        return None

    def valor_linha(self, rotulo):
        return self._valor("Linha", rotulo)

    def valor_coluna(self, rotulo):
        return NAO_ATIVA if rotulo is None else self._valor("Coluna", rotulo)

    def valores_conteudo(self, rotulos):
        return [self._valor("Incremento", r) for r in rotulos]

    def arquivo(self, periodo):
        """Rótulo do período ('Jul/2025', '2024') -> arquivo do formulário ('niuf2507.dbf'), ou None."""
        return self._valor("Arquivos", periodo)

    def select_do_filtro(self, rotulo):
        for r, nome in self.filtros.items():
            if normaliza(r) == normaliza(rotulo):
                return nome
        return None

    def rotulo_opcao(self, select, valor):
        return next((lbl for v, lbl in self.campos[select] if v == valor), None)

    def coluna_do_filtro(self, rotulo_filtro_):
        """Se o campo do filtro também existe como Coluna, devolve o rótulo da coluna."""
        return next((lbl for _, lbl in self.campos["Coluna"] if normaliza(lbl) == normaliza(rotulo_filtro_)), None)

    def categorias(self, rotulo_campo):
        """Opções (sem 'Todas as categorias') do filtro com esse nome, se existir: [(valor, rótulo)]."""
        sel = self.select_do_filtro(rotulo_campo)
        return [(v, lbl) for v, lbl in self.campos[sel] if v != TODAS] if sel else None
