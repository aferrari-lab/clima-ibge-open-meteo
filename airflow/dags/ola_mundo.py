"""DAG de estudo (etapa 1): confere se o Airflow está de pé e se enxerga o projeto.

Não grava nada no banco: só imprime uma mensagem, lista as pastas do projeto montado
e mostra as versões do DuckDB, do pacote clima e do dbt no ambiente do projeto.
"""
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

# Python e dbt do ambiente separado do projeto (criado no Dockerfile).
PROJETO_PY = "/opt/airflow/venv-projeto/bin/python"
DBT = "/opt/airflow/venv-projeto/bin/dbt"


@dag(
    dag_id="ola_mundo",
    schedule=None,                    # sem agendamento: só roda quando você aciona na interface
    start_date=datetime(2026, 1, 1),
    catchup=False,                    # não tenta "recuperar" execuções de datas passadas
    tags=["estudo"],
    doc_md=__doc__,                   # este texto aparece na página do DAG
)
def ola_mundo():
    # TaskFlow API: uma função Python com @task vira uma tarefa.
    @task
    def dizer_ola():
        print("Olá, Airflow! Esta tarefa rodou dentro do container.")
        return "ola"                  # o retorno vira um XCom, que outras tarefas podem ler

    # Operador clássico: roda um comando de terminal dentro do container.
    conferir_projeto = BashOperator(
        task_id="conferir_projeto",
        # A raiz do projeto está montada em /opt/projeto (veja o docker-compose.yaml).
        bash_command="ls /opt/projeto && ls -la /opt/projeto/dados",
    )

    conferir_ambiente = BashOperator(
        task_id="conferir_ambiente",
        bash_command=(
            f"{PROJETO_PY} -c 'import duckdb, clima; "
            f"print(\"duckdb\", duckdb.__version__, \"| pacote clima em\", clima.__file__)'"
            f" && {DBT} --version"
        ),
    )

    # Dependências: ">>" define a ordem (dizer_ola, depois conferir_projeto, depois conferir_ambiente).
    dizer_ola() >> conferir_projeto >> conferir_ambiente


ola_mundo()
