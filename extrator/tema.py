"""
Temas claro e escuro da janela.

- "auto" segue o tema de aplicativos do Windows; "claro" e "escuro" fixam um deles.
- A escolha e o tamanho da janela ficam em preferencias.json, na pasta do aplicativo.
- As cores dos widgets desenhados à mão (barra lateral, cartões, estimativa) vêm do dicionário C,
  atualizado no lugar quando o tema muda; os widgets ttk seguem o tema Sun Valley (sv-ttk).
"""
import sys

from .comum import gravar_json, ler_json

PALETAS = {
    "claro": {
        "fundo": "#fafafa", "lado": "#eef1f5", "cartao": "#ffffff", "borda": "#dfe3e8", "borda_forte": "#c7cdd4",
        "texto": "#1b1b1b", "muda": "#5f6368", "acento": "#005fb8", "acento_texto": "#ffffff",
        "acento_suave": "#e3edfc", "erro": "#b42318", "sucesso": "#0f7b0f", "num": "#dfe3e8",
        "num_feito": "#c9d7ea", "hover": "#e4e8ee", "toast": "#1f1f1f", "toast_texto": "#ffffff",
    },
    "escuro": {
        "fundo": "#1c1c1c", "lado": "#232629", "cartao": "#2b2b2b", "borda": "#3a3d41", "borda_forte": "#4d5157",
        "texto": "#f2f2f2", "muda": "#a8adb3", "acento": "#4cc2ff", "acento_texto": "#0b1a24",
        "acento_suave": "#1f3a4d", "erro": "#ff8f86", "sucesso": "#6ccb5f", "num": "#3a3d41",
        "num_feito": "#2c4a60", "hover": "#2f3337", "toast": "#f2f2f2", "toast_texto": "#1b1b1b",
    },
}
OPCOES = {"auto": "Seguir o Windows", "claro": "Claro", "escuro": "Escuro"}
C = dict(PALETAS["claro"])  # cores em uso (atualizado no lugar)
atual = "claro"


def tema_do_windows():
    """'claro' ou 'escuro', conforme o tema de aplicativos do Windows (claro em outros sistemas)."""
    if sys.platform != "win32":
        return "claro"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "claro" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "escuro"
    except OSError:
        return "claro"


def resolver(preferencia):
    return tema_do_windows() if preferencia == "auto" else (preferencia if preferencia in PALETAS else "claro")


# ---------------------------------------------------------------- preferências
def _arquivo():
    from .fila import pasta_app

    return pasta_app() / "preferencias.json"


def preferencias():
    try:
        return ler_json(_arquivo(), {}) or {}
    except Exception:
        return {}


def salvar_preferencia(**kw):
    try:
        p = preferencias()
        p.update(kw)
        gravar_json(_arquivo(), p)
    except Exception:
        pass  # preferência é conveniência: nunca impede a janela de funcionar


# ---------------------------------------------------------------- aplicar
def barra_de_titulo(janela, escuro):
    """Barra de título escura no Windows 10/11 (DWMWA_USE_IMMERSIVE_DARK_MODE).

    Roda depois que a janela aparece: forçar o desenho antes (update_idletasks) faz o tema
    claro perder a cor de fundo."""
    if sys.platform != "win32":
        return
    janela.after(80, _barra_de_titulo, janela, escuro)


def _barra_de_titulo(janela, escuro):
    try:
        import ctypes

        if not janela.winfo_exists():
            return
        hwnd = ctypes.windll.user32.GetParent(janela.winfo_id())
        valor = ctypes.c_int(1 if escuro else 0)
        for atributo in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
                break
    except Exception:
        pass


def aplicar(raiz, preferencia):
    """Aplica o tema (preferência 'auto', 'claro' ou 'escuro') e devolve o nome resolvido."""
    from tkinter import ttk

    global atual
    nome = resolver(preferencia)
    C.update(PALETAS[nome])
    atual = nome
    estilo = ttk.Style(raiz)
    try:
        import sv_ttk

        sv_ttk.set_theme("dark" if nome == "escuro" else "light")
    except Exception:
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
    raiz.configure(bg=C["fundo"])
    estilo.configure(".", font=("Segoe UI", 10))
    estilo.configure("TLabelframe.Label", font=("Segoe UI Semibold", 10))
    estilo.configure("Muda.TLabel", foreground=C["muda"], font=("Segoe UI", 9))
    estilo.configure("Erro.TLabel", foreground=C["erro"])
    estilo.configure("Sucesso.TLabel", foreground=C["sucesso"])
    estilo.configure("Titulo.TLabel", font=("Segoe UI Semibold", 16))
    estilo.configure("Sub.TLabel", font=("Segoe UI Semibold", 11))
    estilo.configure("Treeview", rowheight=26)
    estilo.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
    barra_de_titulo(raiz, nome == "escuro")
    return nome
