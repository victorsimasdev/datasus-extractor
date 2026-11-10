"""
Janela de pedido de dados do TabNet/DATASUS.

O usuário monta o pedido em seis passos, com as opções reais de cada formulário (nacional e dos
27 estados), lidas do site por `python -m extrator atualizar-opcoes`. Ao gerar o pedido, a janela
salva pedido.json na pasta de saída e pode iniciar a coleta (python -m extrator rodar).

Comportamento do site (testado): várias opções marcadas no mesmo filtro, ou vários períodos,
viram UM resultado só, somado; médias e taxas são recalculadas pelo site. Por isso, em cada
filtro e no período, o usuário monta uma lista de itens: cada item é uma opção sozinha
(coletada separada) ou um grupo de opções (coletadas juntas, somadas pelo site).

Uso:  python -m extrator
"""
import itertools
import json
import math
import os
import re
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import fila
from .coleta import pasta_saida
from .comum import gravar_json
from .formularios import ARQUIVO_OPCOES

PASTA = Path(tempfile.gettempdir())  # onde o modelo de planilha é gravado para abrir no Excel
OPCOES = json.loads(ARQUIVO_OPCOES.read_text(encoding="utf-8"))
SEGUNDOS_POR_CONSULTA = 20
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
PASSOS = ["Base de dados", "Tabela", "Período", "Filtros", "Saída", "Revisar"]
TODAS = "TODAS_AS_CATEGORIAS__"
UFS = {"ac": "Acre", "al": "Alagoas", "am": "Amazonas", "ap": "Amapá", "ba": "Bahia", "ce": "Ceará",
       "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás", "ma": "Maranhão", "mg": "Minas Gerais",
       "ms": "Mato Grosso do Sul", "mt": "Mato Grosso", "pa": "Pará", "pb": "Paraíba", "pe": "Pernambuco",
       "pi": "Piauí", "pr": "Paraná", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte", "ro": "Rondônia",
       "rr": "Roraima", "rs": "Rio Grande do Sul", "sc": "Santa Catarina", "se": "Sergipe", "sp": "São Paulo",
       "to": "Tocantins"}
REGIOES = {"Norte": "ac am ap pa ro rr to", "Nordeste": "al ba ce ma pb pe pi rn se",
           "Centro-Oeste": "df go ms mt", "Sudeste": "es mg rj sp", "Sul": "pr rs sc"}

FONTE = ("Segoe UI", 10)
FONTE_P = ("Segoe UI", 9)
FONTE_T = ("Segoe UI Semibold", 15)
FONTE_ST = ("Segoe UI Semibold", 11)
COR_MUDA = "#5f6368"
COR_ERRO = "#b42318"
COR_ACENTO = "#005fb8"
COR_FUNDO = "#fafafa"
COR_FUNDO_LADO = "#eef1f5"
COR_BORDA = "#dfe3e8"
COR_CARTAO = "#ffffff"


def chave_periodo(rotulo):
    """'Ago/2026' -> 2026*12+8 ; '2026' -> 2026*12."""
    m = re.match(r"([A-Za-zç]{3})/(\d{4})", rotulo)
    if m:
        return int(m.group(2)) * 12 + MESES.index(m.group(1).capitalize()) + 1
    m = re.match(r"(\d{4})", rotulo)
    return int(m.group(1)) * 12 if m else 0


def rotulo_filtro(nome):
    return nome[1:].replace("_", " ").strip()


def fmt(n):
    return f"{n:,}".replace(",", ".")


class Formulario:
    """Campos de um formulário do TabNet (nacional, ou a união dos formulários dos estados escolhidos)."""

    def __init__(self, base, campos, geo=()):
        self.chave, self.nome, self.descricao = base.chave, base.nome, base.descricao
        self.linhas = [lbl for _, lbl in campos["Linha"]]
        self.colunas = [lbl for _, lbl in campos["Coluna"]]
        self.conteudos = [lbl for _, lbl in campos["Incremento"]]
        self.periodos = sorted({lbl for _, lbl in campos["Arquivos"]}, key=chave_periodo)
        self.mensal = "/" in self.periodos[-1]
        self.filtros = {}  # rótulo -> [(valor, rótulo)]
        self.geo = set()  # filtros que existem só no formulário de cada estado
        for nome, ops in campos.items():
            if nome.startswith("S"):
                self.filtros[rotulo_filtro(nome)] = [(v, lbl) for v, lbl in ops if v != TODAS]
                if nome in geo:
                    self.geo.add(rotulo_filtro(nome))


class Base:
    def __init__(self, chave, d):
        self.chave, self.nome, self.descricao, self.d = chave, d["nome"], d["descricao"], d
        self.nacional = Formulario(self, d["nacional"]["campos"])
        e = d["estadual"]
        self.so_estadual = [rotulo_filtro(n) for n in e["ordem"]
                            if n.startswith("S") and n not in d["nacional"]["campos"]]

    def estadual(self, ufs):
        """União dos formulários dos estados escolhidos. Opções que mudam de estado para estado
        (municípios, regiões de saúde, estabelecimentos) levam a sigla do estado na frente."""
        e = self.d["estadual"]
        campos, geo = {}, set()
        for n in e["ordem"]:
            if n in e["comuns"]:
                campos[n] = e["comuns"][n]
                continue
            ops, vistos = [], set()
            for uf in ufs:
                for v, lbl in e["por_uf"][uf].get(n, []):
                    if n == "Arquivos":
                        chave, item = lbl, [lbl, lbl]
                    elif v == TODAS:
                        chave, item = TODAS, [v, lbl]
                    else:
                        chave, item = f"{uf}|{v}", [f"{uf}|{v}", f"{uf.upper()} · {lbl}"]
                    if chave not in vistos:
                        vistos.add(chave)
                        ops.append(item)
            campos[n] = ops
            if n != "Arquivos":
                geo.add(n)
        return Formulario(self, campos, geo)


BASES = [Base(k, d) for k, d in OPCOES.items()]


def nome_grupo(rotulos):
    if len(rotulos) == 1:
        return rotulos[0]
    if len(rotulos) == 2:
        return f"{rotulos[0]} + {rotulos[1]}"
    return f"{rotulos[0]} até {rotulos[-1]} ({len(rotulos)} opções)"


CHECK_ON, CHECK_OFF = "☑", "☐"


class ConstrutorItens(ttk.Frame):
    """Lista de opções com caixas de marcar + lista do que será coletado.

    O usuário marca as opções (clique na linha ou na caixa) e escolhe o que fazer com as marcadas:
    adicionar cada uma separada, ou somar todas num grupo. Usado nos filtros e no período.
    """

    def __init__(self, pai, ao_mudar, rotulo_opcoes="Opções", altura=9):
        super().__init__(pai)
        self.ao_mudar = ao_mudar
        self.opcoes, self.itens, self.marcadas = [], [], set()
        self.columnconfigure(0, weight=1)
        self._agendado = None

        topo = ttk.Frame(self)
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(1, weight=1)
        ttk.Label(topo, text="🔍", font=FONTE).grid(row=0, column=0, padx=(0, 6))
        self.v_busca = tk.StringVar()
        self.e_busca = ttk.Entry(topo, textvariable=self.v_busca)
        self.e_busca.grid(row=0, column=1, sticky="ew")
        self.v_busca.trace_add("write", lambda *a: self._agendar_lista())
        self.l_dica_busca = ttk.Label(topo, text=f"Digite para buscar {rotulo_opcoes}", style="Muda.TLabel")
        self.l_dica_busca.grid(row=1, column=1, sticky="w")

        quadro = ttk.Frame(self)
        quadro.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        quadro.columnconfigure(0, weight=1)
        self.tv_op = ttk.Treeview(quadro, columns=("marca", "opcao", "status"), show="headings", height=altura,
                                  selectmode="none")
        self.tv_op.heading("marca", text=CHECK_OFF, command=self._marcar_visiveis_alternar)
        self.tv_op.heading("opcao", text="① Marque as opções", anchor="w")
        self.tv_op.heading("status", text="Já na lista", anchor="w")
        self.tv_op.column("marca", width=34, minwidth=34, stretch=False, anchor="center")
        self.tv_op.column("opcao", width=330, anchor="w")
        self.tv_op.column("status", width=95, stretch=False, anchor="w")
        self.tv_op.tag_configure("marcada", background="#e3edfc")
        self.tv_op.tag_configure("usada", foreground=COR_ACENTO)
        self.tv_op.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(quadro, command=self.tv_op.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tv_op.config(yscrollcommand=sb.set)
        self.tv_op.bind("<Button-1>", self._clique)
        self.tv_op.bind("<space>", self._espaco)

        bt = ttk.Frame(self)
        bt.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(bt, text="②").pack(side="left", padx=(0, 4))
        self.b_sep = ttk.Button(bt, text="➕ Adicionar separadas", command=self.adicionar_separadas)
        self.b_sep.pack(side="left")
        self.b_jun = ttk.Button(bt, text="Σ Somar num grupo", command=self.adicionar_grupo)
        self.b_jun.pack(side="left", padx=6)
        ttk.Button(bt, text="Desmarcar", command=self.desmarcar).pack(side="left")
        self.l_info = ttk.Label(self, style="Muda.TLabel", wraplength=480, justify="left")
        self.l_info.grid(row=3, column=0, sticky="w", pady=(2, 0))

        ttk.Label(self, text="③ Será coletado", style="Sub.TLabel").grid(row=4, column=0, sticky="w", pady=(10, 2))
        quadro2 = ttk.Frame(self)
        quadro2.grid(row=5, column=0, sticky="nsew")
        quadro2.columnconfigure(0, weight=1)
        self.tv = ttk.Treeview(quadro2, columns=("tipo", "qtd"), show="tree headings", height=6, selectmode="extended")
        self.tv.heading("#0", text="Nome na planilha")
        self.tv.heading("tipo", text="Como")
        self.tv.heading("qtd", text="Opções")
        self.tv.column("#0", width=270)
        self.tv.column("tipo", width=130, anchor="center")
        self.tv.column("qtd", width=65, anchor="center")
        self.tv.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(quadro2, command=self.tv.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.tv.config(yscrollcommand=sb2.set)
        self.tv.bind("<Double-Button-1>", lambda e: self.renomear())
        self.tv.bind("<Delete>", lambda e: self.remover())
        bt2 = ttk.Frame(self)
        bt2.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(bt2, text="Remover selecionados", command=self.remover).pack(side="left")
        ttk.Button(bt2, text="Renomear", command=self.renomear).pack(side="left", padx=6)
        ttk.Button(bt2, text="Limpar tudo", command=self.limpar).pack(side="left")
        self.l_vazio = ttk.Label(self, style="Muda.TLabel", wraplength=480, justify="left")
        self.l_vazio.grid(row=7, column=0, sticky="w", pady=(4, 0))
        self.texto_vazio = ""

    # ----- lista de opções -----
    def carregar(self, opcoes, itens, texto_vazio):
        """opcoes: [(valor, rótulo)]; itens: lista (alterada no lugar) de dicts do pedido."""
        self.opcoes, self.itens, self.texto_vazio = opcoes, itens, texto_vazio
        self.rot = dict(opcoes)
        self.marcadas = set()
        self.v_busca.set("")
        self._listar()
        self._mostrar_itens()

    def _agendar_lista(self):
        if self._agendado:
            self.after_cancel(self._agendado)
        self._agendado = self.after(120, self._listar)

    def _status(self):
        st = {}
        for it in self.itens:
            for v in it["valores"]:
                st.setdefault(v, "separada" if it["tipo"] == "separada" else "em grupo")
        return st

    def _listar(self):
        self._agendado = None
        termo = self.v_busca.get().strip().lower()
        self.visiveis = [(v, lbl) for v, lbl in self.opcoes if termo in lbl.lower()] if termo else list(self.opcoes)
        self.tv_op.delete(*self.tv_op.get_children())
        st = self._status()
        for i, (v, lbl) in enumerate(self.visiveis):
            tags = (("marcada",) if v in self.marcadas else ()) + (("usada",) if v in st else ())
            self.tv_op.insert("", "end", iid=str(i), values=(CHECK_ON if v in self.marcadas else CHECK_OFF, lbl,
                                                             st.get(v, "")), tags=tags)
        self._info()

    def _alternar(self, i):
        v, lbl = self.visiveis[i]
        if v in self.marcadas:
            self.marcadas.discard(v)
        else:
            self.marcadas.add(v)
        marcada = v in self.marcadas
        tags = (("marcada",) if marcada else ()) + (("usada",) if "usada" in self.tv_op.item(str(i), "tags") else ())
        self.tv_op.item(str(i), values=(CHECK_ON if marcada else CHECK_OFF, lbl, self.tv_op.set(str(i), "status")),
                        tags=tags)
        self._info()

    def _clique(self, ev):
        if self.tv_op.identify_region(ev.x, ev.y) != "cell":
            return
        linha = self.tv_op.identify_row(ev.y)
        if linha:
            self.tv_op.focus(linha)
            self._alternar(int(linha))
        return "break"

    def _espaco(self, ev):
        f = self.tv_op.focus()
        if f:
            self._alternar(int(f))
        return "break"

    def _marcar_visiveis_alternar(self):
        vis = {v for v, _ in self.visiveis}
        if vis and vis <= self.marcadas:
            self.marcadas -= vis
        else:
            self.marcadas |= vis
        self._listar()

    def desmarcar(self):
        self.marcadas.clear()
        self._listar()

    def _info(self):
        n = len(self.marcadas)
        vis = {v for v, _ in self.visiveis}
        self.tv_op.heading("marca", text=CHECK_ON if vis and vis <= self.marcadas else CHECK_OFF)
        if n == 0:
            txt = "Clique nas opções para marcar (a caixa do cabeçalho marca todas as mostradas)."
        elif n == 1:
            txt = "1 marcada → clique em \"Adicionar separadas\" (para somar num grupo, marque 2 ou mais)."
        else:
            txt = f"{n} marcadas → \"Adicionar separadas\" (um resultado cada) ou \"Somar num grupo\" (um só)."
        if len(self.visiveis) != len(self.opcoes):
            txt += f"  Mostrando {fmt(len(self.visiveis))} de {fmt(len(self.opcoes))}."
        self.l_info.config(text=txt)
        for b in (self.b_sep, self.b_jun):
            b.state(["!disabled"])

    def marcadas_em_ordem(self):
        return [(v, lbl) for v, lbl in self.opcoes if v in self.marcadas]

    # ----- adicionar / remover itens -----
    def adicionar_separadas(self, valores=None):
        sel = [(v, self.rot[v]) for v in valores] if valores is not None else self.marcadas_em_ordem()
        if not sel:
            self.l_info.config(text="Marque pelo menos uma opção na lista acima.")
            return
        ja = {it["valores"][0] for it in self.itens if it["tipo"] == "separada"}
        for v, lbl in sel:
            if v not in ja:
                self.itens.append({"tipo": "separada", "nome": lbl, "valores": [v]})
        self._depois()

    def adicionar_grupo(self, valores=None, nome=None):
        sel = [(v, self.rot[v]) for v in valores] if valores is not None else self.marcadas_em_ordem()
        if len(sel) < 2:
            self.l_info.config(text="Para somar num grupo, marque pelo menos 2 opções.")
            return
        ordem = {v: i for i, (v, _) in enumerate(self.opcoes)}
        sel.sort(key=lambda x: ordem[x[0]])
        vals = [v for v, _ in sel]
        if any(it["tipo"] == "grupo" and it["valores"] == vals for it in self.itens):
            self.l_info.config(text="Esse grupo já está na lista.")
            return
        self.itens.append({"tipo": "grupo", "nome": nome or nome_grupo([lbl for _, lbl in sel]), "valores": vals})
        self._depois()

    def remover(self):
        idx = sorted((int(i) for i in self.tv.selection()), reverse=True)
        if not idx:
            self.l_vazio.config(text="Clique num item da lista \"Será coletado\" para escolher o que remover.")
            return
        for i in idx:
            del self.itens[i]
        self._depois()

    def limpar(self):
        self.itens.clear()
        self._depois()

    def renomear(self):
        sel = self.tv.selection()
        if not sel:
            self.l_vazio.config(text="Clique num item da lista \"Será coletado\" para renomear.")
            return
        it = self.itens[int(sel[0])]
        novo = simpledialog.askstring("Renomear", "Nome na planilha:", initialvalue=it["nome"], parent=self)
        if novo and novo.strip():
            it["nome"] = novo.strip()
            self._depois(manter_marcas=True)

    def _depois(self, manter_marcas=False):
        if not manter_marcas:
            self.marcadas.clear()
        self._listar()
        self._mostrar_itens()
        self.ao_mudar()

    def _mostrar_itens(self):
        self.tv.delete(*self.tv.get_children())
        for i, it in enumerate(self.itens):
            como = "separada" if it["tipo"] == "separada" else "somadas (grupo)"
            self.tv.insert("", "end", iid=str(i), text=it["nome"], values=(como, len(it["valores"])))
        self.l_vazio.config(text=self.texto_vazio if not self.itens else
                            f"{len(self.itens)} item(ns) = {len(self.itens)} resultado(s). "
                            "Duplo clique num item para mudar o nome dele na planilha.")


class Janela(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Novo pedido de dados - DATASUS / TabNet")
        self.geometry("1380x920")
        self.minsize(1240, 760)
        estilo = ttk.Style(self)
        try:
            import sv_ttk  # tema moderno (Windows 11); sem ele, usa o tema padrão do Windows
            sv_ttk.set_theme("light")
        except Exception:
            if "vista" in estilo.theme_names():
                estilo.theme_use("vista")
        self.configure(bg=COR_FUNDO)
        estilo.configure(".", font=FONTE)
        estilo.configure("TLabelframe.Label", font=("Segoe UI Semibold", 10))
        estilo.configure("Passo.TLabel", font=("Segoe UI Semibold", 10))
        estilo.configure("Lado.TLabel", background=COR_FUNDO_LADO)
        estilo.configure("Lado.TFrame", background=COR_FUNDO_LADO)
        estilo.configure("Muda.TLabel", foreground=COR_MUDA, font=FONTE_P)
        estilo.configure("Erro.TLabel", foreground=COR_ERRO)
        estilo.configure("Titulo.TLabel", font=FONTE_T)
        estilo.configure("Sub.TLabel", font=FONTE_ST)
        estilo.configure("Treeview", rowheight=26)
        estilo.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))

        self.passo = 0
        self.base = None  # formulário em uso (nacional ou dos estados escolhidos)
        self.dados = None  # base escolhida
        self.v_base = tk.StringVar()
        self.v_abr = tk.StringVar(value="nacional")
        self.v_ufs = {uf: tk.BooleanVar(value=False) for uf in UFS}
        self.v_linha = tk.StringVar()
        self.v_colunas = {}
        self.ordem_colunas = []
        self.v_conteudos = {}
        self.ordem_conteudos = []
        self.v_ordenar = tk.BooleanVar(value=False)
        self.v_de, self.v_ate = tk.StringVar(), tk.StringVar()
        self.itens_per = []  # itens de período: separado ou grupo somado
        self.itens = {}  # filtro -> [itens]
        self.ordem_campos = []  # campos na ordem em que ganharam itens (= ordem dos blocos na planilha)
        self.titulos = {}  # campo -> nome do bloco na planilha (ex.: "IDADE" em vez de "FAIXA ETÁRIA 1")
        self.v_combinar = tk.StringVar(value="independentes")
        self.v_nome = tk.StringVar(value="Meu pedido")
        self.v_formato = tk.StringVar(value="por_periodo")
        self.v_regioes = tk.BooleanVar(value=True)  # acrescentar BRASIL - TOTAL e regiões no fim
        self.v_cont_blocos = {}  # conteúdos mostrados nos blocos de quebra (SEXO, IDADE...)
        self.v_evid = tk.StringVar(value="pdf_png")
        self.v_conf_total = tk.BooleanVar(value=True)
        self.v_conf_pdf = tk.BooleanVar(value=True)
        self.v_pasta = tk.StringVar(value=str(Path.home() / "Documents" / "DATASUS"))

        self._montar_estrutura()
        self.escolher_base(BASES[0].chave)
        self.ir(0)

    # ---------- estrutura ----------
    def _montar_estrutura(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        lado = tk.Frame(self, bg=COR_FUNDO_LADO, padx=16, pady=18)
        lado.grid(row=0, column=0, sticky="ns")
        tk.Label(lado, text="DATASUS · TabNet", font=("Segoe UI", 9), fg=COR_MUDA, bg=COR_FUNDO_LADO).pack(anchor="w")
        tk.Label(lado, text="Novo pedido", font=FONTE_T, bg=COR_FUNDO_LADO).pack(anchor="w", pady=(0, 16))
        self.rot_passos, self.sub_passos, self.num_passos = [], [], []
        for i, nome in enumerate(PASSOS):
            linha = tk.Frame(lado, bg=COR_FUNDO_LADO, cursor="hand2")
            linha.pack(anchor="w", fill="x", pady=4)
            num = tk.Label(linha, text=str(i + 1), width=2, font=("Segoe UI Semibold", 10), bg="#d5dbe3",
                           fg="black", cursor="hand2")
            num.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10), ipady=2)
            lbl = tk.Label(linha, text=nome, font=FONTE, bg=COR_FUNDO_LADO, anchor="w", cursor="hand2")
            lbl.grid(row=0, column=1, sticky="w")
            sub_ = tk.Label(linha, text="", font=("Segoe UI", 8), fg=COR_MUDA, bg=COR_FUNDO_LADO, anchor="w",
                            justify="left", wraplength=150, cursor="hand2")
            sub_.grid(row=1, column=1, sticky="w")
            for w in (linha, num, lbl, sub_):
                w.bind("<Button-1>", lambda e, i=i: self.ir(i))
            self.rot_passos.append(lbl)
            self.sub_passos.append(sub_)
            self.num_passos.append(num)

        tk.Frame(lado, bg=COR_BORDA, height=1).pack(fill="x", pady=(18, 12))
        ttk.Button(lado, text="📋  Minhas coletas", command=self.abrir_coletas).pack(anchor="w", fill="x")
        self.l_coleta_atual = tk.Label(lado, text="", font=("Segoe UI", 8), fg=COR_MUDA, bg=COR_FUNDO_LADO,
                                       justify="left", wraplength=170, anchor="w")
        self.l_coleta_atual.pack(anchor="w", fill="x", pady=(6, 0))
        self.after(500, self._atualizar_coleta_atual)

        self.area = ttk.Frame(self, padding=(26, 18, 18, 6))
        self.area.grid(row=0, column=1, sticky="nsew")
        self.area.columnconfigure(0, weight=1)
        self.area.rowconfigure(2, weight=1)
        self.l_titulo = ttk.Label(self.area, style="Titulo.TLabel")
        self.l_titulo.grid(row=0, column=0, sticky="w")
        self.l_ajuda = ttk.Label(self.area, style="Muda.TLabel", wraplength=660, justify="left")
        self.l_ajuda.grid(row=1, column=0, sticky="w", pady=(2, 12))
        self.conteudo = ttk.Frame(self.area)
        self.conteudo.grid(row=2, column=0, sticky="nsew")

        resumo = ttk.Frame(self, padding=(16, 18))
        resumo.grid(row=0, column=2, sticky="ns")
        ttk.Label(resumo, text="Resumo do pedido", style="Sub.TLabel").pack(anchor="w")
        self.t_resumo = tk.Text(resumo, width=34, height=20, wrap="word", font=FONTE_P, relief="flat",
                                bg=COR_FUNDO, padx=0, pady=8, cursor="arrow", highlightthickness=0)
        self.t_resumo.pack(fill="both", expand=True)
        self.t_resumo.tag_configure("k", foreground=COR_MUDA, font=("Segoe UI Semibold", 8))
        est = tk.Frame(resumo, bg=COR_CARTAO, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=10)
        est.pack(fill="x", pady=(8, 0))
        tk.Label(est, text="ESTIMATIVA", font=("Segoe UI Semibold", 8), fg=COR_MUDA, bg=COR_CARTAO).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.l_consultas = self._metrica(est, "Consultas ao site", 1)
        self.l_tempo = self._metrica(est, "Tempo estimado", 2)
        self.l_arquivos = self._metrica(est, "Arquivos de evidência", 3)
        self.l_conta = tk.Label(est, font=("Segoe UI", 8), fg=COR_MUDA, bg=COR_CARTAO, wraplength=230,
                                justify="left")
        self.l_conta.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        rodape = ttk.Frame(self, padding=(22, 8, 22, 12))
        rodape.grid(row=1, column=0, columnspan=3, sticky="ew")
        ttk.Separator(rodape).pack(fill="x", side="top", pady=(0, 10))
        self.l_passo = ttk.Label(rodape, style="Muda.TLabel")
        self.l_passo.pack(side="left", padx=(0, 16))
        self.l_erro = ttk.Label(rodape, style="Erro.TLabel")
        self.l_erro.pack(side="left")
        self.b_avancar = ttk.Button(rodape, text="Avançar  →", command=self.avancar, width=18, style="Accent.TButton")
        self.b_avancar.pack(side="right")
        self.b_voltar = ttk.Button(rodape, text="←  Voltar", command=lambda: self.ir(self.passo - 1), width=12)
        self.b_voltar.pack(side="right", padx=8)

    def _metrica(self, pai, rotulo, linha):
        tk.Label(pai, text=rotulo, font=FONTE_P, fg=COR_MUDA, bg=COR_CARTAO).grid(row=linha, column=0, sticky="w",
                                                                                pady=1)
        v = tk.Label(pai, font=("Segoe UI Semibold", 12), bg=COR_CARTAO)
        v.grid(row=linha, column=1, sticky="e", padx=(16, 0))
        pai.columnconfigure(1, weight=1)
        return v

    # ---------- navegação ----------
    def ir(self, i):
        if i < 0 or i >= len(PASSOS):
            return
        if i > self.passo and not all(self.validar(p) for p in range(self.passo, i)):
            return
        self.passo = i
        self.l_erro.config(text="")
        for w in self.conteudo.winfo_children():
            w.destroy()
        titulos = [
            ("Qual base de dados?", "Escolha o sistema do DATASUS e onde: o Brasil inteiro, ou dentro de estados "
             "(aí aparecem municípios, regiões de saúde e outros detalhes que só existem por estado)."),
            ("O que contar e como organizar", "Escolha o que contar, o que vai em cada linha da planilha e, se "
             "quiser, quebras em colunas."),
            ("Qual período?", "Monte a lista de períodos. Cada um sozinho vira uma aba da planilha; períodos somados "
             "(ex.: um trimestre, um ano) viram uma aba só com o total."),
            ("Quer filtrar ou detalhar?", "Opcional. Escolha um campo à esquerda e marque as opções. Com 1 opção, "
             "o pedido inteiro fica limitado a ela. Com 2 ou mais, cada uma vira uma coluna na planilha."),
            ("Como entregar?", "Formato da planilha, evidências e conferências automáticas."),
            ("Revise o pedido", "Confira o resumo e a prévia da planilha. Ao gerar, o pedido é salvo na pasta de "
             "saída e a coleta pode começar na hora."),
        ]
        t, a = titulos[i]
        self.l_titulo.config(text=f"{i + 1}. {t}")
        self.l_ajuda.config(text=a)
        [self.p_base, self.p_tabela, self.p_periodo, self.p_filtros, self.p_saida, self.p_revisar][i]()
        self.b_voltar.state(["!disabled"] if i > 0 else ["disabled"])
        self.b_avancar.config(text="✓  Gerar pedido" if i == len(PASSOS) - 1 else "Avançar  →")
        self.l_passo.config(text=f"Passo {i + 1} de {len(PASSOS)}")
        self.atualizar()

    def avancar(self):
        if self.passo == len(PASSOS) - 1:
            self.gerar()
        else:
            self.ir(self.passo + 1)

    def validar(self, p):
        erro = ""
        if p == 0 and self.v_abr.get() == "estadual" and not self.ufs_escolhidas():
            erro = "Marque pelo menos um estado."
        elif p == 1:
            if not any(v.get() for v in self.v_conteudos.values()):
                erro = "Marque pelo menos um conteúdo para contar."
            elif self.v_linha.get() in self.colunas_escolhidas():
                erro = f"\"{self.v_linha.get()}\" já está nas linhas: desmarque essa coluna."
        elif p == 2 and not self.itens_per:
            erro = "Adicione pelo menos um período à lista do que será coletado."
        elif p == 4 and not self.v_nome.get().strip():
            erro = "Dê um nome ao pedido."
        if erro:
            if p != self.passo:
                self.ir(p)
            self.l_erro.config(text=erro)
            return False
        return True

    # ---------- passo 1: base ----------
    def ufs_escolhidas(self):
        return [uf for uf, v in self.v_ufs.items() if v.get()]

    def escolher_base(self, chave):
        nova = next(b for b in BASES if b.chave == chave)
        if self.dados is nova:
            return
        self.dados = nova
        self.v_base.set(chave)
        self.base = None
        self.reconstruir()

    def reconstruir(self):
        """Monta o formulário da abrangência escolhida, mantendo o que ainda existir nele."""
        ufs = self.ufs_escolhidas()
        if self.v_abr.get() == "estadual" and not ufs and self.base is not None:
            return  # nenhum estado marcado: mantém o formulário até marcar algum (a validação avisa)
        novo = self.dados.nacional if self.v_abr.get() == "nacional" else self.dados.estadual(ufs or ["sp"])
        antigo = self.base
        self.base = b = novo
        if antigo is None or self.v_linha.get() not in b.linhas:
            pref = "Unidade da Federação" if self.v_abr.get() == "nacional" else "Município"
            self.v_linha.set(pref if pref in b.linhas else b.linhas[0])
        marcadas = [c for c in self.ordem_colunas if c in b.colunas] if antigo else []
        self.v_colunas = {c: tk.BooleanVar(value=c in marcadas) for c in b.colunas if c != "Não ativa"}
        self.ordem_colunas = marcadas
        antes = {c for c, v in self.v_conteudos.items() if v.get()} if antigo else set()
        antes = (antes & set(b.conteudos)) or {b.conteudos[0]}
        self.v_conteudos = {c: tk.BooleanVar(value=c in antes) for c in b.conteudos}
        self.ordem_conteudos = [c for c in getattr(self, "ordem_conteudos", []) if c in antes] if antigo else []
        antes_b = {c for c, v in self.v_cont_blocos.items() if v.get()} if antigo else set()
        antes_b = (antes_b & set(b.conteudos)) or {b.conteudos[0]}
        self.v_cont_blocos = {c: tk.BooleanVar(value=c in antes_b) for c in b.conteudos}
        # períodos: mantém os itens que ainda existem; sem nenhum, os últimos 12 meses (ou 5 anos), separados
        validos = set(b.periodos)
        self.itens_per = [it for it in self.itens_per if all(v in validos for v in it["valores"])] if antigo else []
        if not self.itens_per:
            ult = b.periodos[-(12 if b.mensal else 5):]
            self.itens_per = [{"tipo": "separada", "nome": p, "valores": [p]} for p in ult]
        self.v_de.set(self.itens_per[0]["valores"][0])
        self.v_ate.set(b.periodos[-1])
        velhos = self.itens if antigo else {}
        if not antigo:
            self.ordem_campos, self.titulos = [], {}
        self.itens = {}
        for f, ops in b.filtros.items():
            ok = {v for v, _ in ops}
            self.itens[f] = [it for it in velhos.get(f, []) if all(v in ok for v in it["valores"])]

    def p_base(self):
        grade = ttk.Frame(self.conteudo)
        grade.pack(fill="x")
        for i, dados in enumerate(BASES):
            b = dados.nacional
            card = tk.Frame(grade, bd=0, highlightthickness=1, cursor="hand2", padx=14, pady=8, bg="white")
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 12), pady=(0, 10))
            grade.columnconfigure(i % 2, weight=1)
            per = f"{b.periodos[0]} a {b.periodos[-1]}  ({len(b.periodos)} {'meses' if b.mensal else 'anos'})"
            linhas = [(b.nome, ("Segoe UI Semibold", 11), "black"),
                      (b.descricao, FONTE_P, COR_MUDA),
                      (f"Período: {per}", FONTE_P, "black"),
                      (f"{len(b.conteudos)} conteúdos  ·  {len(b.filtros) + len(dados.so_estadual)} filtros "
                       f"({len(dados.so_estadual)} só por estado)", FONTE_P, "black")]
            widgets = [card]
            for txt, fonte, cor in linhas:
                lb = tk.Label(card, text=txt, font=fonte, fg=cor, bg="white", anchor="w", justify="left",
                              wraplength=300)
                lb.pack(anchor="w", fill="x")
                widgets.append(lb)
            ativo = dados.chave == self.v_base.get()
            card.config(highlightbackground=COR_ACENTO if ativo else "#d0d0cc", highlightthickness=2 if ativo else 1)
            for w in widgets:
                w.bind("<Button-1>", lambda e, k=dados.chave: (self.escolher_base(k), self.ir(0)))
                w.bind("<Double-Button-1>", lambda e, k=dados.chave: (self.escolher_base(k), self.ir(1)))

        abr = ttk.LabelFrame(self.conteudo, text="Abrangência", padding=(12, 6))
        abr.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(abr, text="Brasil inteiro: linhas por região, estado, ano...", value="nacional",
                        variable=self.v_abr, command=self._mudou_abrangencia).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(abr, text="Dentro de estados: linhas por município e mais detalhes", value="estadual",
                        variable=self.v_abr, command=self._mudou_abrangencia).grid(row=1, column=0, sticky="w")
        ttk.Label(abr, text="Acrescenta: " + ", ".join(self.dados.so_estadual) + ".", style="Muda.TLabel",
                  wraplength=640, justify="left").grid(row=2, column=0, sticky="w", padx=(22, 0))
        if self.v_abr.get() == "estadual":
            est = ttk.Frame(abr)
            est.grid(row=3, column=0, sticky="w", pady=(6, 0))
            for i, uf in enumerate(UFS):
                ttk.Checkbutton(est, text=uf.upper(), variable=self.v_ufs[uf], command=self._mudou_estados).grid(
                    row=i // 14, column=i % 14, sticky="w", padx=(0, 6))
            at = ttk.Frame(abr)
            at.grid(row=4, column=0, sticky="w", pady=(6, 0))
            ttk.Button(at, text="Todos", command=lambda: self._marcar_ufs(list(UFS))).pack(side="left", padx=(0, 6))
            for reg, ufs in REGIOES.items():
                ttk.Button(at, text=reg, command=lambda u=ufs.split(): self._marcar_ufs(u)).pack(side="left",
                                                                                                padx=(0, 6))
            ttk.Button(at, text="Limpar", command=lambda: self._marcar_ufs([])).pack(side="left")

    def _mudou_abrangencia(self):
        self.reconstruir()
        self.ir(0)

    def _mudou_estados(self):
        self.reconstruir()
        self.atualizar()

    def _marcar_ufs(self, ufs):
        for uf, v in self.v_ufs.items():
            v.set(uf in ufs)
        self._mudou_estados()

    # ---------- passo 2: tabela ----------
    def conteudos_escolhidos(self):
        for c, v in self.v_conteudos.items():  # na ordem em que foram marcados
            if v.get() and c not in self.ordem_conteudos:
                self.ordem_conteudos.append(c)
        self.ordem_conteudos = [c for c in self.ordem_conteudos if self.v_conteudos[c].get()]
        return list(self.ordem_conteudos)

    def colunas_escolhidas(self):
        for c, v in self.v_colunas.items():  # mantém a ordem em que foram marcadas
            if v.get() and c not in self.ordem_colunas:
                self.ordem_colunas.append(c)
        self.ordem_colunas = [c for c in self.ordem_colunas if self.v_colunas[c].get()]
        return list(self.ordem_colunas)

    def categorias(self, tipo):
        """Categorias de um tipo de coluna (ex.: Sexo -> Masc, Fem, Ign), quando há filtro com o mesmo nome."""
        def norm(t):
            return t.lower().replace(".", "").replace(" ", "")
        for nome, ops in self.base.filtros.items():
            if norm(nome) == norm(tipo):
                return [lbl for _, lbl in ops]
        return None

    def p_tabela(self):
        b = self.base
        f = ttk.Frame(self.conteudo)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)

        q1 = ttk.LabelFrame(f, text="①  O que contar em cada célula", padding=(12, 6))
        q1.grid(row=0, column=0, sticky="ew")
        for i, (c, v) in enumerate(self.v_conteudos.items()):
            ttk.Checkbutton(q1, text=c, variable=v, command=self.atualizar).grid(
                row=i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=1)
        ttk.Label(q1, text="Marque quantos quiser: vêm todos na mesma consulta, na ordem em que você marcar.",
                  style="Muda.TLabel").grid(row=99, column=0, columnspan=3, sticky="w", pady=(4, 0))

        q2 = ttk.LabelFrame(f, text="②  Uma linha da planilha para cada", padding=(12, 6))
        q2.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        cb = ttk.Combobox(q2, textvariable=self.v_linha, values=b.linhas, state="readonly", width=42)
        cb.grid(row=0, column=0, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self.atualizar())
        ttk.Checkbutton(q2, text="Ordenar as linhas pelo valor (maior primeiro)", variable=self.v_ordenar,
                        command=self.atualizar).grid(row=0, column=1, sticky="w", padx=(18, 0))

        q3 = ttk.LabelFrame(f, text="③  Quebrar em colunas (opcional)", padding=(12, 6))
        q3.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(q3, text="Cada tipo marcado vira um bloco de colunas com TODAS as suas categorias. Para só "
                           "algumas categorias, ou para somar categorias, use o passo 4.",
                  style="Muda.TLabel", wraplength=640, justify="left").grid(row=0, column=0, columnspan=3,
                                                                            sticky="w", pady=(0, 4))
        for i, (c, v) in enumerate(self.v_colunas.items()):
            ttk.Checkbutton(q3, text=c, variable=v, command=self.atualizar).grid(
                row=1 + i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=1)

        prev = ttk.LabelFrame(f, text="Prévia das colunas", padding=(12, 6))
        prev.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.l_prev = ttk.Label(prev, font=("Consolas", 9), justify="left", wraplength=640)
        self.l_prev.pack(anchor="w")

    def _previa(self):
        if not hasattr(self, "l_prev") or not self.l_prev.winfo_exists():
            return
        lin = self.v_linha.get()
        corpo = [f"{lin}  ×  Total"]
        for c in self.colunas_escolhidas():
            cats = self.categorias(c)
            if cats:
                mostra = " | ".join(cats) if len(cats) <= 40 else " | ".join(cats[:40]) + f" | ... e mais {len(cats) - 40}"
            else:
                mostra = "(categorias que o site trouxer)"
            corpo.append(f"   + {c}: {mostra}")
        conts = self.conteudos_escolhidos()
        corpo.insert(0, "Conteúdos: " + (", ".join(conts) or "(nenhum)"))
        self.l_prev.config(text="\n".join(corpo))

    # ---------- passo 3: período ----------
    def p_periodo(self):
        b = self.base
        at = ttk.LabelFrame(self.conteudo, text="Atalhos para um intervalo", padding=(10, 6))
        at.pack(fill="x")
        ttk.Label(at, text="De").grid(row=0, column=0, sticky="w")
        ttk.Combobox(at, textvariable=self.v_de, values=b.periodos, state="readonly", width=11, height=20).grid(
            row=0, column=1, padx=(6, 14))
        ttk.Label(at, text="Até").grid(row=0, column=2, sticky="w")
        ttk.Combobox(at, textvariable=self.v_ate, values=b.periodos, state="readonly", width=11, height=20).grid(
            row=0, column=3, padx=6)
        bt = ttk.Frame(at)
        bt.grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Button(bt, text="Cada um separado", command=lambda: self._atalho_per("separados")).pack(side="left")
        ttk.Button(bt, text="Tudo somado (um grupo)", command=lambda: self._atalho_per("somado")).pack(side="left",
                                                                                                   padx=6)
        if b.mensal:
            ttk.Button(bt, text="Um grupo por ano", command=lambda: self._atalho_per("ano")).pack(side="left")
            ttk.Button(bt, text="Um grupo por trimestre", command=lambda: self._atalho_per("tri")).pack(side="left",
                                                                                                    padx=6)
        self.l_atalho = ttk.Label(at, style="Erro.TLabel")
        self.l_atalho.grid(row=2, column=0, columnspan=6, sticky="w")

        self.cons_per = ConstrutorItens(self.conteudo, self.atualizar, rotulo_opcoes="um período (ex.: 2025)", altura=7)
        self.cons_per.pack(fill="both", expand=True, pady=(10, 0))
        self.cons_per.carregar([(p, p) for p in reversed(b.periodos)], self.itens_per,
                               "Nenhum período na lista: use um atalho ou selecione períodos acima.")
        ttk.Label(self.conteudo, text="Aviso do próprio TabNet: dados dos últimos seis meses estão sujeitos a "
                                      "atualização.", style="Muda.TLabel").pack(anchor="w", pady=(6, 0))

    def _atalho_per(self, tipo):
        b = self.base
        a, z = chave_periodo(self.v_de.get()), chave_periodo(self.v_ate.get())
        if a > z:
            self.l_atalho.config(text="O início do intervalo precisa vir antes do fim.")
            return
        self.l_atalho.config(text="")
        intervalo = [p for p in b.periodos if a <= chave_periodo(p) <= z]
        if tipo == "separados":
            self.cons_per.adicionar_separadas(intervalo)
        elif tipo == "somado":
            if len(intervalo) == 1:
                self.cons_per.adicionar_separadas(intervalo)
            else:
                self.cons_per.adicionar_grupo(intervalo, f"{intervalo[0]} a {intervalo[-1]} (somado)")
        else:
            grupos = {}
            for p in intervalo:
                k = chave_periodo(p)
                ano, mes = (k - 1) // 12, (k - 1) % 12 + 1
                g = str(ano) if tipo == "ano" else f"{(mes - 1) // 3 + 1}º tri/{ano}"
                grupos.setdefault(g, []).append(p)
            for g, ps in grupos.items():
                if len(ps) == 1:
                    self.cons_per.adicionar_separadas(ps)
                else:
                    self.cons_per.adicionar_grupo(ps, f"{g} (somado)")

    # ---------- passo 4: filtros ----------
    def p_filtros(self):
        b = self.base
        f = ttk.Frame(self.conteudo)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)

        esq = ttk.Frame(f)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        esq.rowconfigure(0, weight=1)
        self.tv = ttk.Treeview(esq, columns=("sel",), show="tree headings", selectmode="browse")
        self.tv.heading("#0", text="Campo")
        self.tv.heading("sel", text="Será coletado")
        self.tv.column("#0", width=205)
        self.tv.column("sel", width=120, anchor="center")
        self.tv.grid(row=0, column=0, sticky="nsew")
        for nome, ops in b.filtros.items():
            self.tv.insert("", "end", iid=nome, text=f"{nome}  ({fmt(len(ops))})")
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._abrir_filtro())

        comb = ttk.LabelFrame(esq, text="Escolhendo em mais de um campo", padding=(8, 4))
        comb.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Radiobutton(comb, text="Um bloco por campo", value="independentes", variable=self.v_combinar,
                        command=self.atualizar).pack(anchor="w")
        ttk.Label(comb, text="ex.: Masc, Fem, 20 a 29, 30 a 39\n(4 resultados)", style="Muda.TLabel").pack(
            anchor="w", padx=(20, 0))
        ttk.Radiobutton(comb, text="Combinar os campos", value="cruzar", variable=self.v_combinar,
                        command=self.atualizar).pack(anchor="w", pady=(4, 0))
        ttk.Label(comb, text="ex.: Masc 20 a 29, Masc 30 a 39,\nFem 20 a 29, Fem 30 a 39 (4 resultados)",
                  style="Muda.TLabel").pack(anchor="w", padx=(20, 0))

        dir_ = ttk.Frame(f)
        dir_.grid(row=0, column=1, sticky="nsew")
        dir_.columnconfigure(0, weight=1)
        dir_.rowconfigure(2, weight=1)
        self.l_filtro = ttk.Label(dir_, style="Sub.TLabel")
        self.l_filtro.grid(row=0, column=0, sticky="w")
        self.l_dica = ttk.Label(dir_, style="Muda.TLabel", wraplength=480, justify="left")
        self.l_dica.grid(row=1, column=0, sticky="w")
        self.cons = ConstrutorItens(dir_, self._mudou_filtro, rotulo_opcoes="uma opção pelo nome ou código")
        self.cons.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        nb = ttk.Frame(dir_)
        nb.grid(row=0, column=0, sticky="e")
        ttk.Label(nb, text="Nome do bloco:", style="Muda.TLabel").pack(side="left")
        self.v_titulo = tk.StringVar()
        self.e_titulo = ttk.Entry(nb, textvariable=self.v_titulo, width=18)
        self.e_titulo.pack(side="left", padx=6)
        self.e_titulo.bind("<KeyRelease>", lambda e: self._mudou_titulo())

        self._atualizar_tv()
        primeiro = next((n for n, its in self.itens.items() if its), next(iter(b.filtros)))
        self.tv.selection_set(primeiro)
        self.tv.see(primeiro)

    def _abrir_filtro(self):
        sel = self.tv.selection()
        if not sel:
            return
        self.filtro = sel[0]
        self.l_filtro.config(text=self.filtro)
        coluna = next((c for c in self.base.colunas if c.lower() == self.filtro.lower()), None)
        if self.e_linha(self.filtro):
            dica = ("Este campo está nas LINHAS da planilha: as opções separadas escolhem quais linhas aparecem "
                    "(sem nada, aparecem todas). Grupos não se aplicam aqui.")
        elif coluna:
            dica = (f"\"{coluna}\" também existe como coluna: as opções separadas daqui saem numa consulta só "
                    "(coluna = este campo, filtro = as opções).")
        else:
            dica = ""
        self.l_dica.config(text=dica)
        self.v_titulo.set(self.titulos.get(self.filtro, self.filtro.upper()))
        self.cons.carregar(self.base.filtros[self.filtro], self.itens[self.filtro],
                           "Nada escolhido: este campo fica em \"Todas as categorias\".")
        self.cons.e_busca.focus_set()

    def e_linha(self, campo):
        return campo.lower() == self.v_linha.get().lower()

    def _mudou_titulo(self):
        t = self.v_titulo.get().strip()
        if t:
            self.titulos[self.filtro] = t
        self.atualizar()

    def _mudou_filtro(self):
        if self.e_linha(self.filtro):  # no campo das linhas, só opções separadas
            self.itens[self.filtro][:] = [it for it in self.itens[self.filtro] if it["tipo"] == "separada"]
            self.cons._mostrar_itens()
        for f, its in self.itens.items():
            if its and f not in self.ordem_campos:
                self.ordem_campos.append(f)
        self.ordem_campos = [f for f in self.ordem_campos if self.itens.get(f)]
        self._atualizar_tv()
        self.atualizar()

    def _atualizar_tv(self):
        for nome, its in self.itens.items():
            if not its:
                txt = "todas"
            else:
                s = sum(it["tipo"] == "separada" for it in its)
                g = len(its) - s
                txt = " · ".join(x for x in (f"{s} sep." if s else "", f"{g} grupo" + ("s" if g > 1 else "") if g else "") if x)
            self.tv.set(nome, "sel", txt)

    # ---------- passo 5: saída ----------
    def p_saida(self):
        f = ttk.Frame(self.conteudo)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Nome do pedido").grid(row=0, column=0, sticky="w", pady=4)
        e = ttk.Entry(f, textvariable=self.v_nome, width=50)
        e.grid(row=0, column=1, sticky="w", pady=4)
        e.bind("<KeyRelease>", lambda ev: self.atualizar())
        ttk.Label(f, text="Salvar em").grid(row=1, column=0, sticky="w", pady=4)
        pf = ttk.Frame(f)
        pf.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Entry(pf, textvariable=self.v_pasta, width=50).pack(side="left")
        ttk.Button(pf, text="Escolher...", command=self._pasta).pack(side="left", padx=6)

        blocos = [
            ("Formato da planilha", self.v_formato, [
                ("por_periodo", "Uma aba por período, com blocos de colunas (como a planilha FA - INTERNAÇÕES)"),
                ("longo", "Tudo numa aba só, uma linha por valor (para filtros, tabela dinâmica e Power BI)"),
                ("serie", "Uma aba por conteúdo, com os períodos lado a lado (para ver a evolução no tempo)")]),
            ("Evidências", self.v_evid, [
                ("pdf_png", "PDF e print de cada consulta (recomendado)"),
                ("pdf", "Só PDF"),
                ("nenhuma", "Sem evidências (mais rápido, sem prova da origem)")]),
        ]
        for titulo, var, ops in blocos:
            lf = ttk.LabelFrame(self.conteudo, text=titulo, padding=(12, 6))
            lf.pack(fill="x", pady=(12, 0))
            for v, txt in ops:
                ttk.Radiobutton(lf, text=txt, value=v, variable=var, command=self.atualizar).pack(anchor="w", pady=1)
        lay = ttk.LabelFrame(self.conteudo, text="Layout da planilha", padding=(12, 6))
        lay.pack(fill="x", pady=(12, 0))
        self.ck_reg = ttk.Checkbutton(lay, text="Acrescentar BRASIL - TOTAL e as regiões no fim das linhas",
                                      variable=self.v_regioes, command=self.atualizar)
        self.ck_reg.pack(anchor="w")
        if not self.regioes_aplicaveis():
            self.ck_reg.state(["disabled"])
            ttk.Label(lay, text="(só quando as linhas são por Unidade da Federação, no Brasil inteiro)",
                      style="Muda.TLabel").pack(anchor="w", padx=(20, 0))
        ttk.Label(lay, text="Conteúdos dentro dos blocos (SEXO, IDADE...):").pack(anchor="w", pady=(6, 0))
        cb = ttk.Frame(lay)
        cb.pack(anchor="w")
        marcados = self.conteudos_escolhidos()
        for i, c in enumerate(marcados):
            ttk.Checkbutton(cb, text=c, variable=self.v_cont_blocos[c], command=self.atualizar).grid(
                row=i // 3, column=i % 3, sticky="w", padx=(0, 24))
        bt = ttk.Frame(lay)
        bt.pack(anchor="w", pady=(8, 2))
        ttk.Button(bt, text="Abrir modelo da planilha no Excel", command=self.abrir_modelo).pack(side="left")
        self.l_modelo = ttk.Label(bt, style="Muda.TLabel")
        self.l_modelo.pack(side="left", padx=10)

        lf = ttk.LabelFrame(self.conteudo, text="Sem resultado", padding=(12, 6))
        lf.pack(fill="x", pady=(12, 0))
        ttk.Label(lf, text="Vira SR na planilha: linhas zeradas (sempre exibidas, nunca ocultadas), consultas com "
                           "\"Nenhum registro selecionado\" e cada célula em que o site mostra \"-\" (zero) ou "
                           "\"...\" (dado não disponível), mesmo numa linha que tem outros valores.", wraplength=620,
                  justify="left").pack(anchor="w")
        lf = ttk.LabelFrame(self.conteudo, text="Conferências automáticas", padding=(12, 6))
        lf.pack(fill="x", pady=(12, 0))
        ttk.Checkbutton(lf, text="Conferir que a soma das linhas bate com o TOTAL do site",
                        variable=self.v_conf_total).pack(anchor="w", pady=1)
        ttk.Checkbutton(lf, text="Conferir cada valor da planilha com o texto do PDF (conferência independente)",
                        variable=self.v_conf_pdf).pack(anchor="w", pady=1)

    def _pasta(self):
        p = filedialog.askdirectory(initialdir=self.v_pasta.get())
        if p:
            self.v_pasta.set(p)

    # ---------- passo 6: revisar ----------
    def p_revisar(self):
        f = ttk.Frame(self.conteudo)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        ttk.Label(f, text="Prévia da planilha (primeira aba)", style="Sub.TLabel").grid(row=0, column=0, sticky="w")
        quadro = ttk.Frame(f)
        quadro.grid(row=1, column=0, sticky="nsew", pady=(4, 10))
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(0, weight=1)
        cols, linhas = self._grade_previa()
        tv = ttk.Treeview(quadro, columns=[f"c{i}" for i in range(len(cols))], show="headings", height=9)
        for i, c in enumerate(cols):
            tv.heading(f"c{i}", text=c, anchor="w" if i == 0 else "center")
            tv.column(f"c{i}", width=170 if i == 0 else max(90, min(170, 8 * len(c))), stretch=False,
                      anchor="w" if i == 0 else "center")
        for lin in linhas:
            tv.insert("", "end", values=lin)
        tv.grid(row=0, column=0, sticky="nsew")
        sx = ttk.Scrollbar(quadro, orient="horizontal", command=tv.xview)
        sx.grid(row=1, column=0, sticky="ew")
        tv.config(xscrollcommand=sx.set)
        aba = self.itens_per[0]["nome"] if self.itens_per else "-"
        ttk.Label(f, text=f"Aba \"{aba}\" de {len(self.itens_per)}.  \"·\" = onde entram os valores  ·  "
                          "sem resultado aparece como SR.", style="Muda.TLabel").grid(row=2, column=0, sticky="w")

        ttk.Label(f, text="Resumo", style="Sub.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 0))
        t = tk.Text(f, wrap="word", font=FONTE, relief="flat", padx=14, pady=10, height=9, bg=COR_CARTAO,
                    highlightthickness=1, highlightbackground=COR_BORDA)
        t.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        t.tag_configure("k", foreground=COR_MUDA, font=("Segoe UI Semibold", 9))
        t.tag_configure("h", font=("Segoe UI Semibold", 11))
        self._escrever_resumo(t, completo=True)
        avisos = self._avisos()
        if avisos:
            t.insert("end", "Atenção\n", "h")
            for a in avisos:
                t.insert("end", f"•  {a}\n")
        t.config(state="disabled")
        ed = ttk.Frame(f)
        ed.grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(ed, text="Alterar:", style="Muda.TLabel").pack(side="left", padx=(0, 6))
        for i, nome in enumerate(PASSOS[:-1]):
            ttk.Button(ed, text=nome, command=lambda i=i: self.ir(i)).pack(side="left", padx=(0, 6))

    def _grade_previa(self):
        """Cabeçalhos e algumas linhas da primeira aba, do jeito que a planilha vai sair."""
        conts = self.conteudos_escolhidos()
        cb = self.conteudos_blocos()
        blocos = self.blocos()
        cols = [self.v_linha.get().upper()] + conts
        if blocos:
            cols += [c.upper() for c in cb]
            for titulo, subs in blocos:
                for sc in subs:
                    if len(cb) > 1:
                        cols += [f"{titulo} · {sc} · {c}" for c in cb]
                    else:
                        cols.append(f"{titulo} · {sc}")
        linhas = self.linhas_planilha()
        corpo = [x for x in linhas if x][:4]
        fim = [x for x in linhas[linhas.index("") + 1:]] if "" in linhas else []
        mostrar = corpo + (["…"] if len(linhas) > len(corpo) + len(fim) + 1 else []) + fim
        return cols, [[lin] + (["·"] * (len(cols) - 1) if lin != "…" else ["…"] * (len(cols) - 1))
                      for lin in mostrar]

    def _avisos(self):
        a = []
        recentes = {p for p in self.base.periodos[-6:]} if self.base.mensal else set()
        if any(v in recentes for it in self.itens_per for v in it["valores"]):
            a.append("Há períodos entre os últimos seis meses, que o TabNet ainda pode atualizar.")
        if self.v_evid.get() == "nenhuma":
            a.append("Sem evidências, não há como provar depois de onde veio cada valor.")
        if "Município" in self.v_linha.get():
            a.append("Tabelas por município são grandes: o site pode demorar mais em cada consulta.")
        n, _ = self.contar_consultas()
        if n > 2000:
            a.append(f"São {fmt(n)} consultas: confira se precisa de todas as combinações.")
        return a

    # ---------- resumo e estimativa ----------
    def pedido(self):
        return {
            "nome": self.v_nome.get().strip(),
            "base": self.base.chave,
            "abrangencia": self.v_abr.get(),
            "estados": self.ufs_escolhidas() if self.v_abr.get() == "estadual" else [],
            "formulario": OPCOES[self.base.chave][self.v_abr.get()]["def"],
            "linha": self.v_linha.get(),
            "colunas": self.colunas_escolhidas(),
            "conteudos": self.conteudos_escolhidos(),
            "exibir_linhas_zeradas": True,  # sempre: linha sem resultado vira SR, nunca é ocultada
            "sem_resultado": {"valor": "SR", "linha_zerada": True, "nenhum_registro": True, "celula_traco": True,
                              "celula_nao_disponivel": True},
            "ordenar_pelos_valores": self.v_ordenar.get(),
            "periodos": self.itens_per,
            "filtros": {f: its for f, its in self.itens.items() if its},
            "ordem_dos_blocos": [f for f in self.campos_em_bloco()],
            "titulos_dos_blocos": {f: self.titulos.get(f, f.upper()) for f in self.campos_em_bloco()},
            "combinar_filtros": self.v_combinar.get(),
            "layout": {"linhas": self.linhas_planilha(), "conteudos_nos_blocos": self.conteudos_blocos(),
                       "blocos": [{"titulo": t, "colunas": c} for t, c in self.blocos()],
                       "brasil_e_regioes": self.regioes_aplicaveis() and self.v_regioes.get()},
            "saida": {"formato": self.v_formato.get(), "evidencias": self.v_evid.get(),
                      "conferir_total": self.v_conf_total.get(), "conferir_pdf": self.v_conf_pdf.get(),
                      "pasta": self.v_pasta.get()},
        }

    def _descrever(self, itens, completo):
        if not itens:
            return ""
        if not completo:
            s = sum(it["tipo"] == "separada" for it in itens)
            g = len(itens) - s
            partes = [f"{s} separada(s)" if s else "", f"{g} grupo(s)" if g else ""]
            nomes = ", ".join(it["nome"] for it in itens[:3]) + (" ..." if len(itens) > 3 else "")
            return " + ".join(p for p in partes if p) + f": {nomes}"
        linhas = []
        for it in itens:
            if it["tipo"] == "separada":
                linhas.append(f"   • {it['nome']}")
            else:
                linhas.append(f"   • {it['nome']}  [juntas: {len(it['valores'])} opções somadas]")
        return "\n" + "\n".join(linhas)

    def _escrever_resumo(self, t, completo=False):
        p = self.pedido()

        def item(k, v):
            t.insert("end", f"{k.upper()}\n", "k")
            t.insert("end", f"{v}\n\n")

        item("Base", self.base.nome)
        if self.v_abr.get() == "nacional":
            item("Abrangência", "Brasil")
        else:
            u = self.ufs_escolhidas()
            item("Abrangência", f"{len(u)} estado(s): " + (", ".join(x.upper() for x in u) or "nenhum marcado"))
        item("Linhas", p["linha"])
        item("Colunas", "Total" + "".join(f" + {c}" for c in p["colunas"]))
        item("Conteúdo", ", ".join(p["conteudos"]) or "(nenhum)")
        item("Período", self._descrever(self.itens_per, completo) or "(nenhum)")
        if p["filtros"]:
            linhas = [f"{f}: {self._descrever(its, completo)}" for f, its in p["filtros"].items()]
            if len([1 for its in p["filtros"].values() if len(its) > 1]) > 1:
                linhas.append("Campos " + ("cruzados" if p["combinar_filtros"] == "cruzar" else "por conta própria"))
            item("Filtros", "\n".join(linhas))
        else:
            item("Filtros", "nenhum (todas as categorias)")
        if completo:
            fm = {"longo": "Formato longo", "por_periodo": "Uma aba por período", "serie": "Série no tempo"}
            ev = {"pdf_png": "PDF e print", "pdf": "Só PDF", "nenhuma": "Sem evidências"}
            item("Saída", f"{fm[p['saida']['formato']]}  ·  {ev[p['saida']['evidencias']]}  ·  "
                          f"sem resultado = SR\n{p['saida']['pasta']}")

    def regioes_aplicaveis(self):
        return self.v_abr.get() == "nacional" and self.v_linha.get() == "Unidade da Federação" \
            and "Região" in self.base.linhas

    def conteudos_blocos(self):
        marcados = self.conteudos_escolhidos()
        return [c for c in marcados if self.v_cont_blocos.get(c) and self.v_cont_blocos[c].get()] or marcados[:1]

    def blocos(self):
        """Blocos de colunas da planilha: [(TÍTULO, [subcolunas])], na ordem: tipos de coluna, depois filtros."""
        out = []
        for c in self.colunas_escolhidas():
            out.append((c.upper(), self.categorias(c) or ["(categorias do site)"]))
        var = self.campos_em_bloco()
        if self.v_combinar.get() == "cruzar" and len(var) > 1:
            nomes = [[it["nome"] for it in its] for its in var.values()]
            out.append((" × ".join(self.titulos.get(f, f.upper()) for f in var),
                        [" · ".join(c) for c in itertools.product(*nomes)]))
        else:
            for f, its in var.items():
                out.append((self.titulos.get(f, f.upper()), [it["nome"] for it in its]))
        return out

    def campos_em_bloco(self):
        """Campos com 2 ou mais itens viram blocos de colunas, na ordem em que foram montados."""
        ordem = self.ordem_campos + [f for f in self.itens if f not in self.ordem_campos]
        return {f: self.itens[f] for f in ordem if len(self.itens.get(f, [])) > 1 and not self.e_linha(f)}

    def linhas_planilha(self):
        cats = self.categorias(self.v_linha.get())
        campo_linha = next((f for f in self.itens if self.e_linha(f)), None)
        escolhidas = [it["nome"] for it in self.itens.get(campo_linha, [])] if campo_linha else []
        if escolhidas:
            linhas = [c.upper() for c in escolhidas]
        elif cats:
            linhas = [c.upper() for c in cats]
        else:
            linhas = [f"({self.v_linha.get()}: valores que o site trouxer)"]
        fim = ["", "BRASIL - TOTAL" if self.regioes_aplicaveis() else "TOTAL"]
        if self.regioes_aplicaveis() and self.v_regioes.get():
            fim += ["NORTE", "NORDESTE", "CENTRO-OESTE", "SUDESTE", "SUL"]  # ordem da planilha FA
        return linhas + fim

    def abrir_modelo(self):
        """Gera um .xlsx só com o layout (cabeçalhos e linhas), para ver como a planilha vai ficar."""
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        conts = self.conteudos_escolhidos()
        cb = self.conteudos_blocos()
        blocos = self.blocos()
        niveis = 3 if len(cb) > 1 and blocos else 2
        cinza = PatternFill("solid", fgColor="EDEDED")
        negrito = Font(bold=True)
        for it in self.itens_per[:24]:
            nome = re.sub(r"[\\/*?:\[\]]", " ", it["nome"]).upper()[:31]
            ws = wb.create_sheet(nome)
            ws["A1"] = (self.v_linha.get() if self.v_linha.get() != "Unidade da Federação" else "ESTADOS").upper()
            col = 2
            for c in conts:
                ws.cell(1, col, c).font = negrito
                ws.column_dimensions[get_column_letter(col)].width = max(12, len(c) + 2)
                col += 1
            col += 1  # coluna em branco, como na planilha FA
            if blocos:
                for c in cb:
                    ws.cell(1, col, c.upper()).font = negrito
                    ws.column_dimensions[get_column_letter(col)].width = max(12, len(c) + 2)
                    col += 1
            for titulo, subs in blocos:
                ws.cell(1, col, titulo).font = negrito
                for sc in subs:
                    if niveis == 3:
                        ws.cell(2, col, sc)
                        for c in cb:
                            ws.cell(3, col, c)
                            ws.column_dimensions[get_column_letter(col)].width = 13
                            col += 1
                    else:
                        ws.cell(2, col, sc)
                        ws.column_dimensions[get_column_letter(col)].width = max(11, min(28, len(sc) + 2))
                        col += 1
            for r in range(1, niveis + 1):
                for cc in range(1, col):
                    ws.cell(r, cc).fill = cinza
            for i, lin in enumerate(self.linhas_planilha(), start=niveis + 1):
                ws.cell(i, 1, lin)
                if lin:
                    for cc in range(2, col):
                        if cc != len(conts) + 2:
                            ws.cell(i, cc, "·").alignment = Alignment(horizontal="right")
            ws.column_dimensions["A"].width = 30
            ws.freeze_panes = ws.cell(niveis + 1, 2)
        if not self.itens_per:
            return
        destino = PASTA / "modelo_planilha.xlsx"
        try:
            wb.save(destino)
        except PermissionError:
            self.l_modelo.config(text="Feche o modelo aberto no Excel e tente de novo.")
            return
        extra = f" (mostrando 24 de {len(self.itens_per)} abas)" if len(self.itens_per) > 24 else ""
        if hasattr(self, "l_modelo") and self.l_modelo.winfo_exists():
            self.l_modelo.config(text=f"Gerado: {destino.name}{extra}. \"·\" = onde entram os valores.")
        if os.environ.get("JANELA_SEM_ABRIR_EXCEL") != "1":
            os.startfile(destino)
        return destino

    def _resumo_passos(self):
        n_campos = sum(1 for its in self.itens.values() if its)
        fm = {"longo": "aba única", "por_periodo": "uma aba por período", "serie": "aba por conteúdo"}
        conts = self.conteudos_escolhidos()
        abr = "Brasil" if self.v_abr.get() == "nacional" else f"{len(self.ufs_escolhidas())} estado(s)"
        return [f"{self.base.nome} · {abr}",
                f"{len(conts)} conteúdo(s) · por {self.v_linha.get()}",
                f"{len(self.itens_per)} período(s)",
                f"{n_campos} campo(s) escolhido(s)" if n_campos else "nenhum (opcional)",
                fm[self.v_formato.get()],
                ""]

    def contar_consultas(self):
        """Consultas = períodos × locais × (consultas por tabela) × (2 se tiver o bloco de regiões).

        Por tabela: 1 para o Total (ou 1 por tipo de coluna, que já traz o Total), mais os blocos de filtro.
        Opções separadas de um campo que também existe como coluna saem numa consulta só (coluna = campo,
        filtro = as opções escolhidas); cada grupo é uma consulta. Cruzando, é uma consulta por combinação.
        """
        partes = []
        per = len(self.itens_per)
        partes.append(f"{per} período(s)")
        locais = max(1, len(self.ufs_escolhidas())) if self.v_abr.get() == "estadual" else 1
        if locais > 1:
            partes.append(f"{locais} estados")
        k = len(self.colunas_escolhidas())
        por_tabela, desc = max(1, k), [f"{max(1, k)} total/colunas"]
        var = self.campos_em_bloco()
        if var:
            if self.v_combinar.get() == "cruzar" and len(var) > 1:
                q = math.prod(len(its) for its in var.values())
                por_tabela += q
                desc.append(f"{q} combinações")
            else:
                for f, its in var.items():
                    sep = sum(it["tipo"] == "separada" for it in its)
                    grupos = len(its) - sep
                    vira_coluna = any(c.lower() == f.lower() for c in self.base.colunas)
                    q = (1 if sep and vira_coluna else sep) + grupos
                    por_tabela += q
                    desc.append(f"{q} {f}")
        partes.append(f"{por_tabela} por tabela ({' + '.join(desc)})")
        n = per * locais * por_tabela
        if self.regioes_aplicaveis() and self.v_regioes.get():
            n *= 2
            partes.append("2 (estados + regiões)")
        try:  # o número exato vem do próprio plano da coleta
            from .pedido import planejar
            n = len(planejar(self.pedido()).consultas)
        except Exception:
            pass
        return n, partes

    def atualizar(self):
        if not self.base:
            return
        resumos = self._resumo_passos()
        for i, (lbl, sub_, num) in enumerate(zip(self.rot_passos, self.sub_passos, self.num_passos)):
            atual, feito = i == self.passo, i < self.passo
            lbl.config(fg=COR_ACENTO if atual else ("black" if feito else COR_MUDA),
                       font=("Segoe UI Semibold", 10) if atual else FONTE)
            num.config(text="✓" if feito else str(i + 1), bg=COR_ACENTO if atual else ("#c9d7ea" if feito else "#dfe3e8"),
                       fg="white" if atual else "black")
            sub_.config(text=resumos[i])
        self.t_resumo.config(state="normal")
        self.t_resumo.delete("1.0", "end")
        self._escrever_resumo(self.t_resumo)
        self.t_resumo.config(state="disabled")

        n, partes = self.contar_consultas()
        seg = n * SEGUNDOS_POR_CONSULTA
        self.l_consultas.config(text=fmt(n))
        if seg < 3600:
            tempo = f"{max(1, round(seg / 60))} min" if n else "0 min"
        elif seg < 48 * 3600:
            tempo = f"{seg / 3600:.1f} h".replace(".", ",")
        else:
            tempo = f"{seg / 86400:.1f} dias".replace(".", ",")
        self.l_tempo.config(text=tempo)
        por = {"pdf_png": 2, "pdf": 1, "nenhuma": 0}[self.v_evid.get()]
        self.l_arquivos.config(text=fmt(n * por))
        self.l_conta.config(text="Conta: " + "  ×  ".join(partes))
        self._previa()

    def gerar(self):
        if not all(self.validar(p) for p in range(len(PASSOS) - 1)):
            return
        pedido = self.pedido()
        pasta = pasta_saida(pedido)
        arquivo = pasta / "pedido.json"
        ativo = next((e for e in fila.listar() if e["situacao"] in fila.ATIVOS
                      and Path(e["pasta"]) == pasta.resolve()), None)
        if ativo:
            messagebox.showwarning("Pedido já na fila", f"O pedido \"{pedido['nome']}\" já está {ativo['situacao']}. "
                                   "Mude o nome do pedido para fazer outro.", parent=self)
            return
        if arquivo.exists() and not messagebox.askyesno(
                "Pedido já existe", f"Já existe um pedido com esse nome em:\n{pasta}\n\nSubstituir? Se a coleta "
                                    "já tinha começado, ela continua de onde parou nas consultas que não mudaram.",
                parent=self):
            return
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            gravar_json(arquivo, pedido)
            entrada, posicao = fila.adicionar(arquivo)
        except (OSError, fila.JaNaFila) as e:
            messagebox.showerror("Não consegui adicionar", str(e), parent=self)
            return
        fila.iniciar_executor()
        n, _ = self.contar_consultas()
        frente = "Ela começa agora." if posicao == 1 else f"Antes dela há {posicao - 1} coleta(s) na fila."
        messagebox.showinfo("Pedido na fila", f"\"{pedido['nome']}\" entrou na fila de coletas: {fmt(n)} consultas "
                                              f"(cerca de {self.l_tempo.cget('text')}).\n\n{frente} As coletas rodam "
                                              "uma de cada vez, numa janela própria.\n\nAcompanhe em \"Minhas "
                                              "coletas\".", parent=self)
        self.abrir_coletas()

    def abrir_coletas(self):
        if getattr(self, "janela_coletas", None) and self.janela_coletas.winfo_exists():
            self.janela_coletas.lift()
            return
        self.janela_coletas = JanelaColetas(self)

    def _atualizar_coleta_atual(self):
        if not self.winfo_exists():
            return
        try:
            lista = fila.listar()
            em = next((e for e in lista if e["situacao"] == fila.EM_ANDAMENTO), None)
            n_fila = sum(1 for e in lista if e["situacao"] == fila.NA_FILA)
            if em:
                st = fila.progresso(em)
                prog = f" ({st.get('feitas', 0)}/{st.get('total', '?')})" if st.get("total") else ""
                txt = f"Coletando: {em['nome']}{prog}"
            else:
                txt = "Nenhuma coleta em andamento"
            if n_fila:
                txt += f"\n{n_fila} na fila"
            self.l_coleta_atual.config(text=txt)
        except Exception:
            pass
        self.after(3000, self._atualizar_coleta_atual)


class JanelaColetas(tk.Toplevel):
    """Histórico de coletas: fila, progresso da coleta em andamento e coletas terminadas."""

    COLUNAS = (("situacao", "Situação", 105), ("progresso", "Progresso", 95), ("base", "Base", 150),
               ("inicio", "Início", 120), ("fim", "Fim", 120))
    BASES = {"sih": "Internações", "sim": "Mortalidade", "sinasc": "Nascidos vivos", "sia": "Ambulatorial"}

    def __init__(self, pai):
        super().__init__(pai)
        self.title("Minhas coletas")
        self.geometry("980x560")
        self.configure(bg=COR_FUNDO)
        quadro = ttk.Frame(self, padding=16)
        quadro.pack(fill="both", expand=True)
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(2, weight=1)
        ttk.Label(quadro, text="Minhas coletas", style="Titulo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(quadro, text="As coletas rodam uma de cada vez, na ordem da fila. Cada uma salva o que já "
                               "consultou: se parar, continua de onde parou.", style="Muda.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 10))
        self.tv = ttk.Treeview(quadro, columns=[c for c, _, _ in self.COLUNAS], show="tree headings",
                               selectmode="browse")
        self.tv.heading("#0", text="Pedido")
        self.tv.column("#0", width=280)
        for c, t, w in self.COLUNAS:
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="center" if c != "base" else "w")
        self.tv.grid(row=2, column=0, sticky="nsew")
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._detalhe())
        self.tv.bind("<Double-Button-1>", lambda e: self._abrir("planilha"))
        self.tv.tag_configure("andamento", foreground=COR_ACENTO)
        self.tv.tag_configure("erro", foreground=COR_ERRO)

        det = ttk.Frame(quadro)
        det.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        det.columnconfigure(0, weight=1)
        self.barra = ttk.Progressbar(det, mode="determinate", maximum=100)
        self.barra.grid(row=0, column=0, sticky="ew")
        self.l_detalhe = ttk.Label(det, style="Muda.TLabel", wraplength=900, justify="left")
        self.l_detalhe.grid(row=1, column=0, sticky="w", pady=(4, 0))

        bt = ttk.Frame(quadro)
        bt.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.botoes = {}
        for chave, texto, cmd in (("subir", "↑ Subir", lambda: self._mover(-1)),
                                  ("descer", "↓ Descer", lambda: self._mover(1)),
                                  ("remover", "Tirar da fila", self._remover),
                                  ("parar", "■ Parar", self._parar),
                                  ("continuar", "▶ Continuar", self._continuar)):
            self.botoes[chave] = ttk.Button(bt, text=texto, command=cmd)
            self.botoes[chave].pack(side="left", padx=(0, 6))
        for chave, texto in (("pasta", "Abrir pasta"), ("relatorio", "Relatório"), ("planilha", "Abrir planilha")):
            self.botoes[chave] = ttk.Button(bt, text=texto, command=lambda k=chave: self._abrir(k))
            self.botoes[chave].pack(side="right", padx=(6, 0))
        self.l_fila = ttk.Label(quadro, style="Muda.TLabel")
        self.l_fila.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.b_iniciar = ttk.Button(quadro, text="Iniciar a fila", command=self._iniciar_fila)
        self.entradas = {}
        self.atualizar()

    def _ordenadas(self):
        lista = fila.listar()
        em = [e for e in lista if e["situacao"] == fila.EM_ANDAMENTO]
        na = [e for e in lista if e["situacao"] == fila.NA_FILA]
        fim = sorted((e for e in lista if e["situacao"] not in fila.ATIVOS),
                     key=lambda e: e.get("fim") or e.get("criado_em") or "", reverse=True)
        return em + na + fim

    @staticmethod
    def _data(iso):
        return iso.replace("T", " ")[:16] if iso else ""

    def atualizar(self):
        if not self.winfo_exists():
            return
        sel = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        self.entradas = {}
        posicao = 0
        for e in self._ordenadas():
            st = fila.progresso(e)
            if e["situacao"] == fila.NA_FILA:
                posicao += 1
                prog = f"{posicao}º da fila"
            elif st.get("total"):
                prog = f"{st.get('feitas', 0)}/{st['total']}"
            else:
                prog = ""
            tag = ("andamento",) if e["situacao"] == fila.EM_ANDAMENTO else (("erro",) if e["situacao"] == fila.ERRO else ())
            self.tv.insert("", "end", iid=e["id"], text=e["nome"], tags=tag,
                           values=(e["situacao"], prog, self.BASES.get(e.get("base"), e.get("base", "")),
                                   self._data(e.get("inicio")), self._data(e.get("fim"))))
            self.entradas[e["id"]] = (e, st)
        if sel and sel[0] in self.entradas:
            self.tv.selection_set(sel[0])
        elif self.entradas and not sel:
            self.tv.selection_set(next(iter(self.entradas)))
        n_fila = sum(1 for e, _ in self.entradas.values() if e["situacao"] == fila.NA_FILA)
        if n_fila and not fila.fila_rodando():
            self.l_fila.config(text=f"{n_fila} coleta(s) esperando, mas a fila está parada.")
            self.b_iniciar.grid(row=6, column=0, sticky="w", pady=(4, 0))
        else:
            self.l_fila.config(text="Fila em execução." if fila.fila_rodando() else
                               ("Nenhuma coleta. Monte um pedido e clique em \"Gerar pedido\"." if not self.entradas
                                else "Fila vazia."))
            self.b_iniciar.grid_remove()
        self._detalhe()
        self._agendado = self.after(2000, self.atualizar)

    def _atual(self):
        sel = self.tv.selection()
        return self.entradas.get(sel[0]) if sel else (None, None)

    def _detalhe(self):
        e, st = self._atual()
        for b in self.botoes.values():
            b.state(["disabled"])
        if not e:
            self.barra["value"] = 0
            self.l_detalhe.config(text="")
            return
        sit = e["situacao"]
        total, feitas = st.get("total") or 0, st.get("feitas") or 0
        self.barra["value"] = 100 * feitas / total if total else (100 if sit == fila.CONCLUIDO else 0)
        partes = [f"Pasta: {e['pasta']}"]
        if sit == fila.EM_ANDAMENTO:
            fase = {"coleta": "consultando o site", "aguardando": "site instável, tentando de novo em instantes",
                    "planilha": "montando a planilha", "conferencia": "conferindo a planilha com os PDFs"}.get(
                st.get("fase"), st.get("fase", "começando"))
            restam = max(0, total - feitas)
            partes.insert(0, f"{fase.capitalize()}: {feitas} de {total} consultas"
                             + (f", faltam cerca de {max(1, round(restam * SEGUNDOS_POR_CONSULTA / 60))} min" if restam else ""))
        elif sit == fila.CONCLUIDO:
            partes.insert(0, f"Concluída: {st.get('celulas', '?')} células, {st.get('sr', '?')} SR, "
                             f"{st.get('erros_conferencia', 0)} erros na conferência.")
        elif sit in (fila.ERRO, fila.INTERROMPIDO):
            partes.insert(0, f"{sit.capitalize()}: {e.get('mensagem') or st.get('motivo') or 'veja o relatório'}. "
                             f"Já coletadas: {feitas} de {total}. \"Continuar\" retoma de onde parou.")
        self.l_detalhe.config(text="  ·  ".join(partes))
        pode = {"subir": sit == fila.NA_FILA, "descer": sit == fila.NA_FILA, "remover": sit != fila.EM_ANDAMENTO,
                "parar": sit == fila.EM_ANDAMENTO, "continuar": sit in (fila.ERRO, fila.INTERROMPIDO),
                "pasta": Path(e["pasta"]).is_dir(), "relatorio": Path(e["pasta"], "RELATÓRIO.txt").is_file(),
                "planilha": bool(self._planilha(e))}
        self.botoes["remover"].config(text="Tirar da fila" if sit == fila.NA_FILA else "Tirar do histórico")
        for k, ok in pode.items():
            self.botoes[k].state(["!disabled"] if ok else ["disabled"])

    @staticmethod
    def _planilha(e):
        p = Path(e["pasta"])
        return next(iter(sorted(p.glob("*.xlsx"))), None) if p.is_dir() else None

    def _mover(self, delta):
        e, _ = self._atual()
        if e and fila.mover(e["id"], delta):
            self.atualizar_agora()

    def _remover(self):
        e, _ = self._atual()
        if not e:
            return
        msg = ("Tirar este pedido da fila?" if e["situacao"] == fila.NA_FILA else
               "Tirar esta coleta do histórico? A pasta, a planilha e as evidências continuam onde estão.")
        if messagebox.askyesno("Confirmar", msg, parent=self) and fila.remover(e["id"]):
            self.atualizar_agora()

    def _parar(self):
        e, _ = self._atual()
        if e and messagebox.askyesno("Parar a coleta", "Parar esta coleta? Ela termina a consulta atual, salva tudo "
                                     "e para; dá para continuar depois de onde parou.", parent=self):
            fila.pedir_parada(e["id"])
            self.l_detalhe.config(text="Parada pedida: a coleta para ao terminar a consulta atual.")

    def _continuar(self):
        e, _ = self._atual()
        if e and fila.reenfileirar(e["id"]):
            fila.iniciar_executor()
            self.atualizar_agora()

    def _iniciar_fila(self):
        fila.iniciar_executor()
        self.after(1500, self.atualizar_agora)

    def atualizar_agora(self):
        if getattr(self, "_agendado", None):
            self.after_cancel(self._agendado)
        self.atualizar()

    def _abrir(self, o_que):
        e, _ = self._atual()
        if not e:
            return
        alvo = {"pasta": Path(e["pasta"]), "relatorio": Path(e["pasta"], "RELATÓRIO.txt"),
                "planilha": self._planilha(e)}[o_que]
        if alvo and Path(alvo).exists() and sys.platform == "win32":
            os.startfile(alvo)


def abrir():
    """Abre a janela. Só uma janela do programa por vez: se já houver uma aberta, avisa e sai."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido em telas com escala
        except Exception:
            pass
    try:
        with fila.trava(fila.pasta_app() / "janela.lock", "janela de pedido"):
            Janela().mainloop()
    except fila.Ocupado:
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showinfo("Programa já aberto", "O extrator do DATASUS já está aberto em outra janela. "
                                                   "Use a janela que já está aberta.", parent=raiz)
        raiz.destroy()


if __name__ == "__main__":
    abrir()
