"""
Janela de acompanhamento da coleta por perfil. Só LÊ os arquivos (dados_perfil.json,
execucao_perfil.log, status_perfil.json e status_drive_perfil.json): não interfere na coleta.
Pode ser aberta e fechada a qualquer momento.

Mostra: consultas feitas / faltam, andamento de cada processo, tempo desde a última consulta
salva (fica vermelho após 60 min), ritmo da última hora, previsão de término e a última linha do log.

Uso:  pythonw progresso.py     (ou duplo clique em "ABRIR PROGRESSO.bat")
"""
import json
import tkinter as tk
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk

from coletar_perfil import PROCESSOS, chave, todos_casos, todos_nacionais

PASTA = Path(__file__).resolve().parent
ARQ = PASTA / "dados_perfil.json"
LOG = PASTA / "execucao_perfil.log"
STATUS = PASTA / "status_perfil.json"
STATUS_DRIVE = PASTA / "status_drive_perfil.json"
ALERTA_MIN = 60
ATUALIZA_MS = 10_000

CASOS = todos_casos() + todos_nacionais()
TOTAL = len(CASOS)
GRUPOS = {k: f"{i}. {PROCESSOS[p][2]}" for i, p in enumerate(PROCESSOS, start=1) for k in [p]}
TOTAL_GRUPO = Counter(p for p, _, uf, _, _ in CASOS if not uf.startswith(("Região", "Unidade")))
TOTAL_NACIONAL = len(todos_nacionais())


def fmt_dur(seg):
    seg = int(max(seg, 0))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}min" if h else f"{m}min {s:02d}s"


def ler_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def ultima_linha_log():
    try:
        with LOG.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4000))
            linhas = [l.strip() for l in f.read().decode("utf-8", "replace").splitlines() if l.strip()]
        return linhas[-1] if linhas else ""
    except OSError:
        return ""


class Janela:
    def __init__(self, raiz):
        self.raiz = raiz
        self.mtime = None
        self.dados = {}
        raiz.title("Coleta DATASUS por perfil - progresso")
        raiz.geometry("620x430")
        raiz.resizable(False, True)
        f = ttk.Frame(raiz, padding=14)
        f.pack(fill="both", expand=True)

        self.lbl_total = ttk.Label(f, font=("Segoe UI", 15, "bold"))
        self.lbl_total.pack(anchor="w")
        self.barra = ttk.Progressbar(f, maximum=TOTAL, length=590)
        self.barra.pack(fill="x", pady=(6, 10))

        self.lbl_ultima = tk.Label(f, font=("Segoe UI", 12, "bold"), anchor="w")
        self.lbl_ultima.pack(fill="x")
        self.lbl_ritmo = ttk.Label(f, font=("Segoe UI", 10))
        self.lbl_ritmo.pack(anchor="w", pady=(2, 10))

        self.grupos = {}
        for nome in list(GRUPOS.values()) + ["4. Nacional (Região e UF)"]:
            linha = ttk.Frame(f)
            linha.pack(fill="x", pady=2)
            ttk.Label(linha, text=nome, width=24).pack(side="left")
            b = ttk.Progressbar(linha, length=330)
            b.pack(side="left", padx=6)
            l = ttk.Label(linha, width=14)
            l.pack(side="left")
            self.grupos[nome] = (b, l)

        ttk.Separator(f).pack(fill="x", pady=10)
        self.lbl_fase = ttk.Label(f, font=("Segoe UI", 10))
        self.lbl_fase.pack(anchor="w")
        self.lbl_log = ttk.Label(f, font=("Consolas", 9), foreground="#555", wraplength=590)
        self.lbl_log.pack(anchor="w", pady=(4, 0))
        self.lbl_atual = ttk.Label(f, font=("Segoe UI", 8), foreground="#888")
        self.lbl_atual.pack(anchor="w", side="bottom")
        self.atualizar()

    def atualizar(self):
        try:
            mt = ARQ.stat().st_mtime if ARQ.exists() else None
            if mt != self.mtime:
                d = ler_json(ARQ)
                if d is not None:
                    self.dados, self.mtime = d, mt
            self.desenhar()
        finally:
            self.raiz.after(ATUALIZA_MS, self.atualizar)

    def desenhar(self):
        agora = datetime.now()
        feitas_chaves = {chave(*c) for c in CASOS} & self.dados.keys()
        feitas = len(feitas_chaves)
        self.lbl_total.config(text=f"{feitas:,} de {TOTAL:,} consultas   ({feitas / TOTAL:.1%})   "
                                   f"faltam {TOTAL - feitas:,}".replace(",", "."))
        self.barra["value"] = feitas

        momentos = sorted(datetime.fromisoformat(self.dados[k]["consultado_em"]) for k in feitas_chaves)
        if momentos:
            desde = (agora - momentos[-1]).total_seconds()
            cor = "#c00000" if desde > ALERTA_MIN * 60 else ("#b36b00" if desde > 15 * 60 else "#1a7f37")
            aviso = "   ⚠ sem progresso — pode ter travado" if desde > ALERTA_MIN * 60 else ""
            self.lbl_ultima.config(text=f"Última consulta salva há {fmt_dur(desde)}  "
                                        f"({momentos[-1]:%d/%m %H:%M:%S}){aviso}", fg=cor)
            ultima_hora = [m for m in momentos if m > agora - timedelta(hours=1)]
            ritmo = len(ultima_hora)
            if ritmo:
                fim = agora + timedelta(hours=(TOTAL - feitas) / ritmo)
                prev = f"previsão de término: {fim:%d/%m às %H:%M} (se o ritmo se mantiver)"
            else:
                prev = "previsão indisponível (nenhuma consulta na última hora)"
            self.lbl_ritmo.config(text=f"Ritmo da última hora: {ritmo} consultas/h   —   {prev}")
        else:
            self.lbl_ultima.config(text="Nenhuma consulta salva ainda", fg="#555")
            self.lbl_ritmo.config(text="")

        cont = Counter()
        for k in feitas_chaves:
            uf, _, p, _ = k.split("|")
            cont["4. Nacional (Região e UF)" if uf.startswith("BR-") else GRUPOS[p]] += 1
        for p, nome in GRUPOS.items():
            b, l = self.grupos[nome]
            b["maximum"] = TOTAL_GRUPO[p]
            b["value"] = cont[nome]
            l.config(text=f"{cont[nome]} / {TOTAL_GRUPO[p]}")
        b, l = self.grupos["4. Nacional (Região e UF)"]
        b["maximum"] = TOTAL_NACIONAL
        b["value"] = cont["4. Nacional (Região e UF)"]
        l.config(text=f"{cont['4. Nacional (Região e UF)']} / {TOTAL_NACIONAL}")

        st = ler_json(STATUS) or {}
        sd = ler_json(STATUS_DRIVE) or {}
        fase = {"coleta": "coletando", "entrega": "montando a entrega", "planilha": "gerando a planilha",
                "conferencia": "validando pelos PDFs", "concluido": "CONCLUÍDO (0 erros)",
                "erro": f"ERRO: {st.get('motivo')}"}.get(st.get("fase"), st.get("fase", "?"))
        self.lbl_fase.config(text=f"Fase: {fase}     |     Drive: {sd.get('fase', '—')}")
        self.lbl_log.config(text=f"Log: {ultima_linha_log()[:160]}")
        self.lbl_atual.config(text=f"Atualizado às {agora:%H:%M:%S} (a cada {ATUALIZA_MS // 1000}s)  —  "
                                   f"esta janela só lê os arquivos; fechar não afeta a coleta")


if __name__ == "__main__":
    raiz = tk.Tk()
    Janela(raiz)
    raiz.mainloop()
