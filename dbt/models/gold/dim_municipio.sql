-- Dimensão de municípios: atributos do IBGE + cobertura de dados de clima de cada um.

with municipios as (
    select * from {{ ref('municipios') }}
),

cobertura as (
    select
        ibge_id,
        min(data)  as clima_desde,
        max(data)  as clima_ate,
        count(*)   as dias_com_clima
    from {{ ref('clima_diario') }}
    group by ibge_id
),

final as (
    select
        m.ibge_id,
        m.nome,
        m.nome || ' (' || m.uf_sigla || ')'   as nome_uf,     -- único: há cidades homônimas em UFs diferentes
        m.uf_sigla,
        m.uf_nome,
        m.regiao_sigla,
        m.regiao_nome,
        m.regiao_intermediaria,
        m.regiao_imediata,
        m.lat,
        m.lng,
        m.fuso_horario,
        c.ibge_id is not null                  as tem_clima,
        c.clima_desde,
        c.clima_ate,
        coalesce(c.dias_com_clima, 0)          as dias_com_clima
    from municipios m
    left join cobertura c on c.ibge_id = m.ibge_id
)

select * from final
