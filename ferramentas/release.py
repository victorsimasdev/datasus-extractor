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

A main é protegida e nada é gravado nela: a release é só a tag no commit do merge, e a versão é
carimbada no executável na hora de gerá-lo.

A página da release é o modelo fixo .github/modelo-release.md (descrição e como instalar) com a seção
"O que mudou": todos os commits desde a tag anterior, agrupados pelo tipo (Adicionado, Corrigido,
Dependências, Documentação...).

Uso:
  python ferramentas/release.py calcular [--forcar X.Y.Z]   imprime "versao=X.Y.Z" (vazio se não há release)
  python ferramentas/release.py notas X.Y.Z [--saida F] [--anterior vA.B.C] [--ate vX.Y.Z]
                                                            grava a página da release (padrão: notas.md)
  python ferramentas/release.py carimbar X.Y.Z              grava a versão no pyproject.toml e no __init__.py
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYPROJECT = RAIZ / "pyproject.toml"
INIT = RAIZ / "extrator" / "__init__.py"

PESO = {None: 0, "dependencias": 1, "correcao": 1, "menor": 2, "maior": 3}
DEPENDENCIAS_DO_PROGRAMA = "requirements.txt"
RE_ASSUNTO = re.compile(r"^(?P<tipo>[a-z]+)(?:\([^)]*\))?(?P<quebra>!)?:\s*(?P<texto>.+)$")
RE_BUMP = re.compile(r"^bump (?P<pacote>\S+) from (?P<de>\S+) to (?P<para>\S+)", re.I)
RE_VERSAO = re.compile(r"^\d+\.\d+\.\d+$")
SECOES = (("maior", "Mudanças incompatíveis"), ("menor", "Adicionado"), ("correcao", "Corrigido"),
          ("dependencias", "Dependências"), ("interno", "Melhorias internas"), ("docs", "Documentação"),
          ("automacao", "Testes e automação"), ("manutencao", "Manutenção"), ("outros", "Outros"))
TIPOS_SEM_VERSAO = {"refactor": "interno", "perf": "interno", "style": "interno", "docs": "docs",
                    "test": "automacao", "ci": "automacao", "build": "automacao", "chore": "manutencao"}
MODELO = RAIZ / ".github" / "modelo-release.md"
REPO = "victorsimasdev/datasus-extractor"


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


def categoria(assunto, corpo="", arquivos=()):
    """Seção do commit em "O que mudou": a do nível de versão, ou a do tipo (docs, ci, chore...)."""
    nivel = classificar(assunto, corpo, arquivos)
    if nivel:
        return nivel
    m = RE_ASSUNTO.match(assunto.strip())
    return TIPOS_SEM_VERSAO.get(m["tipo"], "outros") if m else "outros"


def notas_dos_commits(commits):
    """"O que mudou" em Markdown: todos os commits, agrupados pelo tipo (Adicionado, Corrigido...)."""
    grupos = {n: [] for n, _ in SECOES}
    for commit in commits:
        assunto, corpo, arquivos = _desempacotar(commit)
        if assunto.startswith("Merge "):
            continue
        grupos[categoria(assunto, corpo, arquivos)].append(_texto(assunto))
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


def commits_desde(tag, ate="HEAD"):
    faixa = f"{tag}..{ate}" if tag else ate
    saida = _git("log", faixa, "--no-merges", "--name-only", "--format=%x1e%s%x1f%b%x1f")
    commits = []
    for bloco in saida.split("\x1e"):
        if not bloco.strip():
            continue
        assunto, corpo, nomes = bloco.split("\x1f", 2)
        commits.append((assunto, corpo.strip(), tuple(n for n in nomes.split("\n") if n.strip())))
    return commits


# ---------------------------------------------------------------- arquivos
def pagina_da_release(versao, notas, anterior, modelo, repo=REPO):
    """Texto da página da release: o modelo fixo com "O que mudou" e o link de comparação."""
    comparar = (f"**Todas as mudanças:** [{anterior}...v{versao}](https://github.com/{repo}/compare/"
                f"{anterior}...v{versao})" if anterior else "")
    texto = (modelo.replace("{versao}", versao).replace("{repo}", repo)
             .replace("{notas}", notas or "Sem mudanças registradas.").replace("{comparar}", comparar))
    return texto.rstrip() + "\n"


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


def gerar_notas(versao, saida, anterior=None, ate="HEAD"):
    """Página da release com as mudanças desde a tag anterior (padrão: a última tag antes desta)."""
    anterior = anterior or ultima_tag()
    notas = notas_dos_commits(commits_desde(anterior, ate))
    pagina = pagina_da_release(versao, notas, anterior, MODELO.read_text(encoding="utf-8"))
    Path(saida).write_text(pagina, encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("calcular")
    c.add_argument("--forcar", default="")
    n = sub.add_parser("notas")
    n.add_argument("versao")
    n.add_argument("--saida", default="notas.md")
    n.add_argument("--anterior", help="tag anterior (padrão: a última tag)")
    n.add_argument("--ate", default="HEAD", help="até qual commit ou tag (padrão: HEAD)")
    v = sub.add_parser("carimbar")
    v.add_argument("versao")
    args = p.parse_args(argv)
    if args.comando == "calcular":
        print(f"versao={calcular(args.forcar.strip())}")
    elif args.comando == "notas":
        gerar_notas(args.versao, args.saida, args.anterior, args.ate)
    else:
        if not RE_VERSAO.match(args.versao):
            sys.exit(f"Versão inválida: {args.versao!r} (use X.Y.Z)")
        gravar_versao(args.versao)


if __name__ == "__main__":
    main()
