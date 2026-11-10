"""
Utilidades de infraestrutura compartilhadas pelos scripts de coleta, execução e entrega.

Ficam aqui só rotinas que não dependem do site nem da planilha (gravação de arquivos,
conferência de cópias, suspensão do Windows). As conferências independentes
(conferir_*.py) de propósito não usam este módulo nem o código da coleta.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path


class DadosCorrompidos(Exception):
    """O arquivo JSON existe mas não pode ser lido (gravação interrompida, cópia incompleta...)."""


def gravar_json(caminho, dados, tentativas=5):
    """Grava num temporário e troca pelo definitivo: uma interrupção nunca deixa o JSON pela metade.

    No Windows a troca pode falhar por alguns instantes se outro programa (antivírus, indexador,
    Google Drive) estiver com o arquivo aberto; por isso há algumas tentativas antes de desistir.
    """
    caminho = Path(caminho)
    tmp = caminho.with_name(caminho.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    for tentativa in range(1, tentativas + 1):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError:
            if tentativa == tentativas:
                raise
            time.sleep(0.5 * tentativa)


def ler_json(caminho, padrao=None):
    """Lê um JSON. Se o arquivo não existe, devolve `padrao`.

    Se existe mas está corrompido, levanta DadosCorrompidos em vez de devolver vazio:
    tratar um arquivo corrompido como "nada coletado" faria a coleta recomeçar do zero
    e sobrescrever o que já existia.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return padrao
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DadosCorrompidos(f"{caminho.name} está corrompido ({e})") from e


def sha256(caminho, bloco=1 << 20):
    h = hashlib.sha256()
    with Path(caminho).open("rb") as f:
        while parte := f.read(bloco):
            h.update(parte)
    return h.hexdigest()


def copia_identica(origem, destino):
    """True se `destino` existe e tem exatamente o mesmo conteúdo de `origem` (tamanho e SHA-256)."""
    origem, destino = Path(origem), Path(destino)
    try:
        if not destino.is_file() or destino.stat().st_size != origem.stat().st_size:
            return False
        return sha256(origem) == sha256(destino)
    except OSError:
        return False


def impedir_suspensao():
    """Impede o Windows de suspender enquanto este processo estiver vivo (sem mudar configurações).

    ES_CONTINUOUS | ES_SYSTEM_REQUIRED. Em outros sistemas não faz nada.
    """
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
