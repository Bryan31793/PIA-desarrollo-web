# Administración de planes y empleados

Los tres endpoints requieren un access token con `Role.ADMIN`. STAFF y MEMBER
reciben `403`; tokens ausentes, inválidos, expirados, revocados o de tipo refresh,
`401`. Las validaciones de rol se ejecutan por dependencias de los endpoints.

## Crear planes

`POST /api/plans`, respuesta `201`:

```sh
curl -i http://localhost:8000/api/plans \
  -H 'Authorization: Bearer <access_token_admin>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Plan Semestral","price":"1700.00","duration_days":180}'
```

```json
{
  "plan_id": 4,
  "name": "Plan Semestral",
  "price": "1700.00",
  "duration_days": 180
}
```

Los tres campos son obligatorios. El nombre se recorta en los extremos, debe tener
entre 1 y 50 caracteres y ser único según la restricción existente de PostgreSQL
(sensible a mayúsculas). `duration_days` debe ser un entero JSON positivo dentro
del rango INT de PostgreSQL. Los campos adicionales se rechazan con `422`.

El precio se valida en el backend: decimal finito, mayor que cero, como máximo
99999999.99 y hasta dos decimales significativos después del punto. No se redondean
silenciosamente importes como 350.001. Se aceptan números JSON o cadenas decimales;
las respuestas lo representan como cadena para conservar precisión. No se admiten
planes gratuitos ni precios negativos, NaN o infinitos.

## Actualizar planes

`PATCH /api/plans/{plan_id}`, respuesta `200` con el plan actualizado completo:

```sh
curl -i -X PATCH http://localhost:8000/api/plans/4 \
  -H 'Authorization: Bearer <access_token_admin>' \
  -H 'Content-Type: application/json' \
  -d '{"price":"1800.00"}'
```

Admite cualquier combinación de `name`, `price` y `duration_days`. Solo modifica
los campos enviados. `{}`, valores `null` y campos desconocidos devuelven `422`.
Un plan inexistente devuelve `404`; un nombre duplicado en alta o edición, `409`.

No recalcula fechas de membresías anteriores ni importes de pagos registrados.
Los nuevos registros de membresía utilizan los valores del plan al realizar el
alta; su bloqueo `FOR SHARE` evita que el precio o la duración cambien durante la
transacción de membresía y pago. Actualizaciones PATCH concurrentes que cambian
campos distintos no sobrescriben los campos omitidos por cada petición.

## Registrar empleados

`POST /api/employees`, respuesta `201`:

```sh
curl -i http://localhost:8000/api/employees \
  -H 'Authorization: Bearer <access_token_admin>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ana Pérez","email":"ana@example.com","password":"una contraseña segura","role":"staff"}'
```

```json
{
  "employee_id": 8,
  "name": "Ana Pérez",
  "email": "ana@example.com",
  "role": "staff",
  "is_active": true,
  "created_at": "2026-01-15T18:00:00Z"
}
```

- `name`: 1–100 caracteres después de recortar espacios en los extremos.
- `email`: formato válido, máximo 254 caracteres; se guarda en minúsculas. La
  unicidad en empleados es insensible a mayúsculas por CITEXT. Puede coincidir con
  el correo de una cuenta de miembro, ya que son tablas y logins separados.
- `password`: 8–128 caracteres, sin modificar sus espacios. Solo se almacena el
  hash Argon2id; contraseña y hash no se incluyen en la respuesta.
- `role`: obligatorio, `admin` o `staff`, usando el enum `Role`. `member` no es un
  rol de empleado. El backend resuelve el `role_id` desde el catálogo existente;
  no se acepta un ID de rol arbitrario.

La cuenta se crea activa según el valor predeterminado existente de la tabla.
No se acepta `is_active`, `employee_id`, `role_id` ni otros campos adicionales.
El rol queda fijo: no se agrega edición de empleados ni de sus roles.

El empleado puede iniciar sesión en `/auth/employees/login` con su correo en
`username` y su contraseña. El registro no emite tokens automáticamente.
Un correo duplicado devuelve `409`. Si el rol válido no existe en el catálogo,
devuelve `409` (`Employee role is not configured`). PostgreSQL no disponible
produce `503`. El sistema requiere un ADMIN existente para utilizar estos
endpoints; no crea una cuenta administradora inicial ni credenciales predeterminadas.

## Migración y verificación

`006_plan_price_validation_backend.sql` retira el CHECK `plans_price_check`
introducido por 001. La validación de precio se realiza en los schemas del backend,
sin agregar restricciones de negocio SQL de precio. Se conserva NUMERIC(10,2),
NOT NULL y las restricciones existentes de nombre y duración. SQL directo puede
eludir esa política; el registro de membresías también conserva su validación
previa de precio positivo y finito antes de cobrar.

```sh
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/006_plan_price_validation_backend.sql
poetry run python -m pytest -q
poetry run ruff check .
```

La migración 006 ya se aplicó en las bases locales `mi_proyecto` y `mi_proyecto_test`.
No se añadieron dependencias ni variables de entorno.
Las pruebas verifican roles, tokens, precios antes de persistir, PATCH parcial,
conflictos, concurrencia, historial de membresías/pagos y registro de empleados con
hash Argon2 seguido de inicio de sesión real contra PostgreSQL.
