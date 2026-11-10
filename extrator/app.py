"""
Interface do extrator: janela de desktop (pywebview) com a interface em HTML/CSS/JS (pasta web/).

A interface não guarda regra de negócio: as opções vêm dos formulários do TabNet, a estimativa e a
prévia da planilha vêm do plano real da coleta (pedido.planejar), e o pedido gerado entra na fila
(fila.py). Só uma janela do programa abre por vez.

Uso:  python -m extrator
"""
import os
import sys
import threading
from collections import deque
from pathlib import Path

from . import __version__, fila, tema
from .coleta import pasta_saida
from .comum import gravar_json

WEB = Path(__file__).resolve().parent / "web"
ICONE_ICO = Path(__file__).resolve().parent / "recursos" / "icone.ico"
SEGUNDOS_POR_CONSULTA = 20


def _bases():
    from .janela import BASES  # mesma leitura de opções da janela clássica (nacional e união dos estados)

    return {b.chave: b for b in BASES}


class Api:
    """Métodos chamados pela interface (window.pywebview.api.*). Tudo devolve JSON simples."""

    def __init__(self):
        self._janela = None
        self._bases = _bases()
        self._atualizando = {"ativo": False, "mensagem": ""}

    # ---------------- bases e formulários
    def bases(self):
        out = []
        for b in self._bases.values():
            f = b.nacional
            out.append({"chave": b.chave, "nome": b.nome, "descricao": b.descricao,
                        "periodo": f"{f.periodos[0]} a {f.periodos[-1]}", "n_periodos": len(f.periodos),
                        "mensal": f.mensal, "n_conteudos": len(f.conteudos),
                        "n_filtros": len(f.filtros) + len(b.so_estadual), "so_estadual": b.so_estadual})
        return out

    def formulario(self, base, abrangencia, ufs):
        b = self._bases[base]
        f = b.nacional if abrangencia == "nacional" or not ufs else b.estadual(ufs)
        colunas = [c for c in f.colunas if c != "Não ativa"]
        return {"linhas": f.linhas, "colunas": colunas, "conteudos": f.conteudos, "periodos": f.periodos,
                "mensal": f.mensal,
                "filtros": [{"nome": n, "opcoes": ops, "geo": n in f.geo,
                             "coluna": any(c.lower() == n.lower() for c in colunas)}
                            for n, ops in f.filtros.items()]}

    def ufs(self):
        from .formularios import UFS

        return UFS

    # ---------------- plano: estimativa e prévia
    def estimar(self, pedido):
        from .pedido import planejar

        try:
            plano = planejar(pedido)
        except Exception as e:
            return {"erro": str(e)}
        n = len(plano.consultas)
        evid = {"pdf_png": 2, "pdf": 1, "nenhuma": 0}.get(pedido.get("saida", {}).get("evidencias"), 2)
        return {"consultas": n, "segundos": n * SEGUNDOS_POR_CONSULTA, "arquivos": n * evid, "avisos": plano.avisos,
                "colunas": [{"grupo": c.grupo, "sub": c.subcoluna, "conteudo": c.conteudo} for c in plano.colunas],
                "linhas": [linha.rotulo for linha in plano.linhas], "abas": plano.abas}

    # ---------------- gerar pedido
    def gerar(self, pedido, substituir=False):
        try:
            pasta = pasta_saida(pedido)
            ativo = next((e for e in fila.listar() if e["situacao"] in fila.ATIVOS
                          and Path(e["pasta"]) == pasta.resolve()), None)
            if ativo:
                return {"erro": f"O pedido \"{pedido['nome']}\" já está {ativo['situacao']}. "
                                "Mude o nome do pedido para fazer outro."}
            arquivo = pasta / "pedido.json"
            if arquivo.exists() and not substituir:
                return {"existe": True, "pasta": str(pasta)}
            pasta.mkdir(parents=True, exist_ok=True)
            gravar_json(arquivo, pedido)
            entrada, posicao = fila.adicionar(arquivo)
            fila.iniciar_executor()
            return {"ok": True, "posicao": posicao, "id": entrada["id"], "pasta": str(pasta)}
        except Exception as e:
            return {"erro": str(e)}

    # ---------------- coletas e fila
    def coletas(self):
        lista = []
        for e in fila.listar():
            st = fila.progresso(e)
            p = Path(e["pasta"])
            planilha = next(iter(sorted(p.glob("*.xlsx"))), None) if p.is_dir() else None
            lista.append({**e, "fase": st.get("fase"), "feitas": st.get("feitas"), "total": st.get("total"),
                          "celulas": st.get("celulas"), "sr": st.get("sr"),
                          "erros_conferencia": st.get("erros_conferencia"), "motivo": st.get("motivo"),
                          "tem_planilha": bool(planilha), "tem_relatorio": (p / "RELATÓRIO.txt").is_file(),
                          "tem_pasta": p.is_dir()})
        return {"coletas": lista, "fila_rodando": fila.fila_rodando()}

    def acao_coleta(self, id_, acao):
        if acao == "subir":
            ok = fila.mover(id_, -1)
        elif acao == "descer":
            ok = fila.mover(id_, 1)
        elif acao == "remover":
            ok = fila.remover(id_)
        elif acao == "parar":
            ok = fila.pedir_parada(id_)
        elif acao == "continuar":
            ok = fila.reenfileirar(id_)
            if ok:
                fila.iniciar_executor()
        elif acao == "iniciar_fila":
            ok = fila.iniciar_executor() or fila.fila_rodando()
        else:
            ok = False
        return {"ok": bool(ok)}

    def abrir(self, id_, alvo):
        e = next((x for x in fila.listar() if x["id"] == id_), None)
        if not e:
            return {"ok": False}
        p = Path(e["pasta"])
        caminho = {"pasta": p, "relatorio": p / "RELATÓRIO.txt",
                   "planilha": next(iter(sorted(p.glob("*.xlsx"))), None) if p.is_dir() else None}.get(alvo)
        if caminho and Path(caminho).exists() and sys.platform == "win32":
            os.startfile(caminho)
            return {"ok": True}
        return {"ok": False}

    def log(self, id_, linhas=40):
        e = next((x for x in fila.listar() if x["id"] == id_), None)
        arq = Path(e["pasta"]) / "execucao.log" if e else None
        if not arq or not arq.is_file():
            return []
        with arq.open(encoding="utf-8", errors="replace") as f:
            return [lin.rstrip("\n") for lin in deque(f, maxlen=linhas)]

    # ---------------- preferências, tema e pastas
    def preferencias(self):
        p = tema.preferencias()
        p.setdefault("tema", "auto")
        p.setdefault("pasta", str(Path.home() / "Documents" / "DATASUS"))
        return {**p, "tema_sistema": tema.tema_do_windows(), "versao": __version__}

    def salvar_preferencia(self, chave, valor):
        tema.salvar_preferencia(**{chave: valor})
        return True

    def tema_sistema(self):
        return tema.tema_do_windows()

    def barra_escura(self, escuro):
        if self._janela is not None:
            _barra_de_titulo(self._janela, bool(escuro))
        return True

    def escolher_pasta(self, inicial=""):
        import webview

        r = self._janela.create_file_dialog(webview.FileDialog.FOLDER, directory=inicial or str(Path.home()))
        return r[0] if r else None

    def registrar_erro(self, mensagem):
        """Erros de JavaScript da interface vão para interface.log (diagnóstico)."""
        from datetime import datetime

        with (fila.pasta_app() / "interface.log").open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {mensagem}\n")
        return True

    # ---------------- opções dos formulários
    def info_opcoes(self):
        from datetime import datetime

        from . import formularios

        quando = datetime.fromtimestamp(formularios.ARQUIVO_OPCOES.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        return {"atualizado_em": quando, **self._atualizando}

    def atualizar_opcoes(self):
        if self._atualizando["ativo"]:
            return False

        def tarefa():
            from . import formularios

            self._atualizando.update(ativo=True, mensagem="Lendo os 112 formulários no site…")
            try:
                formularios._cache = None
                formularios.atualizar_opcoes()
                formularios._cache = None
                self._bases = _bases()
                self._atualizando.update(ativo=False, mensagem="Opções atualizadas.")
            except Exception as e:
                self._atualizando.update(ativo=False, mensagem=f"Não foi possível atualizar: {e}")

        threading.Thread(target=tarefa, daemon=True).start()
        return True


def _hwnd(janela):
    try:
        return int(janela.native.Handle.ToInt64())
    except Exception:
        return None


def _barra_de_titulo(janela, escuro):
    """Barra de título escura no Windows 10/11."""
    if sys.platform != "win32":
        return
    import ctypes

    hwnd = _hwnd(janela)
    if not hwnd:
        return
    valor = ctypes.c_int(1 if escuro else 0)
    for atributo in (20, 19):
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
            break


def _icone(janela):
    """Ícone do programa na janela e na barra de tarefas (WM_SETICON)."""
    if sys.platform != "win32" or not ICONE_ICO.is_file():
        return
    import ctypes

    hwnd = _hwnd(janela)
    if not hwnd:
        return
    for tipo, tam in ((0, 16), (1, 32)):  # ICON_SMALL, ICON_BIG
        h = ctypes.windll.user32.LoadImageW(None, str(ICONE_ICO), 1, tam, tam, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if h:
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, tipo, h)  # WM_SETICON


def abrir():
    """Abre a interface. Só uma janela do programa por vez."""
    try:
        import webview
    except ImportError:  # sem pywebview: usa a janela clássica
        from .janela import abrir as abrir_classica

        return abrir_classica()
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("datasus.extrator")
        except Exception:
            pass
    try:
        with fila.trava(fila.pasta_app() / "janela.lock", "janela do extrator"):
            api = Api()
            prefs = api.preferencias()
            escuro = tema.resolver(prefs["tema"]) == "escuro"
            tamanho = prefs.get("tamanho", "1440x920")
            try:
                largura, altura = (int(x) for x in tamanho.split("x"))
            except ValueError:
                largura, altura = 1440, 920
            janela = webview.create_window(
                "Extrator DATASUS", url=str(WEB / "index.html"), js_api=api, width=largura, height=altura,
                min_size=(1100, 700), background_color="#0e1116" if escuro else "#f5f6f8", text_select=False)
            api._janela = janela

            def ao_mostrar():
                _icone(janela)
                _barra_de_titulo(janela, escuro)

            def ao_fechar():
                try:
                    tema.salvar_preferencia(tamanho=f"{janela.width}x{janela.height}")
                except Exception:
                    pass

            janela.events.shown += ao_mostrar
            janela.events.closing += ao_fechar
            webview.start(debug=os.environ.get("EXTRATOR_DEBUG") == "1",
                          storage_path=str(fila.pasta_app() / "webview"))
    except fila.Ocupado:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, "O Extrator DATASUS já está aberto em outra janela.",
                                             "Programa já aberto", 0x40)
        else:
            print("O Extrator DATASUS já está aberto em outra janela.")


if __name__ == "__main__":
    abrir()
