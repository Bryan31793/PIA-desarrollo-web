# Pool de conexiones PostgreSQL

El backend reutiliza conexiones mediante `psycopg_pool.ConnectionPool`. Existe un
pool síncrono por proceso de FastAPI; no se abre una conexión física nueva por
cada operación del repositorio.

## Ciclo de vida y transacciones

El lifespan de FastAPI abre explícitamente el pool sin esperar conectividad y lo
cierra al apagar la aplicación. No se crea ningún pool al importar módulos. El
cierre libera conexiones e hilos y se ejecuta fuera del bucle asíncrono.

La interfaz existente se conserva:

```python
with get_connection() as connection:
    connection.execute(...)
```

Al terminar el bloque se confirma la transacción; ante una excepción se revierte.
Después se devuelve la conexión al pool. Las operaciones que comparten conexión
explícitamente siguen utilizando una sola transacción: membresía y pago, o
consumo de pase y entrada. No se reintentan consultas ni transacciones de negocio.

Las conexiones conservan `dict_row`, autocommit desactivado y el timeout de
conexión física de 5 segundos. El pool comprueba las conexiones al prestarlas y
reemplaza las rotas. Puede cerrar o renovar conexiones por su ciclo de vida; lo
que se evita es abrir y cerrar una conexión por cada petición.

Si PostgreSQL está caído, FastAPI arranca y los workers del pool reintentan
conectarse en segundo plano. Las operaciones que no consiguen conexión devuelven
`503` con `{"detail":"Storage is temporarily unavailable"}`. La recuperación no
requiere reiniciar la API si el servidor vuelve a estar disponible.

Si falta `DATABASE_URL`, la API también arranca, pero no crea el pool y las
operaciones de base de datos devuelven `503`. Corregir o cambiar la configuración
requiere reiniciar la aplicación. Una configuración numérica inválida del pool
impide el arranque con un error de configuración, sin incluir el DSN.

## Configuración

Mantener `DATABASE_URL` y, opcionalmente, exportar estas variables en ejecución
local o definirlas en `.env` para Compose:

| Variable | Predeterminado | Validación |
| --- | --- | --- |
| `DB_POOL_MIN_SIZE` | `1` | Entero, al menos 1 |
| `DB_POOL_MAX_SIZE` | `10` | Entero, al menos el mínimo |
| `DB_POOL_TIMEOUT_SECONDS` | `5` | Número finito y positivo |

El timeout del pool controla la espera para obtener una conexión, no establece un
timeout para las consultas SQL. Si todas están ocupadas, las solicitudes esperan
hasta ese timeout y luego reciben `503`.

El máximo se aplica por proceso. Por ejemplo, cuatro workers con máximo 10 pueden
mantener hasta 40 conexiones del backend, además de conexiones administrativas y
de otras aplicaciones. Ajustar el límite según el presupuesto de PostgreSQL.

## Instalación y despliegue

Se añadió el extra `pool` a `psycopg[binary,pool]` y se actualizó `poetry.lock`.
Para una instalación existente:

```sh
poetry install
```

Reiniciar Uvicorn después de instalar la dependencia o cambiar variables del pool.
En Docker, reconstruir el backend:

```sh
docker compose up --build
```

Compose transmite las tres variables con sus valores predeterminados. No se
requieren migraciones ni cambios en endpoints, payloads o reglas de negocio.

Los scripts que invoquen servicios directamente, fuera de FastAPI, deben llamar
`open_pool()` antes de usarlos y `close_pool()` en un bloque `finally` al terminar.
No hay inicialización automática en `get_connection()`.

## Pruebas

Las pruebas unitarias aíslan el pool y simulan sus operaciones. Las pruebas de
integración crean un pool independiente para el esquema de cada prueba y lo
cierran antes de eliminar dicho esquema. Las conexiones directas de Psycopg en
los fixtures se mantienen para preparación, verificación y limpieza.

Se comprueban reutilización de `pg_backend_pid()`, commit, rollback, recuperación
tras errores SQL, agotamiento del pool, reemplazo de conexiones rotas y detección
de conexiones obsoletas al prestarlas. También se comprueban configuración,
arranque/cierre y respuestas `503`, y se ejecuta la suite de negocio completa.

```sh
poetry run python -m pytest -q
poetry run ruff check .
```

Referencia: [documentación de pools de Psycopg](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).
