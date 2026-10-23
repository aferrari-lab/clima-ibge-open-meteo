"""Acesso de leitura ao banco DuckDB."""
import duckdb


def consultar(sql, db_path, params=None):
    """Roda um SELECT no banco (somente leitura) e devolve um DataFrame.

    Use `?` no SQL e passe os valores em `params`, em vez de montar o texto na mão.
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql, params or []).fetchdf()
