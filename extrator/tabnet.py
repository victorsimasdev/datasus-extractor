"""
Execução de uma consulta no TabNet, com evidências.

Cada consulta abre o formulário num Chrome real (Playwright, sem janela), seleciona os campos como
uma pessoa faria, CONFERE o formulário inteiro antes de clicar em "Mostra", confere no resultado
os filtros e o período, lê a tabela e salva:
  - um PDF da página de resultado, com rodapé de endereço e data/hora, na largura da tabela
    (para nenhuma coluna ficar cortada);
  - um PNG da página com uma faixa de legenda (endereço, período, filtros);
  - quando o site responde "Nenhum registro selecionado", também o print do formulário preenchido.
"""
import os
import re
import textwrap
import time
from datetime import datetime
from pathlib import Path

from .formularios import NAO_ATIVA, TODAS, URL, limpa, normaliza

TENTATIVAS = 10


# ---------------------------------------------------------------- leitura do resultado
def num_br(s):
    """'6.252,36' -> 6252.36 ; '12' -> 12 ; '-' (zero) e '...' (não disponível) -> None (viram SR)."""
    s = (s or "").strip()
    if s in ("-", "...", ""):
        return None
    n = float(s.replace(".", "").replace(",", "."))
    return int(n) if "," not in s else n


def casas_decimais(s):
    s = (s or "").strip()
    return len(s.split(",")[1]) if "," in s else 0


def ler_tabela_html(html):
    """Lê a página de resultado do TabNet (HTML com tags sem fechamento).

    Devolve {"sem_registro", "titulo", "colunas", "linhas"}; linhas = [[rótulo, texto1, texto2, ...]].
    """
    if re.search(r"Nenhum registro selecionado", html, re.I) and not re.search(r'class="?tabdados', html, re.I):
        return {"sem_registro": True, "titulo": "", "colunas": [], "linhas": []}
    m = re.search(r'<table[^>]*class="?tabdados"?[^>]*>(.*?)</table>', html, re.S | re.I)
    if not m:
        texto = re.sub(r"\s+", " ", limpa(html))
        raise ValueError(f"página sem tabela de resultado: {texto[:300]}")
    corpo = m.group(1)
    fim_cab = corpo.upper().find("</THEAD>")
    cab = corpo[:fim_cab]
    linhas_cab = [[limpa(c) for c in re.split(r"<t[hd][^>]*>", tr, flags=re.I)[1:]]
                  for tr in re.split(r"<tr[^>]*>", cab, flags=re.I)[1:]]
    titulo = linhas_cab[0][0] if linhas_cab and linhas_cab[0] else ""
    colunas = linhas_cab[-1] if len(linhas_cab) > 1 else []
    tbody = corpo[corpo.upper().find("<TBODY"):]
    linhas = []
    for tr in re.split(r"<tr[^>]*>", tbody, flags=re.I)[1:]:
        cel = [limpa(c) for c in re.split(r"<t[hd][^>]*>", tr, flags=re.I)[1:]]
        if cel and len(cel) == len(colunas):
            linhas.append(cel)
    return {"sem_registro": False, "titulo": titulo, "colunas": colunas, "linhas": linhas}


def segmentos(titulo, rotulos):
    """Texto depois de cada 'Rótulo:' no título do resultado, até o próximo rótulo conhecido."""
    t = normaliza(titulo)
    pos = sorted((t.find(normaliza(r) + ":"), r) for r in rotulos if normaliza(r) + ":" in t)
    out = {}
    for i, (ini, r) in enumerate(pos):
        fim = pos[i + 1][0] if i + 1 < len(pos) else len(t)
        out[r] = t[ini + len(normaliza(r)) + 1:fim].strip()
    return out


def validar_resultado(consulta, tabela):
    """Confere se a página de resultado é mesmo a da consulta pedida.

    Levanta ValueError (a consulta é refeita) se o título não traz os filtros e o período pedidos,
    ou se as colunas não são as esperadas. Devolve a lista de inconsistências nos números
    (soma das linhas diferente do TOTAL), que não são refeitas: ficam registradas no relatório.
    """
    if tabela["sem_registro"]:
        return []
    seg = segmentos(tabela["titulo"], list(consulta["filtros_rotulos"]) + ["Período"])
    per = seg.get("Período")
    if per is None or any(normaliza(p) not in per for p in consulta["periodos"]):
        raise ValueError(f"período errado no resultado: {tabela['titulo']!r}")
    for rot, opcoes in consulta["filtros_rotulos"].items():
        if rot not in seg:
            raise ValueError(f"resultado sem o filtro {rot!r}: {tabela['titulo']!r}")
        faltando = [o for o in opcoes if normaliza(o) not in seg[rot]]
        if faltando:
            raise ValueError(f"filtro {rot!r} sem {faltando[:3]} no resultado")
    cols = tabela["colunas"][1:]
    if consulta["coluna"] == NAO_ATIVA:
        if sorted(normaliza(c) for c in cols) != sorted(normaliza(c) for c in consulta["conteudos"]):
            raise ValueError(f"colunas inesperadas: {cols} (esperado {consulta['conteudos']})")
    elif not cols or normaliza(cols[-1]) != "total":
        raise ValueError(f"tabela com coluna ativa sem coluna Total: {cols}")
    return conferir_somas(consulta, tabela)


def _somavel(conteudo):
    return not re.search(r"m[eé]di[oa]|taxa|permanencia m", normaliza(conteudo))


def conferir_somas(consulta, tabela):
    """Linhas somam o TOTAL (e, com coluna ativa, as categorias somam a coluna Total)."""
    problemas = []
    linhas = tabela["linhas"]
    total = next((lin for lin in linhas if normaliza(lin[0]) == "total"), None)
    if total is None:
        return [f"{consulta['chave']}: tabela sem linha TOTAL"]
    if consulta["coluna"] == NAO_ATIVA:  # o site devolve os conteúdos na ordem dele
        somaveis = [i for i, c in enumerate(tabela["colunas"]) if i > 0 and _somavel(c)]
    else:
        somaveis = list(range(1, len(tabela["colunas"]))) if _somavel(consulta["conteudos"][0]) else []
    for i in somaveis:
        partes = [num_br(lin[i]) or 0 for lin in linhas if lin is not total]
        if any(lin[i] == "..." for lin in linhas):
            continue
        esperado = num_br(total[i]) or 0
        if abs(sum(partes) - esperado) > 0.005 * max(1, len(partes)):
            problemas.append(f"{consulta['chave']}: coluna {tabela['colunas'][i]!r} soma {sum(partes):,} "
                             f"mas o TOTAL do site é {total[i]}")
    if consulta["coluna"] != NAO_ATIVA and somaveis:
        for lin in linhas:
            cats = [num_br(v) or 0 for v in lin[1:-1]]
            if "..." not in lin and abs(sum(cats) - (num_br(lin[-1]) or 0)) > 0.005 * max(1, len(cats)):
                problemas.append(f"{consulta['chave']}: linha {lin[0]!r} soma {sum(cats):,} mas o Total é {lin[-1]}")
    return problemas


# ---------------------------------------------------------------- evidências
def fonte_legenda(tamanho=15):
    from PIL import ImageFont

    windir = os.environ.get("WINDIR", "C:/Windows")
    for nome in (f"{windir}/Fonts/arial.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default(size=tamanho)


def legenda_png(caminho_png, linhas):
    """Põe uma faixa ACIMA do print (fora da página) com endereço, data/hora e filtros da consulta."""
    from PIL import Image, ImageDraw

    img = Image.open(caminho_png).convert("RGB")
    largura_chars = max(60, img.width // 8)
    quebradas = [p for lin in linhas for p in (textwrap.wrap(lin, largura_chars) or [""])]
    altura = 12 + 22 * len(quebradas)
    nova = Image.new("RGB", (img.width, img.height + altura), (40, 40, 40))
    d = ImageDraw.Draw(nova)
    fonte = fonte_legenda()
    for i, lin in enumerate(quebradas):
        d.text((10, 8 + 22 * i), lin, fill=(255, 255, 255), font=fonte)
    nova.paste(img, (0, altura))
    nova.save(caminho_png)


def descrever_filtros(consulta):
    return "; ".join(f"{r}: {', '.join(o)}" for r, o in consulta["filtros_rotulos"].items()) or "nenhum filtro"


# ---------------------------------------------------------------- navegador
NAVEGADORES = ("chrome", "msedge")  # Google Chrome, ou o Microsoft Edge que já vem no Windows


def abrir_navegador(pw, headless=True):
    """Abre o Chrome instalado; sem ele, o Edge. Nenhum navegador é baixado."""
    erros = []
    for canal in NAVEGADORES:
        try:
            return pw.chromium.launch(channel=canal, headless=headless)
        except Exception as e:
            erros.append(f"{canal}: {str(e).splitlines()[0][:120]}")
    raise RuntimeError("Nenhum navegador encontrado. Instale o Google Chrome ou o Microsoft Edge. "
                       + " | ".join(erros))


class Coletor:
    def __init__(self, pw, pasta_saida, evidencias="pdf_png", headless=True):
        self.browser = abrir_navegador(pw, headless)
        self.pasta = Path(pasta_saida)
        self.evidencias = evidencias

    def fechar(self):
        self.browser.close()

    def consultar(self, consulta, destino_base):
        """Faz a consulta (dict de Consulta) com até 10 tentativas e devolve o resultado com as evidências."""
        ultimo = None
        for tentativa in range(1, TENTATIVAS + 1):
            ctx = self.browser.new_context(viewport={"width": 1280, "height": 720}, locale="pt-BR")
            try:
                return self._consultar(ctx, consulta, Path(destino_base))
            except Exception as e:
                ultimo = e
                espera = min(60, 5 * tentativa)
                print(f"      tentativa {tentativa} falhou ({type(e).__name__}: {str(e)[:150]}); "
                      f"nova tentativa em {espera}s", flush=True)
                time.sleep(espera)
            finally:
                ctx.close()
        raise RuntimeError(f"desisti após {TENTATIVAS} tentativas: {ultimo}")

    def _consultar(self, ctx, c, destino):
        page = ctx.new_page()
        page.set_default_timeout(180_000)
        url_form = f"{URL}/deftohtm.exe?{c['caminho_def']}"
        page.goto(url_form, wait_until="load", timeout=180_000)

        page.select_option("select[name=Linha]", [c["linha"]])
        page.select_option("select[name=Coluna]", [c["coluna"]])
        page.select_option("select[name=Incremento]", c["incrementos"])
        page.select_option("select[name=Arquivos]", c["arquivos"])
        for nome_sel, valores in c["filtros"].items():
            sid = page.eval_on_selector(f'select[name="{nome_sel}"]', "s => s.id")
            botao = page.query_selector(f"#fig{sid[1:]}")
            if botao and not page.is_visible(f"#{sid}"):
                botao.click()
            page.select_option(f"#{sid}", valores)
        for nome, marcar in (("zeradas", True), ("opcoes", c.get("ordenar", False))):
            caixa = page.query_selector(f"input[name={nome}]")
            if caixa and caixa.is_checked() != marcar:
                caixa.click()
        formato = page.query_selector("input[name=formato][value=table]")
        if formato and not formato.is_checked():
            formato.click()

        # confere o formulário inteiro antes de enviar
        estado = page.evaluate("""() => [...document.querySelectorAll('form select')]
            .filter(s => !s.name.startsWith('listahidden'))
            .map(s => [s.name, [...s.selectedOptions].map(o => o.value)])""")
        esperado = {"Linha": [c["linha"]], "Coluna": [c["coluna"]], "Incremento": c["incrementos"],
                    "Arquivos": c["arquivos"], **c["filtros"]}
        for nome, sel in estado:
            if sorted(sel) != sorted(esperado.get(nome, [TODAS])):
                raise ValueError(f"formulário com seleção inesperada em {nome}: {sel}")
        if page.query_selector("input[name=zeradas]") and not page.is_checked("input[name=zeradas]"):
            raise ValueError("'Exibir linhas zeradas' não ficou marcado")
        print_form = page.screenshot(full_page=True)

        with ctx.expect_page(timeout=180_000) as nova:
            page.click("input[name=mostre]")
        res = nova.value
        res.wait_for_load_state("load", timeout=180_000)
        momento = datetime.now()
        tabela = ler_tabela_html(res.content())
        problemas = validar_resultado(c, tabela)

        destino.parent.mkdir(parents=True, exist_ok=True)
        carimbo = momento.strftime("%d/%m/%Y %H:%M:%S")
        pdf = png = png_form = None
        if self.evidencias in ("pdf_png", "pdf"):
            pdf = destino.with_suffix(".pdf")
            largura = res.evaluate("Math.max(document.documentElement.scrollWidth, 1100)")
            rodape = (f'<div style="font-size:8px;width:100%;padding:0 8mm;font-family:Arial">'
                      f'Consultado em {carimbo} &mdash; Formulário: {url_form} &mdash; Resultado: {res.url}'
                      f'<span style="float:right">pág. <span class="pageNumber"></span>/'
                      f'<span class="totalPages"></span></span></div>')
            res.pdf(path=str(pdf), width=f"{largura + 60}px", height="794px", print_background=True,
                    display_header_footer=True, header_template="<span></span>", footer_template=rodape,
                    margin={"top": "8mm", "bottom": "14mm", "left": "6mm", "right": "6mm"})
        legenda = [f"Consultado em {carimbo}   |   Formulário: {url_form}",
                   f"Período: {', '.join(c['periodos'])}   |   Filtros: {descrever_filtros(c)}"]
        if self.evidencias == "pdf_png":
            png = destino.with_suffix(".png")
            res.screenshot(path=str(png), full_page=True)
            legenda_png(png, legenda)
            if tabela["sem_registro"]:
                png_form = destino.with_name(destino.name + " - FORMULARIO (sem registro).png")
                png_form.write_bytes(print_form)
                legenda_png(png_form, legenda + ["Resposta do site: Nenhum registro selecionado"])

        def rel(p):
            return str(p.relative_to(self.pasta)) if p else None

        return {
            "consultado_em": momento.isoformat(timespec="seconds"),
            "url_formulario": url_form,
            "url_resultado": res.url,
            "sem_registro": tabela["sem_registro"],
            "titulo": tabela["titulo"],
            "colunas": tabela["colunas"],
            "linhas": tabela["linhas"],
            "problemas": problemas,
            "pdf": rel(pdf),
            "png": rel(png),
            "png_formulario": rel(png_form),
        }
