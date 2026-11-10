"""
Fila e histórico de coletas: uma coleta por vez, as outras esperam na fila.

- O histórico (historico.json, na pasta do aplicativo) guarda cada pedido enviado: nome, pasta,
  situação ("na fila", "em andamento", "concluído", "erro", "interrompido") e datas. O progresso de
  cada coleta vem do status.json da pasta dela.
- Só existe um executor da fila por vez (trava fila.lock), e cada coleta, pela fila ou pela linha
  de comando, segura a trava coleta.lock: nunca há duas coletas ao mesmo tempo.
- Para parar a coleta em andamento, cria-se o arquivo PARAR na pasta dela: a coleta termina a
  consulta atual, salva e para; a fila segue para o próximo pedido.

A pasta do aplicativo é ~/.datasus-extractor (ou a da variável DATASUS_EXTRATOR_HOME).
"""
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .comum import gravar_json, ler_json

NA_FILA, EM_ANDAMENTO, CONCLUIDO, ERRO, INTERROMPIDO = "na fila", "em andamento", "concluído", "erro", "interrompido"
ATIVOS = (NA_FILA, EM_ANDAMENTO)


def pasta_app():
    p = Path(os.environ.get("DATASUS_EXTRATOR_HOME") or Path.home() / ".datasus-extractor")
    p.mkdir(parents=True, exist_ok=True)
    return p


def agora():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- travas entre processos
def pid_vivo(pid):
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        codigo = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(codigo))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and codigo.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Ocupado(Exception):
    """A trava já está com outro processo vivo."""

    def __init__(self, info):
        super().__init__(info.get("descricao") or f"processo {info.get('pid')}")
        self.info = info


def dono_da_trava(caminho):
    """Informações de quem segura a trava, ou None se está livre (ou o dono já morreu)."""
    try:
        info = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return info if pid_vivo(int(info.get("pid", 0))) else None


@contextmanager
def trava(caminho, descricao="", esperar=0.0):
    """Trava exclusiva entre processos. Trava de processo que morreu é retomada.
    Com esperar > 0, tenta por esse tempo (em segundos) antes de desistir."""
    caminho = Path(caminho)
    limite = time.time() + esperar
    while True:
        try:
            fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "desde": agora(), "descricao": descricao}, f, ensure_ascii=False)
            break
        except FileExistsError:
            dono = dono_da_trava(caminho)
            if dono is None:
                try:
                    caminho.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.time() >= limite:
                raise Ocupado(dono) from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            caminho.unlink()
        except FileNotFoundError:
            pass


def trava_coleta():
    return pasta_app() / "coleta.lock"


def coleta_em_andamento():
    """Quem está coletando agora (dict com pid e descrição), ou None."""
    return dono_da_trava(trava_coleta())


# ---------------------------------------------------------------- histórico
def _arquivo():
    return pasta_app() / "historico.json"


@contextmanager
def _editar():
    with trava(pasta_app() / "historico.lock", "histórico", esperar=10):
        lista = ler_json(_arquivo(), [])
        yield lista
        gravar_json(_arquivo(), lista)


def listar():
    return ler_json(_arquivo(), [])


class JaNaFila(Exception):
    pass


def adicionar(caminho_pedido):
    """Coloca o pedido no fim da fila. Devolve (entrada, posição na fila)."""
    from .coleta import pasta_saida
    from .pedido import carregar

    caminho_pedido = Path(caminho_pedido).resolve()
    pedido = carregar(caminho_pedido)
    pasta = str(pasta_saida(pedido).resolve())
    with _editar() as lista:
        if any(e["pasta"] == pasta and e["situacao"] in ATIVOS for e in lista):
            raise JaNaFila(f"o pedido \"{pedido['nome']}\" já está na fila ou em andamento")
        entrada = {"id": uuid.uuid4().hex[:8], "nome": pedido["nome"], "base": pedido["base"],
                   "pedido": str(caminho_pedido), "pasta": pasta, "situacao": NA_FILA,
                   "criado_em": agora(), "inicio": None, "fim": None, "mensagem": ""}
        lista.append(entrada)
        posicao = sum(1 for e in lista if e["situacao"] in ATIVOS)
    return entrada, posicao


def atualizar(id_, **campos):
    with _editar() as lista:
        for e in lista:
            if e["id"] == id_:
                e.update(campos)
                return e
    return None


def mover(id_, delta):
    """Muda a posição de um pedido entre os que estão na fila (delta -1 = sobe)."""
    with _editar() as lista:
        fila = [i for i, e in enumerate(lista) if e["situacao"] == NA_FILA]
        pos = next((k for k, i in enumerate(fila) if lista[i]["id"] == id_), None)
        if pos is None or not 0 <= pos + delta < len(fila):
            return False
        a, b = fila[pos], fila[pos + delta]
        lista[a], lista[b] = lista[b], lista[a]
        return True


def remover(id_):
    """Tira um pedido da fila (ou do histórico, se já terminou). Não mexe na pasta nem nos dados."""
    with _editar() as lista:
        alvo = next((e for e in lista if e["id"] == id_), None)
        if alvo is None or alvo["situacao"] == EM_ANDAMENTO:
            return False
        lista.remove(alvo)
        return True


def reenfileirar(id_):
    """Põe de volta na fila uma coleta interrompida ou com erro: ela continua de onde parou."""
    with _editar() as lista:
        alvo = next((e for e in lista if e["id"] == id_), None)
        if alvo is None or alvo["situacao"] in ATIVOS:
            return False
        lista.remove(alvo)
        alvo.update(situacao=NA_FILA, fim=None, mensagem="")
        lista.append(alvo)
        return True


def pedir_parada(id_):
    e = next((x for x in listar() if x["id"] == id_), None)
    if e is None or e["situacao"] != EM_ANDAMENTO:
        return False
    Path(e["pasta"], "PARAR").write_text(agora(), encoding="utf-8")
    return True


def progresso(entrada):
    """Lê o status.json da coleta: {"fase", "feitas", "total", ...} (vazio se ainda não começou)."""
    try:
        return ler_json(Path(entrada["pasta"]) / "status.json", {}) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------- executor da fila
def trava_fila():
    return pasta_app() / "fila.lock"


def fila_rodando():
    return dono_da_trava(trava_fila()) is not None


def executar_fila(rodar=None, saida=print):
    """Executa os pedidos da fila, um de cada vez, até a fila acabar. Só um executor por vez."""
    if rodar is None:
        from .rodar import rodar
    try:
        with trava(trava_fila(), "executor da fila"):
            # entradas "em andamento" de um executor que morreu voltam para o começo da fila
            with _editar() as lista:
                for e in lista:
                    if e["situacao"] == EM_ANDAMENTO:
                        e["situacao"] = NA_FILA
            while True:
                with _editar() as lista:
                    e = next((x for x in lista if x["situacao"] == NA_FILA), None)
                    if e is None:
                        break
                    e.update(situacao=EM_ANDAMENTO, inicio=e.get("inicio") or agora(), mensagem="")
                saida(f"==> {e['nome']}  ({e['pasta']})")
                try:
                    codigo = rodar(e["pedido"])
                except Exception as ex:  # o executor nunca para por causa de um pedido
                    codigo, msg = 1, f"{type(ex).__name__}: {ex}"
                else:
                    msg = ""
                situacao = {0: CONCLUIDO, 130: INTERROMPIDO}.get(codigo, ERRO)
                atualizar(e["id"], situacao=situacao, fim=agora(),
                          mensagem=msg or (progresso(e).get("motivo") or ""))
                saida(f"<== {e['nome']}: {situacao}")
    except Ocupado:
        saida("A fila já está sendo executada em outra janela.")
        return 0
    saida("Fila vazia.")
    return 0


def iniciar_executor():
    """Abre o executor da fila numa janela própria, se ainda não estiver rodando."""
    if fila_rodando():
        return False
    raiz = Path(__file__).resolve().parent.parent
    args = [sys.executable, "-m", "extrator", "fila"]
    if sys.platform == "win32":
        subprocess.Popen(args, cwd=raiz, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(args, cwd=raiz, start_new_session=True)
    return True
