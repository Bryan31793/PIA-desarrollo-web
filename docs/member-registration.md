# Registro de clientes

`POST /auth/register` es público y recibe JSON. Requiere el esquema SQL inicial
aplicado y `DATABASE_URL` configurado; Compose ya proporciona esa variable al
backend. En ejecución local, exportar las variables de `.env.example` con valores
reales antes de iniciar Uvicorn. Instalar las nuevas dependencias con
`poetry install`; si se usa Docker, reconstruir el backend.

```sh
curl -i http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ana Pérez","email":"ana@example.com","password":"una clave larga"}'
```

Respuesta `201 Created`:

```json
{
  "member_id": 1,
  "name": "Ana Pérez",
  "email": "ana@example.com",
  "is_active": true,
  "created_at": "2026-11-09T18:00:00Z"
}
```

- Nombre: entre 1 y 100 caracteres, quitando espacios de los extremos.
- Correo: formato válido, máximo 254 caracteres, guardado en minúsculas.
  La unicidad la garantiza PostgreSQL mediante `CITEXT`, incluso con registros
  concurrentes. Un correo ya registrado devuelve `409` con
  `{"detail":"Email is already registered"}`.
- Contraseña: entre 8 y 128 caracteres; se preservan sus espacios. Se almacena
  únicamente su hash Argon2id con salt aleatorio. No se devuelve ni la contraseña
  ni su hash en la respuesta de creación.
- Datos inválidos, campos faltantes o campos adicionales: `422`.
- Base de datos sin configurar o conexión no disponible: `503` con un mensaje
  genérico, sin datos de conexión.

El cliente nace activo usando los valores predeterminados de la tabla. No puede
elegir un rol, un identificador ni su estado mediante este endpoint. No se crean
membresías, pagos ni tokens durante el registro.

Después del registro, el cliente puede iniciar sesión en `POST /auth/login`.
Este endpoint recibe un formulario `application/x-www-form-urlencoded`, con el
correo en `username` y la contraseña en `password`:

```sh
curl -i http://localhost:8000/auth/login \
  --data-urlencode 'username=ana@example.com' \
  --data-urlencode 'password=una clave larga'
```

Consulta `members` por correo, sin distinguir mayúsculas gracias a `CITEXT`, y
verifica la contraseña contra el hash Argon2 almacenado. Requiere una cuenta
activa; no exige una membresía vigente ni un pago para iniciar sesión.
Devuelve `200` con `access_token`, `refresh_token`, `token_type` y `expires_in`.
El flujo de emisión de tokens requiere Redis, como antes. Un correo inexistente,
una contraseña incorrecta o una cuenta inactiva devuelven el mismo `401` con
`{"detail":"Invalid username or password"}`. Si PostgreSQL no está configurado
o su conexión falla, devuelve `503`. Las credenciales de demostración dejaron de
existir como mecanismo de acceso. No requiere cambios de esquema ni migraciones.

Pruebas del endpoint sin servicios externos:

```sh
poetry run python -m pytest tests/test_member_registration.py -q
```

Para verificar también la persistencia y la restricción de correo de PostgreSQL,
configurar `TEST_DATABASE_URL` con una base de pruebas donde se haya aplicado
`001_init.sql`, y ejecutar:

```sh
poetry run python -m pytest tests/test_member_registration_postgres.py -q
```

La prueba crea un esquema aislado y lo elimina al terminar. La cuenta de conexión
necesita permiso para crear esquemas; no se insertan clientes en `public.members`.
