"""
Versão e notas de release a partir dos commits (usado pelo workflow .github/workflows/release.yml).

Regras (versionamento semântico, uma subida por release, pela mudança mais forte):
- `release:`, `tipo!:` ou `BREAKING CHANGE` no corpo -> sobe o primeiro número (2.4.3 -> 3.0.0)
- `feat:`                                           -> sobe o do meio        (2.4.3 -> 2.5.0)
- `fix:`                                            -> sobe o último         (2.4.3 -> 2.4.4)
- qualquer commit que mude o requirements.txt        -> sobe o último (dependência do programa, ex.: PRs
                                                        do Dependabot com correções de segurança)
- docs, chore, ci, test, refactor e o resto          -> não geram versão (requirements-dev.txt e actions
                                                        do GitHub não chegam a quem usa o programa)

Se a versão do pyproject.toml já estiver à frente da última tag (subida à mão), vale a maior das duas.

Uso:
  python ferramentas/release.py calcular [--forcar X.Y.Z]   imprime "versao=X.Y.Z" (vazio se não há release)
  python ferramentas/release.py aplicar X.Y.Z               grava a versão nos arquivos e as notas em notas.md
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYPROJECT = RAIZ / "pyproject.toml"
INIT = RAIZ / "extrator" / "__init__.py"
CHANGELOG = RAIZ / "CHANGELOG.md"
NAO_LANCADO = "## [Não lançado]"

PESO = {None: 0, "dependencias": 1, "correcao": 1, "menor": 2, "maior": 3}
DEPENDENCIAS_DO_PROGRAMA = "requirements.txt"
RE_ASSUNTO = re.compile(r"^(?P<tipo>[a-z]+)(?:\([^)]*\))?(?P<quebra>!)?:\s*(?P<texto>.+)$")
RE_BUMP = re.compile(r"^bump (?P<pacote>\S+) from (?P<de>\S+) to (?P<para>\S+)", re.I)
RE_VERSAO = re.compile(r"^\d+\.\d+\.\d+$")
SECOES = (("maior", "Mudanças incompatíveis"), ("menor", "Adicionado"), ("correcao", "Corrigido"),
          ("dependencias", "Dependências"))


def classificar(assunto, corpo="", arquivos=()):
    """Quanto um commit sobe a versão: "maior", "menor", "correcao", "dependencias" ou None."""
    m = RE_ASSUNTO.match(assunto.strip())
    nivel = None
    if m:
        if m["tipo"] == "release" or m["quebra"] or re.search(r"^BREAKING[ -]CHANGE:", corpo or "", re.M):
            nivel = "maior"
        else:
            nivel = {"feat": "menor", "fix": "correcao"}.get(m["tipo"])
    if nivel is None and DEPENDENCIAS_DO_PROGRAMA in arquivos:
        nivel = "dependencias"
    return nivel


def _desempacotar(commit):
    """Commit como (assunto, corpo) ou (assunto, corpo, arquivos)."""
    assunto, corpo, *resto = commit
    return assunto, corpo, tuple(resto[0]) if resto else ()


def _texto(assunto):
    """Texto da nota: sem o prefixo; "bump X from A to B" vira "X A → B"."""
    m = RE_ASSUNTO.match(assunto.strip())
    texto = m["texto"] if m else assunto.strip()
    b = RE_BUMP.match(texto)
    if b:
        return f"{b['pacote']} {b['de']} → {b['para']}"
    return texto[:1].upper() + texto[1:]


def proxima(versao, nivel):
    """Próxima versão; os números à direita do que subiu voltam a zero."""
    maior, menor, correcao = (int(x) for x in versao.split("."))
    if nivel == "maior":
        return f"{maior + 1}.0.0"
    if nivel == "menor":
        return f"{maior}.{menor + 1}.0"
    if nivel in ("correcao", "dependencias"):
        return f"{maior}.{menor}.{correcao + 1}"
    return None


def nivel_da_release(commits):
    """A mudança mais forte entre os commits [(assunto, corpo[, arquivos]), ...]."""
    niveis = [classificar(*_desempacotar(c)) for c in commits]
    return max(niveis, key=PESO.get, default=None)


def notas_dos_commits(commits):
    """Notas em Markdown, agrupadas como no CHANGELOG. Só entram commits que sobem a versão."""
    grupos = {n: [] for n, _ in SECOES}
    for commit in commits:
        assunto, corpo, arquivos = _desempacotar(commit)
        nivel = classificar(assunto, corpo, arquivos)
        if nivel:
            grupos[nivel].append(_texto(assunto))
    blocos = [f"### {titulo}\n" + "\n".join(f"- {t}" for t in grupos[n]) for n, titulo in SECOES if grupos[n]]
    return "\n\n".join(blocos)


# ---------------------------------------------------------------- git
def _git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def ultima_tag():
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*").strip()
    except subprocess.CalledProcessError:
        return None


def commits_desde(tag):
    faixa = f"{tag}..HEAD" if tag else "HEAD"
    saida = _git("log", faixa, "--no-merges", "--name-only", "--format=%x1e%s%x1f%b%x1f")
    commits = []
    for bloco in saida.split("\x1e"):
        if not bloco.strip():
            continue
        assunto, corpo, nomes = bloco.split("\x1f", 2)
        commits.append((assunto, corpo.strip(), tuple(n for n in nomes.split("\n") if n.strip())))
    return commits


# ---------------------------------------------------------------- arquivos
def secao(texto, titulo_inicio):
    """(início, fim) da seção do CHANGELOG cujo título começa com titulo_inicio; None se não existe."""
    m = re.search(rf"^{re.escape(titulo_inicio)}.*$", texto, re.M)
    if not m:
        return None
    prox = re.search(r"^## ", texto[m.end():], re.M)
    return m.start(), (m.end() + prox.start()) if prox else len(texto)


def atualizar_changelog(texto, versao, commits, hoje):
    """Devolve (changelog novo, notas da release).

    Ordem de preferência das notas: seção já escrita para a versão ("## [X.Y.Z]"), depois o que
    estiver em "Não lançado" (os dois juntos se houver), e por fim as notas geradas dos commits.
    """
    titulo = f"## [{versao}] - {hoje:%Y-%m-%d}"
    partes = []
    for inicio in (f"## [{versao}]", NAO_LANCADO):
        pos = secao(texto, inicio)
        if pos:
            corpo = texto[pos[0]:pos[1]].split("\n", 1)[1].strip() if "\n" in texto[pos[0]:pos[1]] else ""
            partes.append((pos, corpo))
    # tira as seções antigas (de trás para frente para não deslocar posições)
    for (ini, fim), _ in sorted(partes, key=lambda p: p[0][0], reverse=True):
        texto = texto[:ini] + texto[fim:]
    manual = [corpo for _, corpo in sorted(partes, key=lambda p: p[0][0]) if corpo]
    notas = "\n\n".join(manual) if manual else notas_dos_commits(commits)
    nova = f"{NAO_LANCADO}\n\n{titulo}\n\n{notas}\n\n"
    pos = re.search(r"^## ", texto, re.M)
    texto = texto[:pos.start()] + nova + texto[pos.start():] if pos else texto.rstrip("\n") + "\n\n" + nova
    return texto.rstrip("\n") + "\n", notas


def gravar_versao(versao):
    t = PYPROJECT.read_text(encoding="utf-8")
    PYPROJECT.write_text(re.sub(r'^version = "[^"]*"', f'version = "{versao}"', t, count=1, flags=re.M),
                         encoding="utf-8")
    t = INIT.read_text(encoding="utf-8")
    INIT.write_text(re.sub(r'^__version__ = "[^"]*"', f'__version__ = "{versao}"', t, count=1, flags=re.M),
                    encoding="utf-8")


# ---------------------------------------------------------------- comandos
def _tupla(versao):
    return tuple(int(x) for x in versao.split("."))


def versao_no_codigo():
    m = re.search(r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    return m[1] if m and RE_VERSAO.match(m[1]) else None


def escolher(ultima, calculada, no_codigo):
    """Versão da release: a calculada pelos commits ou a do código, se esta estiver à frente."""
    candidatas = [v for v in (calculada, no_codigo) if v and _tupla(v) > _tupla(ultima)]
    return max(candidatas, key=_tupla, default="")


def calcular(forcar=""):
    if forcar:
        if not RE_VERSAO.match(forcar):
            sys.exit(f"Versão inválida: {forcar!r} (use X.Y.Z)")
        return forcar
    tag = ultima_tag()
    atual = tag.lstrip("v") if tag else "0.0.0"
    return escolher(atual, proxima(atual, nivel_da_release(commits_desde(tag))), versao_no_codigo())


def aplicar(versao, saida_notas):
    tag = ultima_tag()
    if tag == f"v{versao}" or _git("tag", "--list", f"v{versao}").strip():
        sys.exit(f"A tag v{versao} já existe.")
    gravar_versao(versao)
    texto, notas = atualizar_changelog(CHANGELOG.read_text(encoding="utf-8"), versao, commits_desde(tag),
                                       date.today())
    CHANGELOG.write_text(texto, encoding="utf-8")
    Path(saida_notas).write_text(notas + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("calcular")
    c.add_argument("--forcar", default="")
    a = sub.add_parser("aplicar")
    a.add_argument("versao")
    a.add_argument("--notas", default="notas.md")
    args = p.parse_args(argv)
    if args.comando == "calcular":
        print(f"versao={calcular(args.forcar.strip())}")
    else:
        aplicar(args.versao, args.notas)


if __name__ == "__main__":
    main()
