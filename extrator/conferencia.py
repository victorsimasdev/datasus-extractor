"""
Conferência independente: relê no PDF de cada consulta o valor de cada célula da planilha.

Não usa dados.json nem o código da coleta. Para cada célula, a aba _MAPA diz de qual consulta ela
veio, o rótulo da linha no site e a posição da coluna; a aba EVIDÊNCIAS diz qual é o PDF. A
conferência abre o PDF, acha a linha e compara:
  - número no PDF  -> a célula tem de ter exatamente esse número;
  - "-" ou "..."   -> a célula tem de ser SR;
  - "Nenhum registro selecionado" no PDF -> SR.
Também confere que o PDF é o da consulta: formulário, períodos e filtros presentes no texto.
"""
import re
from pathlib import Path

from .formularios import normaliza

SR = "SR"


def num_br(s):
    return float(s.replace(".", "").replace(",", "."))


def texto_pdf(caminho):
    import pypdf

    return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(caminho).pages)


def valores_da_linha(texto, rotulo):
    """Valores (texto) da linha do PDF que começa com o rótulo; None se não achar ou se for ambígua."""
    achadas = [lin for lin in texto.splitlines() if lin.strip().startswith(rotulo + " ")]
    if len(achadas) != 1:
        return None
    return achadas[0].strip()[len(rotulo):].split()


def conferir_celula(valor, texto, rotulo, col, ncols):
    """Devolve None se confere, ou a descrição do problema."""
    if "Nenhum registro selecionado" in texto:
        return None if valor == SR else f"PDF sem registro, planilha={valor!r}"
    toks = valores_da_linha(texto, rotulo)
    if toks is None:
        return f"linha {rotulo!r} não encontrada (ou repetida) no PDF"
    if len(toks) != ncols:
        return f"linha {rotulo!r} com {len(toks)} valores no PDF, esperado {ncols}"
    tok = toks[col]
    if tok in ("-", "..."):
        return None if valor == SR else f"PDF mostra {tok!r}, planilha={valor!r}"
    if valor == SR or not isinstance(valor, (int, float)):
        return f"PDF mostra {tok}, planilha={valor!r}"
    return None if abs(num_br(tok) - float(valor)) < 1e-9 else f"PDF mostra {tok}, planilha={valor!r}"


def conferir(planilha, saida=print):
    import openpyxl

    planilha = Path(planilha)
    pasta = planilha.parent
    wb = openpyxl.load_workbook(planilha)
    erros, ok, sr_sem_pdf = [], 0, 0
    ev = {}
    for row in wb["EVIDÊNCIAS"].iter_rows(min_row=2, values_only=False):
        chave = row[0].value
        pdf = row[9].hyperlink.target if row[9].hyperlink else None
        ev[chave] = {"formulario": row[8].value, "filtros": row[5].value or "", "pdf": pdf,
                     "periodos": [p.strip() for p in (row[12].value or "").split(",") if p.strip()]}
    textos, conferidos_pdf = {}, set()

    def abrir(chave):
        if chave not in textos:
            info = ev.get(chave)
            caminho = pasta / info["pdf"] if info and info["pdf"] else None
            if caminho is None or not caminho.is_file():
                textos[chave] = None
            else:
                t = texto_pdf(caminho)
                textos[chave] = t
                plano = normaliza(re.sub(r"\s+", " ", t))
                if info["formulario"] and f"tabcgi.exe?{info['formulario']}" not in t.replace("\n", ""):
                    erros.append(f"{info['pdf']}: PDF não é do formulário {info['formulario']}")
                if "Nenhum registro selecionado" not in t:
                    for p in info["periodos"]:
                        if normaliza(p) not in plano:
                            erros.append(f"{info['pdf']}: PDF sem o período {p}")
                    for parte in filter(None, info["filtros"].split("; ")):
                        if parte == "nenhum filtro":
                            continue
                        rot, _, opcoes = parte.partition(": ")
                        if normaliza(rot) + ":" not in plano.replace(" :", ":"):
                            erros.append(f"{info['pdf']}: PDF sem o filtro {rot}")
                        for o in opcoes.split(", "):
                            if normaliza(o) not in plano:
                                erros.append(f"{info['pdf']}: PDF sem a opção {o!r} de {rot}")
                conferidos_pdf.add(chave)
        return textos[chave]

    for aba, cel, _, chave, rotulo, col, ncols, motivo in wb["_MAPA"].iter_rows(min_row=2, values_only=True):
        valor = wb[aba][cel].value
        if motivo and (motivo.startswith("sem consulta") or motivo == "consulta não coletada"):
            if valor != SR:
                erros.append(f"{aba}!{cel}: sem consulta mas a célula tem {valor!r}")
            else:
                sr_sem_pdf += 1
            continue
        texto = abrir(chave)
        if texto is None:
            erros.append(f"{aba}!{cel}: evidência (PDF) ausente para a consulta {chave}")
            continue
        if motivo in ("linha ausente no site", "coluna ausente no site"):
            if valor != SR:
                erros.append(f"{aba}!{cel}: {motivo}, mas a célula tem {valor!r}")
            elif "Nenhum registro selecionado" not in texto and rotulo and valores_da_linha(texto, rotulo):
                erros.append(f"{aba}!{cel}: SR por {motivo}, mas a linha {rotulo!r} existe no PDF")
            else:
                ok += 1
            continue
        if motivo == "nenhum registro selecionado":
            problema = None if ("Nenhum registro selecionado" in texto and valor == SR) else \
                f"marcada sem registro, mas o PDF tem tabela (célula {valor!r})"
        else:
            problema = conferir_celula(valor, texto, rotulo, int(col), int(ncols))
        if problema:
            erros.append(f"{aba}!{cel}: {problema}")
        else:
            ok += 1

    links_ok = links_ruins = 0
    for row in wb["EVIDÊNCIAS"].iter_rows(min_row=2):
        for c in row[9:12]:
            if c.hyperlink:
                if (pasta / c.hyperlink.target).is_file():
                    links_ok += 1
                else:
                    links_ruins += 1
                    erros.append(f"link quebrado: {c.hyperlink.target}")
    saida(f"Células conferidas com o PDF: {ok}")
    saida(f"Células SR sem consulta (período ou filtro inexistente no site): {sr_sem_pdf}")
    saida(f"PDFs abertos: {len(conferidos_pdf)}; links ok: {links_ok}, quebrados: {links_ruins}")
    saida(f"ERROS: {len(erros)}")
    for e in erros[:500]:
        saida(f"   {e}")
    if len(erros) > 500:
        saida(f"   ... e mais {len(erros) - 500}")
    return erros
