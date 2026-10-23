{#
  Teste genérico reutilizável: falha se a combinação de colunas se repetir.
  Uso no .yml do modelo:  data_tests: [{chave_unica: {arguments: {colunas: [ibge_id, data]}}}]
#}
{% test chave_unica(model, colunas) %}
select {{ colunas | join(', ') }}, count(*) as linhas
from {{ model }}
group by {{ colunas | join(', ') }}
having count(*) > 1
{% endtest %}
