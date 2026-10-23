-- Teste singular: falha nas linhas com valores fisicamente implausíveis para o Brasil.
-- O teste passa quando esta consulta não devolve nenhuma linha.
select *
from {{ ref('clima_diario') }}
where temp_media_c not between -10 and 50
   or temp_min_c > temp_max_c
   or temp_media_c not between temp_min_c and temp_max_c
   or chuva_mm < 0
   or sol_horas not between 0 and 24
   or vento_max_kmh < 0
