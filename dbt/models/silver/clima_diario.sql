-- Clima diário fechado (archive): nomes claros, unidades explícitas e colunas de calendário.
-- Unidades padrão da API do Open-Meteo: °C, mm, MJ/m², segundos (sol) e km/h.

with origem as (
    select * from {{ source('bronze', 'clima_diario') }}
    where fonte = 'archive'                   -- 'forecast' é provisório e fica de fora
),

renomeado as (
    select
        ibge_id,
        data,
        temperature_2m_mean          as temp_media_c,
        temperature_2m_max           as temp_max_c,
        temperature_2m_min           as temp_min_c,
        precipitation_sum            as chuva_mm,
        shortwave_radiation_sum      as radiacao_mj_m2,
        sunshine_duration / 3600.0   as sol_horas,        -- a API envia em segundos
        wind_speed_10m_max           as vento_max_kmh,
        carregado_em
    from origem
),

final as (
    select
        *,
        temp_max_c - temp_min_c      as amplitude_c,
        year(data)                   as ano,
        month(data)                  as mes,
        dayofyear(data)              as dia_do_ano,
        isodow(data)                 as dia_semana        -- 1 = segunda ... 7 = domingo
    from renomeado
)

select * from final
