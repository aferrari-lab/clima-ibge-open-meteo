# Imagem do Airflow para este projeto: a imagem oficial + um ambiente Python separado
# para o pacote "clima" e o dbt. A versão deve ser a mesma do docker-compose.yaml.
FROM apache/airflow:3.3.2

# Por que um ambiente (venv) separado?
# O Airflow e o dbt fixam versões diferentes de várias bibliotecas. Instalados juntos, um
# pode quebrar o outro. Os DAGs chamam o Python deste venv pelo caminho completo.
# As versões são as mesmas do requirements.txt do projeto (DuckDB 2.0 lê o banco atual).
ENV PROJETO_VENV=/opt/airflow/venv-projeto

RUN python -m venv "${PROJETO_VENV}" \
 && "${PROJETO_VENV}/bin/pip" install --no-cache-dir \
        "duckdb==2.0.0" \
        "pandas==3.1.0" \
        "requests==2.34.2" \
        "tqdm==4.70.1" \
        "dbt-duckdb==1.11.0"

# O código do projeto NÃO é copiado para a imagem: ele é montado em /opt/projeto pelo
# docker-compose. Este arquivo .pth faz o Python do venv enxergar o pacote em
# /opt/projeto/src, então mudanças no código valem sem reconstruir a imagem.
RUN echo "/opt/projeto/src" > "$("${PROJETO_VENV}/bin/python" -c 'import site; print(site.getsitepackages()[0])')/projeto_clima.pth"
