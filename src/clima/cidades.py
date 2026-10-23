"""Seleção das cidades para a carga de clima."""
from .db import consultar

COLUNAS = ["ibge_id", "nome", "lat", "lng", "fuso_horario"]


def carregar_municipios(db_path, uf="SP"):
    """Municípios de uma UF, com coordenadas, fuso e região imediata (tabela bronze.ibge_municipios)."""
    return consultar(
        """
        select ibge_id, nome, regiao_imediata, lat, lng, fuso_horario
        from bronze.ibge_municipios
        where uf_sigla = ?
        order by ibge_id
        """,
        db_path,
        [uf],
    )


def representativas(municipios):
    """Uma cidade por região imediata: a mais próxima do centro (média das coordenadas) da região.

    Municípios vizinhos têm séries de clima quase iguais; usar uma cidade por região reduz muito
    o consumo do limite de uso da API sem perder a variação regional.
    """
    m = municipios.copy()
    grupo = m.groupby("regiao_imediata")
    m["_dist"] = (m["lat"] - grupo["lat"].transform("mean")) ** 2 + (m["lng"] - grupo["lng"].transform("mean")) ** 2
    escolhidas = m.groupby("regiao_imediata")["_dist"].idxmin()
    return m.loc[escolhidas, COLUNAS].reset_index(drop=True)
