"""Testes da carga de clima. A API do Open-Meteo é simulada: não usa rede nem gasta cota."""
from datetime import date, timedelta

import pandas as pd
import pytest
import requests

from clima import open_meteo as om
from clima.cidades import representativas
from clima.db import consultar

HOJE = date(2026, 10, 23)
CORTE = HOJE - timedelta(days=om.DEFASAGEM_ARCHIVE)   # 2026-10-18


class Resp:
    """Resposta HTTP mínima."""

    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("sem corpo")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeAPI:
    """Simula o Open-Meteo: uma série por cidade pedida, com temperatura média constante."""

    def __init__(self, hoje, falhas=None):
        self.hoje = hoje
        self.chamadas = []          # (tipo, n_cidades, inicio, fim)
        self.falhas = falhas or {}  # número da chamada (1, 2, ...) -> Resp a devolver no lugar

    def __call__(self, url, params, timeout):
        n = len(params["latitude"].split(","))
        if "archive" in url:
            tipo = "archive"
            ini, fim = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        else:
            tipo = "forecast"
            ini = self.hoje - timedelta(days=params["past_days"])
            fim = self.hoje + timedelta(days=params["forecast_days"] - 1)
        self.chamadas.append((tipo, n, ini, fim))
        if len(self.chamadas) in self.falhas:
            return self.falhas[len(self.chamadas)]
        dias = [ini + timedelta(days=k) for k in range((fim - ini).days + 1)]
        daily = {"time": [d.isoformat() for d in dias]}
        for v in om.VARS:
            daily[v] = [20.0] * len(dias)
        serie = {"daily": daily}
        return Resp(200, serie if n == 1 else [serie] * n)


@pytest.fixture
def cidades():
    return pd.DataFrame({
        "ibge_id": [1, 2, 3],
        "lat": [-23.5, -22.9, -21.7],
        "lng": [-46.6, -47.0, -51.0],
        "fuso_horario": ["America/Sao_Paulo"] * 3,
    })


def instalar_api(monkeypatch, fake):
    monkeypatch.setattr(om.requests, "get", fake)
    monkeypatch.setattr(om, "PAUSA_MINUTO", 0)
    return fake


def um_valor(db, sql):
    return consultar(sql, db).iloc[0, 0]


def test_carga_completa_e_idempotente(tmp_path, cidades, monkeypatch):
    api = instalar_api(monkeypatch, FakeAPI(HOJE))
    db, inicio = tmp_path / "t.duckdb", date(2025, 1, 1)

    assert om.atualizar_clima(cidades, db, inicio=inicio, hoje=HOJE, pausa=0) is True
    dias = (CORTE - inicio).days + 1
    assert um_valor(db, "select count(*) from bronze.clima_diario where fonte = 'archive'") == 3 * dias
    assert um_valor(db, "select count(*) from bronze.clima_diario where fonte = 'forecast'") == 3 * om.DEFASAGEM_ARCHIVE

    # Segunda execução: o histórico está completo, só a previsão é consultada de novo.
    antes = len(api.chamadas)
    om.atualizar_clima(cidades, db, inicio=inicio, hoje=HOJE, pausa=0)
    assert [c[0] for c in api.chamadas[antes:]] == ["forecast"]
    assert um_valor(db, "select count(*) from bronze.clima_diario") == 3 * (dias + om.DEFASAGEM_ARCHIVE)


def test_previsao_e_substituida_pelo_dado_fechado(tmp_path, cidades, monkeypatch):
    api = instalar_api(monkeypatch, FakeAPI(HOJE))
    db, inicio = tmp_path / "t.duckdb", date(2026, 10, 1)
    om.atualizar_clima(cidades, db, inicio=inicio, hoje=HOJE, pausa=0)

    depois = HOJE + timedelta(days=5)   # passam 5 dias
    api.hoje = depois
    om.atualizar_clima(cidades, db, inicio=inicio, hoje=depois, pausa=0)

    # Os dias 19 a 23 viraram 'archive'; a previsão cobre só 24 a 28.
    assert um_valor(db, "select count(*) from bronze.clima_diario where fonte = 'forecast' and data <= date '2026-10-23'") == 0
    assert um_valor(db, "select min(fonte) from bronze.clima_diario where data = date '2026-10-20'") == "archive"
    assert um_valor(db, "select count(*) from bronze.clima_diario") == um_valor(
        db, "select count(distinct (ibge_id, data)) from bronze.clima_diario")


def test_retomada_apos_limite_sem_buracos(tmp_path, cidades, monkeypatch):
    limite = Resp(429, {"reason": "Hourly API request limit exceeded. Please try again in the next hour."})
    instalar_api(monkeypatch, FakeAPI(HOJE, falhas={4: limite}))
    db, inicio = tmp_path / "t.duckdb", date(2016, 1, 1)

    assert om.atualizar_clima(cidades, db, inicio=inicio, hoje=HOJE, pausa=0) is False   # parou na 4ª chamada
    assert um_valor(db, "select count(*) from bronze.clima_diario") > 0                  # as 3 primeiras faixas ficaram salvas

    assert om.atualizar_clima(cidades, db, inicio=inicio, hoje=HOJE, pausa=0) is True
    buracos = um_valor(db, """
        select max((max_d - min_d + 1) - n) from (
            select ibge_id, min(data) as min_d, max(data) as max_d, count(*) as n
            from bronze.clima_diario where fonte = 'archive' group by 1)""")
    assert buracos == 0
    assert um_valor(db, "select min(data) from bronze.clima_diario") == pd.Timestamp(inicio)


def test_limite_por_minuto_espera_e_repete(cidades, monkeypatch):
    minuto = Resp(429, {"reason": "Minutely API request limit exceeded. Please try again in one minute."})
    api = instalar_api(monkeypatch, FakeAPI(HOJE, falhas={1: minuto}))
    df = om.buscar(om.URL_ARCHIVE, cidades, "America/Sao_Paulo", start_date="2026-01-01", end_date="2026-01-03")
    assert len(api.chamadas) == 2 and len(df) == 3 * 3


def test_erro_400_mostra_o_motivo(cidades, monkeypatch):
    erro = Resp(400, {"error": True, "reason": "Your API call requests too much data."})
    instalar_api(monkeypatch, FakeAPI(HOJE, falhas={1: erro}))
    with pytest.raises(RuntimeError, match="too much data"):
        om.buscar(om.URL_ARCHIVE, cidades, "America/Sao_Paulo", start_date="2026-01-01", end_date="2026-01-03")


def test_planejamento_respeita_orcamento_e_ordem():
    cid = pd.DataFrame({"ibge_id": range(100), "lat": 0.0, "lng": 0.0, "fuso_horario": "America/Sao_Paulo"})
    tarefas = om.planejar_tarefas(cid, {}, date(2016, 1, 1), CORTE)
    archive = [t for t in tarefas if t[0] == "archive"]
    assert archive

    por_lote = {}
    for _, _, ini, fim, lote in archive:
        assert len(lote) * ((fim - ini).days + 1) * len(om.VARS) <= om.ORCAMENTO
        por_lote.setdefault(tuple(lote["ibge_id"]), []).append((ini, fim))
    for faixas in por_lote.values():   # cada lote percorre os anos em ordem, sem sobreposição
        assert faixas[0][0] == date(2016, 1, 1) and faixas[-1][1] == CORTE
        assert all(b[0] == a[1] + timedelta(days=1) for a, b in zip(faixas, faixas[1:]))


def test_representativas_uma_por_regiao():
    m = pd.DataFrame({
        "ibge_id": [1, 2, 3, 4, 5, 6],
        "nome": list("abcdef"),
        "regiao_imediata": ["X", "X", "X", "Y", "Y", "Y"],
        "lat": [0.0, 1.0, 2.0, 10.0, 10.2, 13.0],   # centros: X = 1.0 (id 2); Y ~ 11.07 (id 5)
        "lng": [0.0] * 6,
        "fuso_horario": ["America/Sao_Paulo"] * 6,
    })
    assert sorted(representativas(m)["ibge_id"]) == [2, 5]
