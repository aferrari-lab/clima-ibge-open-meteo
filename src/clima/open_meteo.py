"""Carga incremental de clima diário (Open-Meteo) em um banco DuckDB.

Para cada município, busca na API de histórico (archive) os dias que faltam até D-5 e, na API de
previsão, os dias mais recentes (provisórios, marcados como 'forecast'). Tudo vai para
bronze.clima_diario, com chave (ibge_id, data): regravar o mesmo dia substitui a linha.
"""
import time
from datetime import date, timedelta

import duckdb
import pandas as pd
import requests
from tqdm.auto import tqdm

URL_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"   # histórico (com atraso)
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"         # dias recentes e hoje

INICIO_PADRAO = date(2016, 1, 1)   # primeiro dia da carga histórica
DEFASAGEM_ARCHIVE = 5              # dias de atraso da API de histórico
TAMANHO_LOTE = 10                  # máximo de cidades por pedido (pedidos menores pesam menos no limite por minuto)
ORCAMENTO = 60_000                 # valores por pedido (cidades x dias x variáveis); a API recusa pedidos grandes (400)
PAUSA_MINUTO = 65                  # espera, em segundos, quando a API recusa por limite por minuto

# Variáveis diárias usadas na análise de temperatura.
VARS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "shortwave_radiation_sum", "sunshine_duration",
    "wind_speed_10m_max",
]
# Tipos no banco diferentes de DOUBLE (nenhum por ora; ex.: {"sunrise": "TIMESTAMP"}).
TIPOS: dict[str, str] = {}

COLUNAS_CIDADES = ["ibge_id", "lat", "lng", "fuso_horario"]


class LimiteAtingido(Exception):
    """A API recusou os pedidos por limite de uso (por hora ou por dia)."""


def criar_tabela(con):
    colunas = ", ".join(f"{v} {TIPOS.get(v, 'DOUBLE')}" for v in VARS)
    con.execute("create schema if not exists bronze")
    con.execute(f"""
        create table if not exists bronze.clima_diario (
            ibge_id INTEGER, data DATE, {colunas},
            fonte VARCHAR, carregado_em TIMESTAMP,
            primary key (ibge_id, data)
        )""")


def _motivo(resposta):
    """Texto de 'reason' que a API devolve nos erros (vazio se não houver corpo JSON)."""
    try:
        return str(resposta.json().get("reason", ""))
    except ValueError:
        return ""


def buscar(url, cidades, fuso, **extra):
    """Chama a API para um lote de cidades (mesmo fuso); devolve um DataFrame com uma linha por cidade e dia.

    `extra` leva as datas (archive: start_date/end_date) ou past_days/forecast_days (forecast).
    """
    params = {
        "latitude": ",".join(f"{x:.4f}" for x in cidades["lat"]),
        "longitude": ",".join(f"{x:.4f}" for x in cidades["lng"]),
        "daily": ",".join(VARS),
        "timezone": fuso,
        **extra,
    }
    for _ in range(3):
        r = requests.get(url, params=params, timeout=120)
        if r.status_code == 429:
            motivo = _motivo(r)
            if "minut" in motivo.lower():
                time.sleep(PAUSA_MINUTO)   # limite por minuto: esperar um minuto resolve
                continue
            # Limite por hora ou por dia: esperar alguns minutos não adianta.
            raise LimiteAtingido(motivo or "429 sem detalhe da API")
        if r.status_code == 400:
            raise RuntimeError(f"400 da API: {_motivo(r) or r.text[:500]}")
        r.raise_for_status()
        dados = r.json()
        break
    else:
        raise LimiteAtingido("Limite por minuto persistiu após várias tentativas.")

    dados = dados if isinstance(dados, list) else [dados]   # 1 local -> dict, vários -> lista
    partes = []
    for ibge_id, d in zip(cidades["ibge_id"], dados):       # a resposta vem na mesma ordem do pedido
        t = pd.DataFrame(d["daily"]).rename(columns={"time": "data"})
        t["ibge_id"] = ibge_id
        partes.append(t)
    out = pd.concat(partes, ignore_index=True)
    out["data"] = pd.to_datetime(out["data"]).dt.date
    for v, tipo in TIPOS.items():
        if tipo == "TIMESTAMP" and v in out.columns:
            out[v] = pd.to_datetime(out[v])
    # Dias ainda sem medição chegam vazios: descarta, para não gravar linhas sem clima.
    return out.dropna(subset=["temperature_2m_mean"])


def gravar(con, df, fonte):
    """Insere as linhas; se (ibge_id, data) já existir, substitui (é o que corrige as provisórias)."""
    if df.empty:
        return
    df = df.assign(fonte=fonte, carregado_em=pd.Timestamp.now())
    con.register("novos", df)
    con.execute("insert or replace into bronze.clima_diario by name select * from novos")
    con.unregister("novos")


def faixas_por_ano(inicio, fim):
    """Divide [inicio, fim] em faixas de no máximo 1 ano civil, em ordem cronológica."""
    faixas, ini = [], inicio
    while ini <= fim:
        f = min(date(ini.year, 12, 31), fim)
        faixas.append((ini, f))
        ini = f + timedelta(days=1)
    return faixas


def planejar_tarefas(cid, ultimo, inicio_padrao, corte):
    """Lista de pedidos: (fonte, fuso, inicio, fim, lote_de_cidades).

    Cada lote percorre os anos em ordem cronológica, então uma interrupção nunca deixa "buracos".
    """
    cid = cid.copy()
    cid["inicio"] = [ultimo[i] + timedelta(days=1) if i in ultimo else inicio_padrao for i in cid["ibge_id"]]

    tarefas = []
    falta = cid[cid["inicio"] <= corte]
    for (fuso, ini), g in falta.groupby(["fuso_horario", "inicio"]):
        faixas = faixas_por_ano(ini, corte)
        dias_max = max((f - i).days + 1 for i, f in faixas)
        # Cidades por pedido: o que couber no orçamento para a faixa mais longa.
        tam = max(1, min(TAMANHO_LOTE, ORCAMENTO // (dias_max * len(VARS))))
        for k in range(0, len(g), tam):
            lote = g.iloc[k:k + tam]
            for a, b in faixas:
                tarefas.append(("archive", fuso, a, b, lote))
    # Dias recentes e hoje (provisórios), pela API de previsão: poucos dias, cabe em lotes grandes.
    for fuso, g in cid.groupby("fuso_horario"):
        for k in range(0, len(g), TAMANHO_LOTE):
            tarefas.append(("forecast", fuso, None, None, g.iloc[k:k + TAMANHO_LOTE]))
    return tarefas


def atualizar_clima(cidades, db_path, inicio=INICIO_PADRAO, hoje=None, pausa=1.0):
    """Atualiza o clima das cidades (colunas: ibge_id, lat, lng, fuso_horario) no banco.

    Retorna True se a carga terminou e False se parou por limite de uso (o que foi gravado
    fica salvo; basta rodar de novo mais tarde). `hoje` e `pausa` existem para testes.
    """
    hoje = hoje or date.today()
    corte = hoje - timedelta(days=DEFASAGEM_ARCHIVE)   # último dia que o archive deve ter
    cid = cidades[COLUNAS_CIDADES].reset_index(drop=True).copy()

    with duckdb.connect(str(db_path)) as con:
        criar_tabela(con)
        # Último dia do archive já carregado por cidade; o próximo pedido começa no dia seguinte.
        ultimo = dict(con.execute(
            "select ibge_id, max(data) from bronze.clima_diario where fonte = 'archive' group by 1"
        ).fetchall())
        tarefas = planejar_tarefas(cid, ultimo, inicio, corte)

        try:
            for fonte, fuso, ini, fim, lote in tqdm(tarefas):
                if fonte == "archive":
                    df = buscar(URL_ARCHIVE, lote, fuso, start_date=ini.isoformat(), end_date=fim.isoformat())
                else:
                    df = buscar(URL_FORECAST, lote, fuso, past_days=(hoje - corte).days, forecast_days=1)
                    df = df[df["data"] > corte]   # o dia do corte pertence ao archive
                gravar(con, df, fonte)            # cada pedido é gravado na hora: dá para retomar depois
                time.sleep(pausa)
        except LimiteAtingido as e:
            print("Parou por limite de uso. O que foi gravado fica salvo; rode de novo mais tarde.\n", e)
            return False
    return True
