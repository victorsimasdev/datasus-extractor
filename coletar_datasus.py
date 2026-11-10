"""
Coleta automática do TabNet/DATASUS com evidências (PDF + PNG de cada tabela).

Morbidade Hospitalar do SUS (SIH/SUS) - "Geral, por local de internação - a partir de 2008"
Para cada estado e mês, o script abre o formulário do TabNet num Chrome real (sem janela)
e faz os mesmos passos feitos à mão:
  Linha     = Município            Coluna = Não ativa
  Conteúdo  = Internações, Valor médio intern, Média permanência, Óbitos
  Período   = o mês da consulta
  Lista Morb CID-10 = Transtornos de condução e arritmias cardíacas
  -> clica em "Mostra"
Os números são lidos da própria página de resultado, a mesma que é salva como evidência.

Também consulta o TabNet nacional (Brasil por UF e por Região) com os mesmos filtros:
  - conferência cruzada de cada estado (duas consultas independentes têm de bater);
  - linhas NORTE ... SUL e BRASIL - TOTAL (médias calculadas pelo próprio TabNet).

Uso:
  python coletar_datasus.py --demo    -> 3 casos + 1 nacional, em evidencias_demo/
  python coletar_datasus.py           -> tudo (27 estados x 14 meses + nacional), em evidencias/
Se for interrompido, rodar de novo continua de onde parou.
"""
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from comum import DadosCorrompidos, gravar_json, ler_json

BASE = "https://tabnet.datasus.gov.br/cgi"
CID_VALOR = "174"
CID_ROTULO = "Transtornos de condução e arritmias cardíacas"
CONTEUDOS = ["Internações", "Valor_médio_intern", "Média_permanência", "Óbitos"]
CABECALHO = ["Internações", "Valor médio intern", "Média permanência", "Óbitos"]
CAMPOS = ["internacoes", "valor_medio", "media_perm", "obitos"]

# sigla -> (nome no título do TabNet, nome da pasta/planilha)
UFS = {
    "ac": ("Acre", "ACRE"), "al": ("Alagoas", "ALAGOAS"), "am": ("Amazonas", "AMAZONAS"),
    "ap": ("Amapá", "AMAPÁ"), "ba": ("Bahia", "BAHIA"), "ce": ("Ceará", "CEARÁ"),
    "df": ("Distrito Federal", "DISTRITO FEDERAL"), "es": ("Espírito Santo", "ESPÍRITO SANTO"),
    "go": ("Goiás", "GOIÁS"), "ma": ("Maranhão", "MARANHÃO"), "mt": ("Mato Grosso", "MATO GROSSO"),
    "ms": ("Mato Grosso do Sul", "MATO GROSSO DO SUL"), "mg": ("Minas Gerais", "MINAS GERAIS"),
    "pa": ("Pará", "PARÁ"), "pb": ("Paraíba", "PARAÍBA"), "pr": ("Paraná", "PARANÁ"),
    "pe": ("Pernambuco", "PERNAMBUCO"), "pi": ("Piauí", "PIAUÍ"),
    "rj": ("Rio de Janeiro", "RIO DE JANEIRO"), "rn": ("Rio Grande do Norte", "RIO GRANDE DO NORTE"),
    "rs": ("Rio Grande do Sul", "RIO GRANDE DO SUL"), "ro": ("Rondônia", "RONDÔNIA"),
    "rr": ("Roraima", "RORAIMA"), "sc": ("Santa Catarina", "SANTA CATARINA"),
    "sp": ("São Paulo", "SÃO PAULO"), "se": ("Sergipe", "SERGIPE"), "to": ("Tocantins", "TOCANTINS"),
}
MESES = [(2025, m) for m in range(7, 13)] + [(2026, m) for m in range(1, 9)]
ABA = ["", "JAN", "FEV", "MAR", "ABR", "MAIO", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
ROTULO_MES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

CASOS_DEMO = [("df", 2025, 8), ("ac", 2025, 7), ("ac", 2026, 8)]
NACIONAL_DEMO = [(2025, 8)]

PASTA = Path(__file__).resolve().parent
PASTA_NACIONAL = "_BRASIL (conferência nacional)"


def normaliza(txt):
    return re.sub(r"\s+", " ", txt).strip()


def num_br(s):
    s = s.strip()
    if s == "-":  # TabNet: "dado numérico igual a 0 não resultante de arredondamento"
        return 0
    if s == "...":  # TabNet: "dado numérico não disponível" (ex.: valor médio de município com 0 internações)
        return None
    return float(s.replace(".", "").replace(",", "."))


def legenda_png(caminho_png, linhas):
    """Põe uma faixa ACIMA do print (fora da página) com endereço e data/hora da consulta."""
    img = Image.open(caminho_png).convert("RGB")
    fonte = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    altura = 12 + 22 * len(linhas)
    nova = Image.new("RGB", (img.width, img.height + altura), (40, 40, 40))
    d = ImageDraw.Draw(nova)
    for i, l in enumerate(linhas):
        d.text((10, 8 + 22 * i), l, fill=(255, 255, 255), font=fonte)
    nova.paste(img, (0, altura))
    nova.save(caminho_png)


class Coletor:
    def __init__(self, pw, pasta_evid, conteudos=CONTEUDOS, cabecalho=CABECALHO, campos=CAMPOS):
        self.browser = pw.chromium.launch(channel="chrome", headless=True)
        self.pasta_evid = pasta_evid
        self.conteudos, self.cabecalho, self.campos = conteudos, cabecalho, campos

    def consultar(self, def_name, arquivo_dbf, linha, titulo_esperado, destino_base, filtro=None):
        """Faz uma consulta completa no site e devolve o dicionário com tabela e evidências.
        filtro = (nome do select, valor, texto esperado no resultado), ex.:
                 ("SSexo", "2", "Sexo: Fem")  -> além do CID, seleciona só essa categoria."""
        ultimo_erro = None
        for tentativa in range(1, 11):
            ctx = self.browser.new_context(viewport={"width": 1280, "height": 720}, locale="pt-BR")
            try:
                return self._consultar(ctx, def_name, arquivo_dbf, linha, titulo_esperado, destino_base, filtro)
            except Exception as e:
                ultimo_erro = e
                espera = min(60, 5 * tentativa)
                print(f"      tentativa {tentativa} falhou ({type(e).__name__}: {str(e)[:120]}); "
                      f"nova tentativa em {espera}s", flush=True)
                time.sleep(espera)
            finally:
                ctx.close()
        raise RuntimeError(f"Desisti após 10 tentativas: {ultimo_erro}")

    def _consultar(self, ctx, def_name, arquivo_dbf, linha, titulo_esperado, destino_base, filtro):
        page = ctx.new_page()
        page.set_default_timeout(180_000)
        url_form = f"{BASE}/deftohtm.exe?{def_name}"
        page.goto(url_form, wait_until="load", timeout=180_000)

        rotulo_mes = page.eval_on_selector(
            f'select[name=Arquivos] option[value="{arquivo_dbf}"]', "o => o.textContent.trim()")
        rotulo_linha = page.eval_on_selector(
            f'select[name=Linha] option[value="{linha}"]', "o => o.textContent.trim()")

        page.select_option("select[name=Linha]", [linha])
        page.select_option("select[name=Coluna]", ["--Não-Ativa--"])
        page.select_option("select[name=Incremento]", self.conteudos)
        page.select_option("select[name=Arquivos]", [arquivo_dbf])
        # abre o "+ Lista Morb CID-10" (e o do filtro extra) e escolhe a categoria, como na tela
        selecoes = {"SLista_Morb__CID-10": CID_VALOR}
        if filtro:
            selecoes[filtro[0]] = filtro[1]
        for nome_sel, valor in selecoes.items():
            sid = page.eval_on_selector(f'select[name="{nome_sel}"]', "s => s.id")
            page.click(f"#fig{sid[1:]}")
            page.select_option(f"#{sid}", [valor])

        # confere o formulário inteiro antes de enviar
        estado_form = page.evaluate("""() => [...document.querySelectorAll('form select')]
            .filter(s => !s.name.startsWith('listahidden'))
            .map(s => [s.name, [...s.selectedOptions].map(o => o.value)])""")
        for nome, sel in estado_form:
            if nome == "Linha":
                ok = sel == [linha]
            elif nome == "Coluna":
                ok = sel == ["--Não-Ativa--"]
            elif nome == "Incremento":
                ok = sel == self.conteudos
            elif nome == "Arquivos":
                ok = sel == [arquivo_dbf]
            elif nome in selecoes:
                ok = sel == [selecoes[nome]]
            else:
                ok = sel == ["TODAS_AS_CATEGORIAS__"]
            if not ok:
                raise ValueError(f"Formulário com seleção inesperada em {nome}: {sel}")
        if not page.is_checked('input[name=formato][value=table]'):
            raise ValueError("Formato de saída não é 'Tabela com bordas'")

        # print do formulário preenchido (usado como evidência quando não há registro):
        # cada lista é rolada até o item escolhido e a de Conteúdo é aberta por inteiro
        page.evaluate("""() => {
            const inc = document.querySelector('select[name=Incremento]');
            inc.size = inc.options.length;
            for (let e = inc.parentElement; e && e.tagName !== 'FORM'; e = e.parentElement)
                e.style.height = 'auto';  // as caixas têm altura fixa no CSS do site
            for (const s of document.querySelectorAll('form select')) {
                const o = s.selectedOptions[0];
                if (o) s.scrollTop = o.offsetTop - s.offsetTop - 2;
            }
        }""")
        print_form = page.screenshot(full_page=True)

        with ctx.expect_page(timeout=180_000) as nova:
            page.click("input[name=mostre]")
        res = nova.value
        res.wait_for_load_state("load", timeout=180_000)
        momento = datetime.now()
        texto = normaliza(res.inner_text("body"))

        # A página "Nenhum registro selecionado" não traz título, filtro nem período;
        # nesse caso a prova da consulta é o print do formulário conferido acima.
        sem_registro = texto.lower().endswith("nenhum registro selecionado")
        if not sem_registro:
            for trecho in (f"por local de internação - {titulo_esperado}",
                           f"Lista Morb CID-10: {CID_ROTULO}",
                           f"Período: {rotulo_mes}") + ((filtro[2],) if filtro else ()):
                if trecho.lower() not in texto.lower():
                    raise ValueError(f"Página de resultado não contém: {trecho!r}")
        tabela = None
        if not sem_registro:
            cab = res.eval_on_selector_all("table.tabdados thead tr[valign] th",
                                           "ths => ths.map(t => t.innerText.trim())")
            if cab != [rotulo_linha] + self.cabecalho:
                raise ValueError(f"Cabeçalho inesperado: {cab}")
            linhas = res.eval_on_selector_all("table.tabdados tbody tr",
                                              "trs => trs.map(tr => [...tr.cells].map(c => c.innerText.trim()))")
            tabela = {}
            for cel in linhas:
                if len(cel) != 1 + len(self.campos):
                    continue
                nome = cel[0]
                if nome in tabela:
                    raise ValueError(f"Linha repetida na tabela: {nome}")
                tabela[nome] = {"texto_site": cel[1:], **{c: num_br(v) for c, v in zip(self.campos, cel[1:])}}
            if not any(k.upper() == "TOTAL" for k in tabela):
                raise ValueError("Tabela sem linha TOTAL")

        # evidências
        destino_base.parent.mkdir(parents=True, exist_ok=True)
        carimbo = momento.strftime("%d/%m/%Y %H:%M:%S")
        rodape = (f'<div style="font-size:8px;width:100%;padding:0 10mm;font-family:Arial">'
                  f'Consultado em {carimbo} &mdash; Formulário: {url_form} &mdash; Resultado: {res.url}'
                  f'<span style="float:right">pág. <span class="pageNumber"></span>/'
                  f'<span class="totalPages"></span></span></div>')
        pdf = destino_base.with_suffix(".pdf")
        png = destino_base.with_suffix(".png")
        res.pdf(path=str(pdf), format="A4", landscape=True, print_background=True,
                display_header_footer=True, header_template="<span></span>", footer_template=rodape,
                margin={"top": "8mm", "bottom": "14mm", "left": "6mm", "right": "6mm"})
        res.screenshot(path=str(png), full_page=True)
        extra = f"   |   {filtro[2]}" if filtro else ""
        legenda_png(png, [f"Consultado em {carimbo}   |   Formulário: {url_form}",
                          f"Resultado: {res.url}   |   Período: {rotulo_mes}   |   Lista Morb CID-10: {CID_ROTULO}{extra}"])
        png_form = None
        if sem_registro:
            png_form = destino_base.with_name(destino_base.name + " - FORMULARIO (sem registro).png")
            png_form.write_bytes(print_form)
            legenda_png(png_form, [f"Formulário preenchido e enviado em {carimbo}   |   {url_form}",
                                   f"Período: {rotulo_mes}   |   Lista Morb CID-10: {CID_ROTULO}{extra}   |   "
                                   f"Resposta do site: Nenhum registro selecionado"])

        return {
            "consultado_em": momento.isoformat(timespec="seconds"),
            "url_formulario": url_form,
            "url_resultado": res.url,
            "periodo": rotulo_mes,
            "sem_registro": sem_registro,
            "tabela": tabela,
            "pdf": str(pdf.relative_to(PASTA)),
            "png": str(png.relative_to(PASTA)),
            "png_formulario": str(png_form.relative_to(PASTA)) if png_form else None,
            "formulario": estado_form,
        }


def main():
    demo = "--demo" in sys.argv
    pasta_evid = PASTA / ("evidencias_demo" if demo else "evidencias")
    arq_dados = PASTA / ("dados_demo.json" if demo else "dados_coletados.json")
    try:
        dados = ler_json(arq_dados, {})
    except DadosCorrompidos as e:
        sys.exit(f"ERRO: {e}. Restaure a cópia de segurança antes de continuar.")

    casos = CASOS_DEMO if demo else [(uf, a, m) for uf in UFS for a, m in MESES]
    nacionais = NACIONAL_DEMO if demo else MESES
    total = len(casos) + 2 * len(nacionais)
    feitos = 0

    def salvar():  # gravação atômica: uma interrupção nunca deixa o JSON pela metade
        gravar_json(arq_dados, dados)

    with sync_playwright() as pw:
        col = Coletor(pw, pasta_evid)
        for uf, ano, mes in casos:
            feitos += 1
            chave = f"{uf}|{ano}-{mes:02d}"
            if chave in dados:
                continue
            titulo, pasta_nome = UFS[uf]
            destino = pasta_evid / pasta_nome / f"{ano}-{mes:02d} - {ABA[mes]} {ano} - {pasta_nome}"
            print(f"[{feitos}/{total}] {pasta_nome} {ROTULO_MES[mes]}/{ano}...", flush=True)
            r = col.consultar(f"sih/cnv/ni{uf}.def", f"ni{uf}{ano % 100:02d}{mes:02d}.dbf",
                              "Município", titulo, destino)
            r["uf"] = uf
            dados[chave] = r
            salvar()
            if r["sem_registro"]:
                print("      Nenhum registro selecionado -> SR", flush=True)
            else:
                t = next(v for k, v in r["tabela"].items() if k.upper() == "TOTAL")
                print(f"      TOTAL: {' | '.join(t['texto_site'])}", flush=True)

        for ano, mes in nacionais:
            for linha, sufixo in (("Unidade_da_Federação", "por UF"), ("Região", "por Região")):
                feitos += 1
                chave = f"BR-{linha}|{ano}-{mes:02d}"
                if chave in dados:
                    continue
                destino = pasta_evid / PASTA_NACIONAL / f"{ano}-{mes:02d} - {ABA[mes]} {ano} - BRASIL {sufixo}"
                print(f"[{feitos}/{total}] BRASIL {sufixo} {ROTULO_MES[mes]}/{ano}...", flush=True)
                r = col.consultar("sih/cnv/niuf.def", f"niuf{ano % 100:02d}{mes:02d}.dbf",
                                  linha, "Brasil", destino)
                dados[chave] = r
                salvar()
                print(f"      {len(r['tabela'] or {})} linhas", flush=True)
    print("Concluído.")


if __name__ == "__main__":
    main()
