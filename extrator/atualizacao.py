"""
Atualização do executável pelas releases do GitHub.

Ao abrir, a interface pergunta se há versão nova (verificar). Se a pessoa aceitar, instalar() baixa o zip
da release, confere o SHA-256 informado pelo GitHub, extrai o ExtratorDATASUS.exe ao lado do atual
(ExtratorDATASUS.exe.novo) e entrega a troca a um script do cmd, que espera o programa fechar, troca os
arquivos e abre a versão nova. Só vale para o executável: pelo código-fonte, a atualização é pelo git
(EXTRATOR_VERIFICAR_ATUALIZACAO=1 liga o aviso para testar).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import __version__

REPO = "victorsimasdev/datasus-extractor"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
NOME_EXE = "ExtratorDATASUS.exe"
CABECALHOS = {"Accept": "application/vnd.github+json", "User-Agent": "datasus-extractor"}

# %1 exe em uso, %2 exe novo, %3 e %4 processos do programa (o do PyInstaller e o do Python).
# Espera os dois fecharem (até 2 min), troca os arquivos (volta o antigo se a troca falhar) e abre o exe.
# Só ASCII: o cmd lê o .cmd na página de código do console; os caminhos chegam como argumentos.
# Ferramentas pelo caminho completo: um find.exe do Git no PATH faria a espera acabar na hora.
SCRIPT = r"""@echo off
set W=%SystemRoot%\System32
set N=0
:esperar
"%W%\tasklist.exe" /FI "PID eq %~3" /NH | "%W%\find.exe" "%~3" >NUL && goto ainda
"%W%\tasklist.exe" /FI "PID eq %~4" /NH | "%W%\find.exe" "%~4" >NUL && goto ainda
goto trocar
:ainda
set /a N+=1
if %N% GEQ 120 goto abrir
"%W%\PING.EXE" -n 2 127.0.0.1 >NUL
goto esperar
:trocar
move /Y "%~1" "%~1.antigo" >NUL || goto abrir
move /Y "%~2" "%~1" >NUL || move /Y "%~1.antigo" "%~1" >NUL
del "%~1.antigo" >NUL 2>&1
:abrir
start "" "%~1"
del "%~f0"
"""


def versao_tupla(texto):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (texto or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def executavel():
    """Caminho do ExtratorDATASUS.exe em uso, ou None fora do executável do Windows."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return Path(sys.executable)
    return None


def nova_versao(release, atual=__version__):
    """Dados da release se ela for mais nova que a atual e tiver o zip do Windows; senão None."""
    nova, em_uso = versao_tupla(release.get("tag_name")), versao_tupla(atual)
    if not nova or not em_uso or nova <= em_uso or release.get("draft") or release.get("prerelease"):
        return None
    zip_ = next((a for a in release.get("assets", []) if a.get("name", "").endswith("-windows.zip")), None)
    if not zip_:
        return None
    digest = zip_.get("digest") or ""
    return {"versao": ".".join(map(str, nova)), "pagina": release.get("html_url"),
            "zip": zip_["browser_download_url"], "tamanho": zip_.get("size", 0),
            "sha256": digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else ""}


def verificar(timeout=4):
    """Release mais nova que a versão em uso, ou None (também sem internet e fora do executável)."""
    exe = executavel()
    if not exe and os.environ.get("EXTRATOR_VERIFICAR_ATUALIZACAO") != "1":
        return None
    try:
        if exe:  # sobra de uma troca em que o antigo ainda estava em uso (pode continuar preso)
            exe.with_name(exe.name + ".antigo").unlink(missing_ok=True)
    except OSError:
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(URL_ULTIMA, headers=CABECALHOS), timeout=timeout) as r:
            return nova_versao(json.load(r))
    except Exception:
        return None


def baixar(info, destino, progresso=lambda feito, total: None):
    """Baixa o zip da release e confere o SHA-256 (quando o GitHub informa)."""
    h = hashlib.sha256()
    req = urllib.request.Request(info["zip"], headers={"User-Agent": CABECALHOS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=30) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("tamanho") or 0)
        feito = 0
        while bloco := r.read(1 << 16):
            f.write(bloco)
            h.update(bloco)
            feito += len(bloco)
            progresso(feito, total)
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        raise ValueError("o arquivo baixado não confere com o da release")


def extrair_exe(arquivo_zip, destino):
    with zipfile.ZipFile(arquivo_zip) as z:
        if NOME_EXE not in z.namelist():
            raise ValueError(f"{NOME_EXE} não está no zip da release")
        with z.open(NOME_EXE) as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida)


def instalar(info, progresso=lambda feito, total: None):
    """Deixa o exe novo ao lado do atual e inicia o script que troca os dois quando o programa fechar.
    Quem chama fecha a janela em seguida."""
    exe = executavel()
    if not exe:
        raise RuntimeError("a atualização automática só funciona no executável")
    novo = exe.with_name(exe.name + ".novo")
    pasta = Path(tempfile.mkdtemp(prefix="datasus-atualizacao-"))
    try:
        baixar(info, pasta / "release.zip", progresso)
        extrair_exe(pasta / "release.zip", novo)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    script = Path(tempfile.gettempdir()) / f"datasus-atualizacao-{os.getpid()}.cmd"
    script.write_text(SCRIPT, encoding="ascii")
    args = subprocess.list2cmdline([str(script), str(exe), str(novo), str(os.getppid()), str(os.getpid())])
    # /s: o cmd tira só as aspas de fora, e os caminhos com espaço continuam entre aspas.
    # Ambiente novo do PyInstaller para o exe aberto pelo script (a pasta temporária deste é apagada).
    subprocess.Popen(f'cmd /s /c "{args}"', creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                     env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
