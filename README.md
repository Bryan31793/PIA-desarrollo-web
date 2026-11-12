# GymFlow · aplicación client-server

Cliente React + TypeScript conectado al backend FastAPI, con PostgreSQL y Redis.
Incluye interfaces para miembros, recepción y administración.

## Ejecutar con Docker

Configura `.env` a partir de `.env.example` si aún no existe. Define `DB_PASSWORD`
y un `JWT_SECRET` de al menos 32 bytes. Mantén los valores de una instalación
existente.

```sh
docker compose up --build
```

- Cliente: http://localhost:5173
- API y documentación: http://localhost:8000/docs

En una base nueva, aplicar las migraciones numeradas según
[migrations/README.md](migrations/README.md). Compose no las aplica automáticamente;
no repetir las migraciones ya aplicadas en una base existente.

El cliente usa Nginx para enviar `/auth` y `/api` al backend dentro de Compose.
El navegador se comunica con un mismo origen, sin configurar CORS ni exponer
credenciales de PostgreSQL o Redis.

## Desarrollo local del cliente

Requiere Node.js 24 y el backend ejecutándose en el puerto 8000:

```sh
npm --prefix client ci
npm --prefix client run dev
```

Abre http://localhost:5173. Si el backend está en otra dirección, configura
`BACKEND_URL` en `client/.env` siguiendo `client/.env.example`; reinicia Vite.
Esta variable configura el proxy del servidor de desarrollo, no una URL pública
incluida en el navegador.

Para ejecutar el backend localmente, instala las dependencias con `poetry install`,
exporta `DATABASE_URL`, `REDIS_URL` y `JWT_SECRET`, y ejecuta:

```sh
poetry run uvicorn app.main:app --reload
```

Ver [client/README.md](client/README.md) para flujos, sesiones, cámara y pruebas.

## Funcionalidades

| Cuenta | Funciones |
| --- | --- |
| Miembro | Registro, login, estado y fechas de la membresía, pase QR de 120 segundos |
| Staff | Login, registro de miembros, membresía con cobro en efectivo, escaneo QR |
| Admin | Login, creación y PATCH de planes, registro de empleados ADMIN/STAFF |

El backend conserva la autorización y las reglas: una entrada por miembro al día
en Monterrey, invalidación del QR anterior al regenerar, membresía activa y pago
obligatorio al registrar una nueva membresía. No se crean cuentas administradoras
ni contraseñas predeterminadas en la aplicación real.

## Verificación

```sh
poetry run python -m pytest -q
poetry run ruff check .
npm --prefix client test
npm --prefix client run build
npm --prefix client run format:check
```

Las pruebas de navegador con backend real se describen en `client/README.md` y
usan exclusivamente un esquema temporal de la base de pruebas.
