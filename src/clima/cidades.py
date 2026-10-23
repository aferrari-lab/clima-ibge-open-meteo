"""Seleção das cidades para a carga de clima."""
from .db import consultar

COLUNAS = ["ibge_id", "nome", "uf_sigla", "lat", "lng", "fuso_horario"]
BRASIL = "BR"


def carregar_municipios(db_path, uf=BRASIL):
    """Municípios com coordenadas, fuso e região imediata (tabela bronze.ibge_municipios).

    `uf` é a sigla de uma UF (ex.: "SP") ou "BR" para o Brasil inteiro.
    """
    uf = uf.upper()
    return consultar(
        """
        select ibge_id, nome, uf_sigla, regiao_imediata, lat, lng, fuso_horario
        from bronze.ibge_municipios
        where ? = 'BR' or uf_sigla = ?
        order by uf_sigla, ibge_id
        """,
        db_path,
        [uf, uf],
    )


def representativas(municipios):
    """Uma cidade por região imediata: a mais próxima do centro (média das coordenadas) da região.

    Municípios vizinhos têm séries de clima quase iguais; usar uma cidade por região reduz muito
    o consumo do limite de uso da API sem perder a variação regional. A região é identificada
    por UF + nome, porque há nomes de região repetidos em estados diferentes.
    """
    m = municipios.copy()
    chave = ["uf_sigla", "regiao_imediata"]
    grupo = m.groupby(chave)
    m["_dist"] = (m["lat"] - grupo["lat"].transform("mean")) ** 2 + (m["lng"] - grupo["lng"].transform("mean")) ** 2
    escolhidas = m.groupby(chave)["_dist"].idxmin()
    return m.loc[escolhidas, COLUNAS].reset_index(drop=True)
