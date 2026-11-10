"""
Uso:
  python -m extrator                          abre a janela para montar um pedido
  python -m extrator rodar PEDIDO.json        coleta, monta a planilha e confere (retoma de onde parou)
  python -m extrator planilha PASTA           monta de novo a planilha a partir de uma coleta
  python -m extrator conferir PLANILHA.xlsx   conferência independente pelos PDFs
  python -m extrator atualizar-opcoes         relê no site as opções dos formulários
"""
import argparse
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m extrator", description="Extrator de dados do TabNet/DATASUS")
    sub = p.add_subparsers(dest="comando")
    r = sub.add_parser("rodar", help="coleta, monta a planilha e confere")
    r.add_argument("pedido")
    r.add_argument("--mostrar-navegador", action="store_true", help="abre o Chrome visível durante a coleta")
    r.add_argument("--limite-horas", type=float, default=72)
    pl = sub.add_parser("planilha", help="monta de novo a planilha de uma coleta")
    pl.add_argument("pasta")
    c = sub.add_parser("conferir", help="conferência independente pelos PDFs")
    c.add_argument("planilha")
    sub.add_parser("atualizar-opcoes", help="relê no site as opções dos formulários")
    sub.add_parser("janela", help="abre a janela de pedido")
    a = p.parse_args(argv)

    if a.comando in (None, "janela"):
        from .janela import abrir

        abrir()
        return 0
    if a.comando == "rodar":
        from .rodar import rodar

        return rodar(a.pedido, headless=not a.mostrar_navegador, limite_horas=a.limite_horas)
    if a.comando == "planilha":
        from .rodar import regerar_planilha

        return regerar_planilha(a.pasta)
    if a.comando == "conferir":
        from .conferencia import conferir

        return 1 if conferir(a.planilha) else 0
    if a.comando == "atualizar-opcoes":
        from .formularios import atualizar_opcoes

        print(f"Gravado: {atualizar_opcoes()}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
