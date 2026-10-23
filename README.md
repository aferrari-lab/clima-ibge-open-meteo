# Clima em São Paulo: pipeline de dados para previsão de temperatura

Pipeline em Python que coleta o histórico e o clima recente de cidades de São Paulo (Open-Meteo), usando a base de municípios do IBGE, e guarda tudo em um banco DuckDB local. Por padrão carrega uma cidade por região imediata do IBGE; é possível carregar todos os 645 municípios. É a base de dados para uma análise de previsão de temperatura.

> **Status:** em desenvolvimento.
>
> - **Pronto:** extração dos municípios (IBGE) e das coordenadas; carga incremental e retomável do clima (Open-Meteo), com testes automatizados.
> - **Em andamento:** carga histórica inicial (desde 2016), limitada pela cota diária gratuita da API.
> - **Próximo:** validação de qualidade dos dados e modelagem da previsão de temperatura.

## Fluxo

```
IBGE (API de localidades) ───────┐
Coordenadas dos municípios ──────┼─► DuckDB (schema bronze) ─► análise e modelo de previsão
Open-Meteo (histórico + previsão)┘
```

## Tabelas

**`bronze.ibge_municipios`**: os 5.571 municípios do IBGE, com UF, região, microrregião, latitude, longitude e fuso horário. Inclui `nome_norm` (nome sem acento, em minúsculas) para cruzar com outras bases.

**`bronze.clima_diario`**: um registro por município e dia (chave `ibge_id` + `data`).

| Variável | Descrição |
|---|---|
| `temperature_2m_mean` / `_max` / `_min` | temperatura do ar a 2 m (°C) |
| `precipitation_sum` | chuva total do dia |
| `shortwave_radiation_sum` | radiação solar acumulada |
| `sunshine_duration` | duração do sol no dia |
| `wind_speed_10m_max` | vento máximo a 10 m |

Além delas: `fonte` (`archive` = dado fechado, `forecast` = provisório) e `carregado_em`.

## Decisões de projeto

- **Carga incremental e idempotente:** cada execução busca só o que falta (a partir do último dia gravado de cada município). Gravar de novo o mesmo dia substitui a linha, sem duplicar.
- **Dado fechado e provisório:** a API de histórico tem alguns dias de atraso. Os dias mais recentes vêm da API de previsão, marcados como `forecast`, e são substituídos pelo dado fechado quando ele fica disponível.
- **Pedidos divididos:** a API recusa pedidos grandes demais (erro 400). Por isso a carga divide o período por ano e as cidades em lotes, com um orçamento de valores por pedido.
- **Retomável:** cada pedido é gravado ao terminar. Se a carga parar (por limite de uso, por exemplo), basta rodar de novo.
- **Limite de uso da API:** o plano gratuito pesa cada pedido por cidades × dias. Por isso a carga usa, por padrão, uma cidade por região imediata (os vizinhos têm séries quase iguais); `--todas` carrega o estado inteiro ao longo de vários dias.
- **Fuso horário por município:** passado à API para evitar datas deslocadas.

## Limites da API

O plano gratuito do Open-Meteo permite 600 chamadas por minuto, 5.000 por hora e 10.000 por dia, e cada pedido pesa conforme o número de cidades e de dias (e de variáveis, acima de 10). Pela fórmula divulgada (`cidades × dias / 14`), o histórico completo desde 2016 pesa algo como 180 mil para os 645 municípios (cerca de 18 dias de cota) e algo como 17 mil para 60 cidades (cerca de 2 dias). São estimativas: confira os limites atuais na documentação.

Por isso a carga usa uma cidade por região imediata por padrão, divide os pedidos por ano e em lotes pequenos, e pode ser interrompida e retomada: ao atingir o limite diário, ela para (código de saída 2) e continua do ponto em que parou no dia seguinte.

## Estrutura

```
src/clima/       módulo da carga (open_meteo.py, cidades.py, db.py) e linha de comando (__main__.py)
notebooks/       municípios do IBGE (01), carga do clima (02) e análise exploratória (03)
tests/           testes com a API simulada (não gastam o limite de uso)
dados/           dados e banco local (não versionados)
```

## Como rodar

Desenvolvido com Python 3.14.3.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (no Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt   # instala as dependências e o pacote `clima` (src/)
```

**1. Municípios e coordenadas:** execute `notebooks/01_ibge_localidades.ipynb` (cria `bronze.ibge_municipios`).

**2. Clima**, pelo terminal (ou pelo `notebooks/02_open_meteo.ipynb`):

```bash
python -m clima                            # SP: uma cidade por região imediata, desde 2016
python -m clima --todas                    # todos os municípios da UF
python -m clima --limite 5                 # teste rápido com 5 cidades
python -m clima --uf SP --inicio 2020-01-01
```

A carga é retomável. Se parar por limite de uso da API, o programa termina com código de saída 2: rode o mesmo comando mais tarde.

**3. Análise exploratória (EDA):** `notebooks/03_eda.ipynb`. Só lê o banco, então precisa da carga do passo 2.

**Testes:** `pip install pytest` e depois `pytest`.

## Fontes e atribuição

- Dados meteorológicos: [Open-Meteo.com](https://open-meteo.com/), licença CC BY 4.0. O uso gratuito da API é para fins não comerciais; consulte os termos no site.
- Limites e custo dos pedidos: [Open-Meteo, preços e limites](https://open-meteo.com/en/pricing) e [post sobre múltiplas localidades](https://openmeteo.substack.com/p/weather-data-for-multiple-locations).
- Municípios: [API de localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades).
- Coordenadas dos municípios: repositório [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros).

Os dados do Open-Meteo vêm de modelos de reanálise com grade de resolução limitada: municípios vizinhos podem ter valores muito parecidos.

## Próximos passos

- Concluir a carga histórica (depende da cota diária da API).
- Validações de qualidade dos dados (dias faltando por município).
- Modelo de referência com a média histórica de cada dia do ano.
- Modelo de previsão de temperatura, com validação separada por data.
