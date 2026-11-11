"""
Pedido -> plano de coleta: a lista exata de consultas ao TabNet e o layout da planilha.

O pedido é o JSON gerado pela janela. Regras do site que o plano respeita (testadas no site):
  - várias opções marcadas no mesmo filtro, ou vários períodos, viram UM resultado, somado;
  - o mesmo campo pode ser Coluna e filtro ao mesmo tempo: a tabela traz só as categorias filtradas;
  - com Coluna ativa, o site aceita um conteúdo só por consulta.

Cada consulta tem uma chave estável: a coleta usa a chave para retomar de onde parou.
"""
import itertools
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .formularios import NAO_ATIVA, Formulario, carregar_opcoes, normaliza

REGIOES = ["NORTE", "NORDESTE", "CENTRO-OESTE", "SUDESTE", "SUL"]
OBRIGATORIOS = ("nome", "base", "abrangencia", "linha", "conteudos", "periodos")


class PedidoInvalido(Exception):
    pass


@dataclass
class Consulta:
    chave: str
    aba: str
    uf: str | None
    caminho_def: str
    linha: str  # valor do select Linha
    linha_tipo: str  # "principal" ou "regioes"
    coluna: str  # valor do select Coluna (NAO_ATIVA se não houver)
    conteudos: list  # rótulos
    incrementos: list  # valores do select Incremento
    periodos: list  # rótulos ("Jul/2025")
    arquivos: list  # valores do select Arquivos
    filtros: dict  # select -> [valores]
    filtros_rotulos: dict  # rótulo do campo -> [rótulos das opções] (para conferir o cabeçalho do resultado)
    papel: dict = field(default_factory=dict)
    ordenar: bool = False

    def para_dict(self):
        return asdict(self)


@dataclass
class ColunaPlanilha:
    grupo: str | None  # None = conteúdos do total; "=TOTAL" = cópia do total ao lado dos blocos; senão título do bloco
    subcoluna: str
    conteudo: str


@dataclass
class LinhaPlanilha:
    rotulo: str  # como aparece na planilha
    uf: str | None
    tipo: str  # "principal", "regioes" ou "separador"
    chave: str = ""  # rótulo sem o código (ver chave_linha), para casar quando o site escreve diferente
    site: str = ""  # rótulo como no formulário/site, para casar exato (ver planilha.casar_rotulos)


@dataclass
class Plano:
    pedido: dict
    consultas: list
    colunas: list
    linhas: list  # por uf: linhas esperadas (as dinâmicas são completadas na planilha)
    linhas_dinamicas: bool
    abas: list
    avisos: list


def chave_linha(rotulo):
    """'12 Acre' e 'Acre' -> 'acre';  '1 Região Norte' -> 'norte';  '120001 ACRELANDIA' -> 'acrelandia'."""
    s = normaliza(rotulo)
    s = re.sub(r"^\d+\s+", "", s)
    s = re.sub(r"^regiao\s+", "", s)
    return s


def carregar(caminho):
    pedido = json.loads(Path(caminho).read_text(encoding="utf-8"))
    validar(pedido)
    return pedido


def validar(pedido):
    faltando = [k for k in OBRIGATORIOS if not pedido.get(k)]
    if faltando:
        raise PedidoInvalido(f"pedido sem: {', '.join(faltando)}")
    if pedido["abrangencia"] == "estadual" and not pedido.get("estados"):
        raise PedidoInvalido("pedido por estado sem nenhum estado")
    if pedido["base"] not in carregar_opcoes():
        raise PedidoInvalido(f"base desconhecida: {pedido['base']}")


def _regioes_aplicaveis(pedido):
    return (pedido["abrangencia"] == "nacional" and normaliza(pedido["linha"]) == normaliza("Unidade da Federação")
            and pedido.get("layout", {}).get("brasil_e_regioes", False))


def _valores_para_uf(valores, uf):
    """Filtros de campos que só existem por estado chegam como 'uf|valor'. Devolve os valores deste
    formulário (sem prefixo) e se o campo tinha valores de outros estados."""
    proprios, de_outros = [], False
    for v in valores:
        if "|" in v:
            u, real = v.split("|", 1)
            if u == uf:
                proprios.append(real)
            else:
                de_outros = True
        else:
            proprios.append(v)
    return proprios, de_outros


def planejar(pedido, opcoes=None):
    """Expande o pedido nas consultas e no layout da planilha."""
    validar(pedido)
    opcoes = opcoes or carregar_opcoes()
    avisos = []
    base = pedido["base"]
    ufs = pedido["estados"] if pedido["abrangencia"] == "estadual" else [None]
    conts = list(pedido["conteudos"])
    cb = [c for c in pedido.get("layout", {}).get("conteudos_nos_blocos", []) if c in conts] or conts[:1]
    linha_rot = pedido["linha"]
    filtros = pedido.get("filtros", {})
    campo_linha = next((f for f in filtros if normaliza(f) == normaliza(linha_rot)), None)
    ordem = pedido.get("ordem_dos_blocos") or list(filtros)
    ordem += [f for f in filtros if f not in ordem]
    var = {f: filtros[f] for f in ordem if f in filtros and len(filtros[f]) > 1 and f != campo_linha}
    fixos = {f: its for f, its in filtros.items() if len(its) == 1 and f != campo_linha}
    titulos = {f: pedido.get("titulos_dos_blocos", {}).get(f, f.upper()) for f in var}
    cruzar = pedido.get("combinar_filtros") == "cruzar" and len(var) > 1
    regioes = _regioes_aplicaveis(pedido)
    tipos_linha = ["principal"] + (["regioes"] if regioes else [])
    ordenar = bool(pedido.get("ordenar_pelos_valores"))

    consultas, linhas, dinamicas = [], [], False
    for uf in ufs:
        form = Formulario(base, uf, opcoes)
        pre = f"{uf.upper()} · " if len(ufs) > 1 else ""
        if form.valor_linha(linha_rot) is None:
            raise PedidoInvalido(f"linha '{linha_rot}' não existe no formulário {form.caminho_def}")
        valores_conteudos = form.valores_conteudo(conts)
        if None in valores_conteudos:
            raise PedidoInvalido(f"conteúdo inexistente em {form.caminho_def}: "
                                 f"{[c for c, v in zip(conts, valores_conteudos) if v is None]}")

        # filtros aplicados a todas as consultas deste formulário
        def converter(campo, valores):
            sel = form.select_do_filtro(campo)
            if sel is None:
                raise PedidoInvalido(f"filtro '{campo}' não existe em {form.caminho_def}")
            proprios, de_outros = _valores_para_uf(valores, uf)
            return sel, proprios, de_outros

        comuns, pular_uf = {}, False
        for campo, its in fixos.items():
            sel, vals, outros = converter(campo, its[0]["valores"])
            if not vals and outros:
                pular_uf = True
            comuns[sel] = vals
        restricao_linha = {}
        if campo_linha:
            vals_linha = [v for it in filtros[campo_linha] if it["tipo"] == "separada" for v in it["valores"]]
            sel, vals, outros = converter(campo_linha, vals_linha)
            if not vals and outros:
                pular_uf = True
            if vals:
                restricao_linha[sel] = vals

        # linhas da planilha deste formulário
        cats = form.categorias(linha_rot)
        if campo_linha and restricao_linha:
            sel = form.select_do_filtro(campo_linha)
            esperadas = [form.rotulo_opcao(sel, v) for v in restricao_linha[sel]]
        elif cats is not None:
            esperadas = [lbl for _, lbl in cats]
        else:
            esperadas, dinamicas = [], True
        if linhas:
            linhas.append(LinhaPlanilha("", uf, "separador"))
        linhas += [LinhaPlanilha(pre + lbl.upper(), uf, "principal", chave_linha(lbl), lbl) for lbl in esperadas]
        if pular_uf:
            avisos.append(f"{form.caminho_def}: nenhum filtro escolhido existe neste estado; linhas ficam SR")
        if regioes:
            linhas.append(LinhaPlanilha("", uf, "separador"))
            linhas.append(LinhaPlanilha("BRASIL - TOTAL", uf, "principal", "total", "Total"))
            linhas += [LinhaPlanilha(r, uf, "regioes", chave_linha(r), r) for r in REGIOES]
        else:
            if esperadas and not dinamicas:
                linhas.append(LinhaPlanilha("", uf, "separador"))
            linhas.append(LinhaPlanilha(pre + "TOTAL", uf, "principal", "total", "Total"))
        if pular_uf:
            continue

        def nova(aba, per_rot, arquivos, tipo, coluna, cont_rot, filtros_extra, papel, descr):
            filtros_q = dict(comuns)
            if tipo == "principal":
                filtros_q.update(restricao_linha)
            filtros_q.update(filtros_extra)
            rotulos = {}
            for sel, vals in filtros_q.items():
                rotulos[next(r for r, n in form.filtros.items() if n == sel)] = [form.rotulo_opcao(sel, v) for v in vals]
            linha_valor = form.valor_linha("Região") if tipo == "regioes" else form.valor_linha(linha_rot)
            chave = f"{aba}|{uf or 'BR'}|{tipo}|{descr}|{'+'.join(cont_rot)}"
            return Consulta(chave=chave, aba=aba, uf=uf, caminho_def=form.caminho_def, linha=linha_valor,
                            linha_tipo=tipo, coluna=coluna, conteudos=list(cont_rot),
                            incrementos=form.valores_conteudo(cont_rot), periodos=per_rot, arquivos=arquivos,
                            filtros=filtros_q, filtros_rotulos=rotulos, papel=papel, ordenar=ordenar)

        for it_per in pedido["periodos"]:
            aba = it_per["nome"]
            arquivos = [form.arquivo(p) for p in it_per["valores"]]
            if None in arquivos:
                avisos.append(f"{form.caminho_def}: período {aba} não disponível; células ficam SR")
                continue
            for tipo in tipos_linha:
                def add(*a):
                    consultas.append(nova(aba, it_per["valores"], arquivos, tipo, *a))

                add(NAO_ATIVA, conts, {}, {"tipo": "base"}, "base")
                for tipo_col in pedido.get("colunas", []):
                    col = form.valor_coluna(tipo_col)
                    if col is None:
                        raise PedidoInvalido(f"coluna '{tipo_col}' não existe em {form.caminho_def}")
                    cats_col = form.categorias(tipo_col)
                    mapa = {chave_linha(lbl): lbl for _, lbl in cats_col} if cats_col else {}
                    for c in cb:
                        add(col, [c], {}, {"tipo": "coluna", "bloco": tipo_col.upper(), "mapa": mapa},
                            f"coluna:{tipo_col}")
                if cruzar:
                    nomes = list(var)
                    for combo in itertools.product(*[var[f] for f in nomes]):
                        extra, ok = {}, True
                        for f, it in zip(nomes, combo):
                            sel, vals, _ = converter(f, it["valores"])
                            ok &= bool(vals)
                            extra[sel] = vals
                        if ok:
                            sub = " · ".join(it["nome"] for it in combo)
                            add(NAO_ATIVA, cb, extra, {"tipo": "bloco", "bloco": " × ".join(titulos[f] for f in nomes),
                                                       "modo": "total", "subcoluna": sub}, f"cruz:{sub}")
                    continue
                for campo, its in var.items():
                    sel = form.select_do_filtro(campo)
                    if sel is None:
                        raise PedidoInvalido(f"filtro '{campo}' não existe em {form.caminho_def}")
                    sep = [it for it in its if it["tipo"] == "separada"]
                    grupos = [it for it in its if it["tipo"] == "grupo"]
                    col_campo = form.coluna_do_filtro(campo)
                    if sep and col_campo:
                        vals, mapa = [], {}
                        for it in sep:
                            _, v, _ = converter(campo, it["valores"])
                            for real in v:
                                vals.append(real)
                                mapa[form.rotulo_opcao(sel, real)] = it["nome"]
                        if vals:
                            for c in cb:
                                add(form.valor_coluna(col_campo), [c], {sel: vals},
                                    {"tipo": "bloco", "bloco": titulos[campo], "modo": "coluna", "mapa": mapa},
                                    f"bloco:{campo}:coluna")
                    else:
                        grupos = sep + grupos
                    for it in grupos:
                        _, vals, _ = converter(campo, it["valores"])
                        if vals:
                            add(NAO_ATIVA, cb, {sel: vals},
                                {"tipo": "bloco", "bloco": titulos[campo], "modo": "total", "subcoluna": it["nome"]},
                                f"bloco:{campo}:{it['tipo']}:{it['nome']}")

    # colunas da planilha
    colunas = [ColunaPlanilha(None, c, c) for c in conts]
    blocos = []
    form0 = Formulario(base, ufs[0], opcoes)
    for tipo_col in pedido.get("colunas", []):
        cats_col = form0.categorias(tipo_col)
        blocos.append((tipo_col.upper(), [lbl for _, lbl in cats_col] if cats_col else None))
    if cruzar:
        nomes = list(var)
        blocos.append((" × ".join(titulos[f] for f in nomes),
                       [" · ".join(it["nome"] for it in combo) for combo in itertools.product(*[var[f] for f in nomes])]))
    else:
        for campo, its in var.items():
            blocos.append((titulos[campo], [it["nome"] for it in its]))
    if blocos:
        colunas += [ColunaPlanilha("=TOTAL", c.upper(), c) for c in cb]
    for titulo, subs in blocos:
        if subs is None:
            colunas.append(ColunaPlanilha(titulo, "*", cb[0]))  # categorias decididas pelo que o site trouxer
            continue
        for s in subs:
            for c in cb:
                colunas.append(ColunaPlanilha(titulo, s, c))
    abas = [it["nome"] for it in pedido["periodos"]]
    return Plano(pedido=pedido, consultas=consultas, colunas=colunas, linhas=linhas,
                 linhas_dinamicas=dinamicas, abas=abas, avisos=avisos)
