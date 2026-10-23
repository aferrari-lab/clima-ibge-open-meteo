# Clima no Brasil: pipeline de dados para previsão de temperatura

Pipeline em Python que coleta o clima diário dos municípios brasileiros desde 2016 (Open-Meteo), usando a base de municípios do IBGE, e guarda tudo em um banco DuckDB local. Por padrão carrega uma cidade por região imediata do IBGE (510 no país), o que cobre todas as regiões com uma fração das consultas; também é possível carregar todos os 5.571 municípios. É a base de dados para uma análise de previsão de temperatura.

> **Status:** em desenvolvimento.
>
> - **Pronto:** extração dos municípios (IBGE) e das coordenadas; carga incremental e retomável do clima (Open-Meteo); transformação em camadas com dbt (silver e gold), com testes de qualidade.
> - **Em andamento:** carga histórica desde 2016, começando por São Paulo e seguindo para as demais UFs, no ritmo da cota diária gratuita da API.
> - **Próximo:** análise exploratória com os dados completos e modelagem da previsão de temperatura.

## Fluxo

```
IBGE (API de localidades) ───────┐
Coordenadas dos municípios ──────┼─► bronze ──► silver ──► gold ──► EDA e modelo de previsão
Open-Meteo (histórico + previsão)┘   Python     dbt        dbt
```

Tudo fica em um único banco DuckDB local, com uma schema por camada.

## Tabelas

### Bronze: dados crus (carga em Python)

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

### Silver: limpeza, tipos e unidades (dbt)

- **`silver.municipios`**: municípios tipados, com as colunas usadas nas próximas camadas.
- **`silver.clima_diario`**: só dado fechado (`archive`), com nomes e unidades explícitos (`temp_media_c`, `chuva_mm`, `radiacao_mj_m2`, `sol_horas`, `vento_max_kmh`), amplitude térmica e colunas de calendário.

### Gold: análise e modelo (dbt)

- **`gold.dim_municipio`**: uma linha por município, com o nome no formato "Cidade (UF)" e a cobertura de dados de clima.
- **`gold.fct_clima_diario`**: uma linha por município e dia, com UF, região e variáveis do passado recente (temperatura de ontem, média e chuva dos 7 dias anteriores), calculadas só com dias anteriores para não vazar o futuro para o modelo.

## Decisões de projeto

- **Carga incremental e idempotente:** cada execução busca só o que falta (a partir do último dia gravado de cada município). Gravar de novo o mesmo dia substitui a linha, sem duplicar.
- **Dado fechado e provisório:** a API de histórico tem alguns dias de atraso. Os dias mais recentes vêm da API de previsão, marcados como `forecast`, e são substituídos pelo dado fechado quando ele fica disponível.
- **Pedidos divididos:** a API recusa pedidos grandes demais (erro 400). Por isso a carga divide o período por ano e as cidades em lotes, com um orçamento de valores por pedido.
- **Retomável:** cada pedido é gravado ao terminar. Se a carga parar (por limite de uso, por exemplo), basta rodar de novo.
- **Limite de uso da API:** o plano gratuito pesa cada pedido por cidades × dias. Por isso a carga usa, por padrão, uma cidade por região imediata (os vizinhos têm séries quase iguais); `--todas` carrega todos os municípios (para o Brasil inteiro, leva meses na cota gratuita).
- **Camadas e testes com dbt:** a bronze é só lida pelo dbt (declarada como *source*); a silver tem um modelo de limpeza por tabela de origem; junções e variáveis ficam na gold. Há testes de qualidade nas três camadas (chaves únicas, integridade entre tabelas, faixas plausíveis) e aviso de atraso da carga (`dbt source freshness`).
- **Fuso horário por município:** passado à API para evitar datas deslocadas.

## Limites da API

O plano gratuito do Open-Meteo permite 600 chamadas por minuto, 5.000 por hora e 10.000 por dia, e cada pedido pesa conforme o número de cidades e de dias (e de variáveis, acima de 10). Pela fórmula divulgada (`cidades × dias / 14`), o histórico do Brasil desde 2016 pesa algo como 145 mil com uma cidade por região imediata (cerca de 15 dias de cota) e algo como 1,6 milhão com todos os 5.571 municípios (cerca de 5 meses). São estimativas: confira os limites atuais na documentação.

Por isso a carga usa uma cidade por região imediata por padrão, divide os pedidos por ano e em lotes pequenos, e pode ser interrompida e retomada: ao atingir o limite diário, ela para (código de saída 2) e continua do ponto em que parou no dia seguinte.

## Estrutura

```
src/clima/       módulo da carga (open_meteo.py, cidades.py, db.py) e linha de comando (__main__.py)
dbt/             transformação em camadas (bronze -> silver -> gold), testes de dados e documentação
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
python -m clima                            # Brasil: uma cidade por região imediata, desde 2016
python -m clima --uf SP --todas            # todos os municípios de uma UF
python -m clima --limite 5                 # teste rápido com 5 cidades
python -m clima --uf MG                    # só uma UF
python -m clima --uf SP --inicio 2020-01-01
```

Sem `--uf`, o comando carrega o Brasil inteiro; com `--uf SP`, só uma UF. A carga é retomável. Se parar por limite de uso da API, o programa termina com código de saída 2: rode o mesmo comando mais tarde.

**3. Transformação (dbt)**, com os notebooks que usam o banco fechados:

```bash
cd dbt
dbt build --profiles-dir .              # cria silver e gold e roda os testes de dados
dbt source freshness --profiles-dir .   # avisa se a carga está atrasada
dbt docs generate --profiles-dir .      # documentação e linhagem (veja com: dbt docs serve --profiles-dir .)
```

**4. Análise exploratória (EDA):** `notebooks/03_eda.ipynb`. Lê a camada gold, então precisa dos passos 2 e 3.

**Testes do pacote:** `pip install pytest` e depois `pytest`, na raiz. Os testes de dados ficam no dbt e rodam no `dbt build`.

## Fontes e atribuição

- Dados meteorológicos: [Open-Meteo.com](https://open-meteo.com/), licença CC BY 4.0. O uso gratuito da API é para fins não comerciais; consulte os termos no site.
- Limites e custo dos pedidos: [Open-Meteo, preços e limites](https://open-meteo.com/en/pricing) e [post sobre múltiplas localidades](https://openmeteo.substack.com/p/weather-data-for-multiple-locations).
- Municípios: [API de localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades).
- Coordenadas dos municípios: repositório [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros).

Os dados do Open-Meteo vêm de modelos de reanálise com grade de resolução limitada: municípios vizinhos podem ter valores muito parecidos.

## Próximos passos

- Concluir a carga histórica (depende da cota diária da API).
- Rodar o EDA com a carga completa e registrar as conclusões.
- Modelo de referência com a média histórica de cada dia do ano.
- Modelo de previsão de temperatura, com validação separada por data.

## Licença

O código deste projeto está sob a licença MIT: veja o arquivo [LICENSE](LICENSE). Os dados usados vêm de terceiros e seguem as licenças e os termos de cada fonte (veja "Fontes e atribuição").
