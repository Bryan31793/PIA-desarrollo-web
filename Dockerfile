
FROM python:3.14-slim

WORKDIR /app

# Instalar Poetry
RUN pip install --no-cache-dir poetry==2.2.1

# No crear un venv adicional en el contenedor
ENV POETRY_VIRTUALENVS_CREATE=false

# Copiar archivos de dependencias
COPY pyproject.toml poetry.lock ./

# Instalar únicamente dependencias de producción
RUN poetry install --only main --no-root --no-interaction

# Copiar código fuente
COPY ./app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]

