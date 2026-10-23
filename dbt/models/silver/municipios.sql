-- Municípios do IBGE: tipados e com as colunas que as próximas camadas usam.

with origem as (
    select * from {{ source('bronze', 'ibge_municipios') }}
),

final as (
    select
        cast(ibge_id as integer)  as ibge_id,
        nome,
        nome_norm,                -- sem acento, minúsculo: para cruzar com outras bases
        uf_sigla,
        uf_nome,
        regiao_sigla,
        regiao_nome,
        mesorregiao,
        microrregiao,
        regiao_intermediaria,
        regiao_imediata,
        cast(lat as double)       as lat,
        cast(lng as double)       as lng,
        fuso_horario
    from origem
)

select * from final
