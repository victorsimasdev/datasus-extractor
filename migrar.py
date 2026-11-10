"""
Leva a coleta por perfil de um computador para outro sem perder nada.
É chamado pelos arquivos de duplo clique:

  "1 - PARAR E EXPORTAR.bat"   (computador atual)
      -> pergunta a pasta de destino (pendrive, HD externo...),
         para a coleta, o envio ao Drive e o Chrome da coleta,
         confere os dados, copia a pasta inteira e confere a cópia arquivo a arquivo.

  "2 - CONTINUAR AQUI.bat"     (computador novo, dentro da pasta copiada)
      -> (o .bat instala Python, bibliotecas e Chrome se faltarem)
         confere a cópia (consultas sem evidência voltam para a fila),
         retoma a coleta de onde parou, arma o envio ao Drive e abre a janela de progresso.

Uso direto:  python migrar.py exportar [--teste DESTINO]   |   python migrar.py continuar [--teste]
  --teste: não para nem inicia processos (só para testar a cópia e as conferências).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ARQ = PASTA / "dados_perfil.json"
PADRAO_PROCESSOS = "rodar_perfil|coletar_perfil|enviar_drive"
IGNORAR = shutil.ignore_patterns("__pycache__", "*.tmp", "desktop.ini")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
TESTE = "--teste" in sys.argv


def ps(comando):
    return subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def processos_da_coleta():
    saida = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
               f"Where-Object {{ $_.CommandLine -match '{PADRAO_PROCESSOS}' }} | "
               "ForEach-Object { $_.ProcessId }")
    return [int(x) for x in saida.split() if x.isdigit()]


def parar_coleta():
    pids = processos_da_coleta()
    print(f"Parando {len(pids)} processo(s) da coleta/envio...")
    for _ in range(3):
        ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
           f"Where-Object {{ $_.CommandLine -match '{PADRAO_PROCESSOS}' }} | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        # Chrome sem janela usado pela coleta (o Chrome normal do usuário não é tocado)
        ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
           "Where-Object { $_.CommandLine -match '--headless' -and $_.CommandLine -match 'playwright' } | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        time.sleep(3)
        if not processos_da_coleta():
            return True
    return False


def conferir_dados(corrigir):
    """Mesma regra de verificar_retomada.py; devolve (salvas, sem_evidencia, total)."""
    args = [sys.executable, str(PASTA / "verificar_retomada.py")] + (["--corrigir"] if corrigir else [])
    saida = subprocess.run(args, cwd=PASTA, capture_output=True, text=True, encoding="utf-8", env=ENV)
    print(saida.stdout + saida.stderr)
    return saida.returncode == 0, saida.stdout


def copiar_conferindo(origem, destino):
    arquivos = [p for p in origem.rglob("*") if p.is_file() and p.name != "desktop.ini"
                and "__pycache__" not in p.parts and p.suffix != ".tmp"]
    total_mb = sum(p.stat().st_size for p in arquivos) / 1e6
    print(f"Copiando {len(arquivos)} arquivos ({total_mb:,.0f} MB) para {destino} ...")
    for i, p in enumerate(arquivos, start=1):
        alvo = destino / p.relative_to(origem)
        if not alvo.is_file() or alvo.stat().st_size != p.stat().st_size:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, alvo)
        if i % 200 == 0 or i == len(arquivos):
            print(f"  {i}/{len(arquivos)}")
    erradas = [str(p.relative_to(origem)) for p in arquivos
               if not (destino / p.relative_to(origem)).is_file()
               or (destino / p.relative_to(origem)).stat().st_size != p.stat().st_size]
    return len(arquivos), erradas


class _SoTexto:
    """No modo --teste as caixas de mensagem viram texto (nada aparece na tela)."""
    @staticmethod
    def _p(titulo, texto, *a, **k):
        print(f"[{titulo}] {texto}")
        return True
    showinfo = showerror = askyesno = _p


def janelas():
    if TESTE:
        return _SoTexto
    import tkinter as tk
    from tkinter import messagebox
    raiz = tk.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    return messagebox


def exportar():
    messagebox = janelas()

    if TESTE:
        base = Path(sys.argv[sys.argv.index("--teste") + 1])
    else:
        from tkinter import filedialog
        escolha = filedialog.askdirectory(title="Escolha onde salvar a coleta (pendrive, HD externo...)")
        if not escolha:
            print("Cancelado: nada foi parado nem copiado.")
            return 1
        base = Path(escolha)
    destino = base / PASTA.name
    if destino.resolve() == PASTA.resolve() or PASTA.resolve() in destino.resolve().parents:
        messagebox.showerror("Destino inválido", "Escolha uma pasta fora da pasta do projeto.")
        return 1

    if not TESTE:
        if not messagebox.askyesno("Parar a coleta?",
                                   f"A coleta e o envio ao Drive serão PARADOS neste computador e tudo será "
                                   f"copiado para:\n\n{destino}\n\nContinuar?"):
            print("Cancelado: nada foi parado nem copiado.")
            return 1
        if not parar_coleta():
            messagebox.showerror("Erro", "Não consegui parar a coleta. Nada foi copiado. Tente de novo.")
            return 1
        print("Coleta parada.")

    ok, saida = conferir_dados(corrigir=False)
    if not ok:
        messagebox.showerror("Erro nos dados", f"Problema em dados_perfil.json. Nada foi copiado.\n\n{saida}")
        return 1
    n, erradas = copiar_conferindo(PASTA, destino)
    (destino / "EXPORTADO EM.txt").write_text(
        f"Exportado de {os.environ.get('COMPUTERNAME', '?')} em {datetime.now():%d/%m/%Y %H:%M:%S}\n\n{saida}",
        encoding="utf-8")
    if erradas:
        messagebox.showerror("Cópia incompleta",
                             f"{len(erradas)} arquivo(s) não foram copiados corretamente (ex.: {erradas[0]}).\n"
                             f"Rode de novo para completar a cópia.")
        return 1
    resumo = next((l for l in saida.splitlines() if l.startswith("Consultas salvas")), "")
    messagebox.showinfo("Pronto",
                        f"Coleta parada e copiada com sucesso ({n} arquivos conferidos).\n{resumo}\n\n"
                        f"No computador novo, copie a pasta\n\"{PASTA.name}\"\n"
                        f"e dê duplo clique em \"2 - CONTINUAR AQUI.bat\" dentro dela.\n\n"
                        f"Não continue a coleta NESTE computador, para não haver dois rodando ao mesmo tempo.")
    return 0


def continuar():
    messagebox = janelas()

    if not ARQ.exists():
        messagebox.showerror("Pasta incompleta", "dados_perfil.json não encontrado nesta pasta. "
                                                 "Copie a pasta exportada inteira.")
        return 1
    if not TESTE and processos_da_coleta():
        messagebox.showinfo("Já está rodando", "A coleta já está rodando neste computador.")
        subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), str(PASTA / "progresso.py")], cwd=PASTA)
        return 0

    ok, saida = conferir_dados(corrigir=True)
    if not ok:
        messagebox.showerror("Erro nos dados", saida)
        return 1

    if not TESTE:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        # console próprio e invisível: sobrevive ao fechamento da janela do .bat e não abre janelas
        sem_janela = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        for args in (["rodar_perfil.py"], ["enviar_drive.py", "--perfil"]):
            subprocess.Popen([sys.executable, "-u", str(PASTA / args[0]), *args[1:]], cwd=PASTA, env=ENV,
                             creationflags=sem_janela, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        if not processos_da_coleta():
            messagebox.showerror("Erro", "A coleta não iniciou. Veja execucao_perfil.log.")
            return 1
        subprocess.Popen([pythonw if Path(pythonw).exists() else sys.executable, str(PASTA / "progresso.py")], cwd=PASTA)

    drive = any(Path(f"{l}:/Meu Drive").is_dir() or Path(f"{l}:/My Drive").is_dir()
                for l in "DEFGHIJKLMNOPQRSTUVWXYZ")
    resumo = "\n".join(l for l in saida.splitlines() if l.startswith(("Consultas salvas", "Faltam", "Retiradas")))
    aviso_drive = "" if drive else ("\n\n⚠ Google Drive para Desktop não encontrado: a coleta continua, mas o envio "
                                    "ao Drive só acontece depois que ele for instalado e conectado à conta.")
    messagebox.showinfo("Coleta retomada", f"A coleta continuou de onde parou.\n\n{resumo}\n\n"
                                           f"A janela de progresso foi aberta (pode fechá-la sem afetar a coleta). "
                                           f"Deixe o computador ligado e com internet.{aviso_drive}")
    return 0


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    if acao == "exportar":
        sys.exit(exportar())
    if acao == "continuar":
        sys.exit(continuar())
    sys.exit(__doc__)
