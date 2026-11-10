"""
Copia a pasta de entrega (planilha + relatório + evidências, sem código) para a pasta
do Google Drive "FA INTERNAÇÕES - DATASUS (Jul-2025 a Ago-2026)", através do
Google Drive para Desktop, que sincroniza com a nuvem sozinho.

Espera (sem limite) até: a execução noturna terminar E o Google Drive para Desktop
estar disponível. Depois copia e confere arquivo a arquivo (tamanho e SHA-256).
Grava status_drive.json.

Uso:  python enviar_drive.py            -> entrega da rodada B-E (rodar_noite.py)
      python enviar_drive.py --perfil   -> entrega com H-U por perfil (rodar_perfil.py), na mesma
                                           pasta do Drive: substitui a planilha e acrescenta
                                           evidencias_perfil/ e o relatório novo
"""
import shutil
import string
import sys
import time
from datetime import datetime
from pathlib import Path

from comum import DadosCorrompidos, copia_identica, gravar_json, impedir_suspensao, ler_json

PASTA = Path(__file__).resolve().parent
PERFIL = "--perfil" in sys.argv
ENTREGA = PASTA / ("ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS" if PERFIL else "ENTREGA - FA INTERNAÇÕES DATASUS")
NOME_PASTA_DRIVE = "FA INTERNAÇÕES - DATASUS (Jul-2025 a Ago-2026)"  # drive.google.com/drive/folders/1AjXY_nNUCoPd1Dzb6H39RM6JInfaKGoB
STATUS = PASTA / ("status_drive_perfil.json" if PERFIL else "status_drive.json")
STATUS_EXECUCAO = PASTA / ("status_perfil.json" if PERFIL else "status_execucao.json")


def status(**kw):
    kw["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    gravar_json(STATUS, kw)


def raiz_drive():
    """Procura 'Meu Drive' / 'My Drive' nas letras de unidade (Google Drive para Desktop)."""
    for letra in string.ascii_uppercase:
        for nome in ("Meu Drive", "My Drive"):
            p = Path(f"{letra}:/{nome}")
            try:
                if p.is_dir():
                    return p
            except OSError:
                pass
    return None


def execucao_concluida():
    try:
        return (ler_json(STATUS_EXECUCAO) or {}).get("fase") == "concluido"
    except DadosCorrompidos:
        return False


def main():
    impedir_suspensao()
    while True:
        drive = raiz_drive()
        if execucao_concluida() and drive:
            break
        status(fase="aguardando",
               coleta_concluida=execucao_concluida(),
               google_drive_desktop=str(drive) if drive else "não encontrado")
        time.sleep(60)

    destino = drive / NOME_PASTA_DRIVE
    status(fase="copiando", destino=str(destino))
    # aguarda a pasta criada na nuvem aparecer no disco virtual (até 30 min)
    for _ in range(60):
        if destino.is_dir():
            break
        time.sleep(30)
    destino.mkdir(exist_ok=True)

    origem = list(p for p in ENTREGA.rglob("*") if p.is_file() and p.name != "desktop.ini")
    for p in origem:
        alvo = destino / p.relative_to(ENTREGA)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        for tentativa in range(5):
            if copia_identica(p, alvo):  # já está lá (ex.: envio retomado) ou a cópia deu certo
                break
            try:
                shutil.copy2(p, alvo)
            except OSError:
                time.sleep(10)
    diferentes = [str(p.relative_to(ENTREGA)) for p in origem
                  if not copia_identica(p, destino / p.relative_to(ENTREGA))]
    status(fase="concluido" if not diferentes else "erro", destino=str(destino),
           arquivos=len(origem), com_problema=diferentes)


if __name__ == "__main__":
    main()
