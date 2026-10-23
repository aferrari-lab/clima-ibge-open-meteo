-- Fato de clima: uma linha por município e dia, com atributos de localização e
-- variáveis do passado recente para o modelo de previsão.
-- Só usa dias ANTERIORES ao da linha, para não vazar o futuro para o modelo.

with clima as (
    select * from {{ ref('clima_diario') }}
),

municipios as (
    select ibge_id, uf_sigla, regiao_imediata from {{ ref('municipios') }}
),

com_passado as (
    select
        *,
        -- Temperatura de ontem: só vale se a linha anterior for mesmo o dia anterior.
        case
            when lag(data) over por_cidade = data - 1
            then lag(temp_media_c) over por_cidade
        end                                          as temp_media_ontem_c,
        -- Janelas dos 7 dias anteriores (pelo calendário, não pelo número de linhas).
        avg(temp_media_c) over ultimos_7_dias        as temp_media_7d_c,
        sum(chuva_mm) over ultimos_7_dias            as chuva_7d_mm,
        count(*) over ultimos_7_dias                 as dias_validos_7d
    from clima
    window
        por_cidade as (partition by ibge_id order by data),
        ultimos_7_dias as (
            partition by ibge_id order by data
            range between interval 7 days preceding and interval 1 day preceding
        )
),

final as (
    select
        c.ibge_id,
        c.data,
        m.uf_sigla,
        m.regiao_imediata,
        c.temp_media_c,
        c.temp_max_c,
        c.temp_min_c,
        c.amplitude_c,
        c.chuva_mm,
        c.radiacao_mj_m2,
        c.sol_horas,
        c.vento_max_kmh,
        c.ano,
        c.mes,
        c.dia_do_ano,
        c.dia_semana,
        c.temp_media_ontem_c,
        c.temp_media_7d_c,
        c.chuva_7d_mm,
        c.dias_validos_7d                            -- menos de 7 = janela incompleta (início da série ou falha)
    from com_passado c
    join municipios m on m.ibge_id = c.ibge_id
)

select * from final
