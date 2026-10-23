"""Linha de comando: python -m clima [--uf BR|SP|...] [--todas] [--inicio AAAA-MM-DD] [--limite N]."""
import argparse
import sys
from datetime import date

from .cidades import BRASIL, carregar_municipios, representativas
from .open_meteo import INICIO_PADRAO, atualizar_clima


def main():
    p = argparse.ArgumentParser(prog="python -m clima", description="Carga incremental de clima (Open-Meteo -> DuckDB).")
    p.add_argument("--db", default="dados/warehouse.duckdb", help="arquivo DuckDB (padrão: dados/warehouse.duckdb)")
    p.add_argument("--uf", default=BRASIL, help="sigla de uma UF (ex.: SP) ou BR para o Brasil inteiro (padrão: BR)")
    p.add_argument("--todas", action="store_true",
                   help="todos os municípios (padrão: uma cidade por região imediata)")
    p.add_argument("--inicio", type=date.fromisoformat, default=INICIO_PADRAO,
                   help=f"primeiro dia do histórico, AAAA-MM-DD (padrão: {INICIO_PADRAO})")
    p.add_argument("--limite", type=int, help="usar só as N primeiras cidades (teste rápido)")
    args = p.parse_args()

    cidades = carregar_municipios(args.db, args.uf)
    if cidades.empty:
        sys.exit(f"Nenhum município encontrado para '{args.uf}'. Use a sigla de uma UF ou BR.")
    if not args.todas:
        cidades = representativas(cidades)
    if args.limite:
        cidades = cidades.head(args.limite)
    print(f"{len(cidades)} cidades em {cidades['uf_sigla'].nunique()} UF(s), histórico desde {args.inicio}")

    concluiu = atualizar_clima(cidades, args.db, inicio=args.inicio)
    sys.exit(0 if concluiu else 2)   # 2 = parou por limite de uso; rode de novo mais tarde


if __name__ == "__main__":
    main()
