"""
Gera o executável do Windows e o zip da release:

  datasus-extractor-X.Y.Z-windows.zip
    ExtratorDATASUS.exe   o programa (não precisa de Python)
    LEIA-ME.txt           como instalar e usar
    LICENSE.txt           licença MIT

Uso (no Windows):
  pip install -r requirements-build.txt
  python empacotamento/gerar_exe.py [--saida dist]
"""
import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AQUI = RAIZ / "empacotamento"
PACOTE = RAIZ / "extrator"
NOME = "ExtratorDATASUS"


def versao():
    m = re.search(r'^version = "([^"]+)"', (RAIZ / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return m[1]


def comando_pyinstaller(saida):
    obra = saida / "obra"
    dados = [(PACOTE / "web", "extrator/web"), (PACOTE / "recursos", "extrator/recursos"),
             (PACOTE / "opcoes_formularios.json", "extrator")]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", NOME, "--icon", str(PACOTE / "recursos" / "icone.ico"),
           "--distpath", str(saida), "--workpath", str(obra), "--specpath", str(obra),
           "--paths", str(RAIZ), "--collect-submodules", "extrator", "--collect-data", "sv_ttk"]
    for origem, destino in dados:
        cmd += ["--add-data", f"{origem}{os.pathsep}{destino}"]
    return cmd + [str(AQUI / "entrada.py")]


def texto_windows(texto):
    """Quebras de linha do Windows e BOM, para abrir certo em qualquer Bloco de Notas."""
    return texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8-sig")


def montar_zip(saida, v):
    exe = saida / f"{NOME}.exe"
    if not exe.is_file():
        sys.exit(f"Executável não encontrado: {exe}")
    leia_me = (AQUI / "LEIA-ME.txt").read_text(encoding="utf-8").replace("{versao}", v)
    arquivo = saida / f"datasus-extractor-{v}-windows.zip"
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(exe, exe.name)
        z.writestr("LEIA-ME.txt", texto_windows(leia_me))
        z.writestr("LICENSE.txt", texto_windows((RAIZ / "LICENSE").read_text(encoding="utf-8")))
    return arquivo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saida", default=str(RAIZ / "dist"))
    p.add_argument("--so-zip", action="store_true", help="não roda o PyInstaller, só monta o zip")
    a = p.parse_args(argv)
    saida = Path(a.saida).resolve()
    saida.mkdir(parents=True, exist_ok=True)
    if not a.so_zip:
        subprocess.run(comando_pyinstaller(saida), check=True)
    arquivo = montar_zip(saida, versao())
    print(f"Gerado: {arquivo} ({arquivo.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
