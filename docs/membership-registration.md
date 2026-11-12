# Registro de membresías con cobro obligatorio

`POST /api/memberships` registra una membresía y su pago completo en efectivo,
en MXN, dentro de una sola transacción. Requiere un access token con `Role.STAFF`;
`ADMIN` y `MEMBER` reciben `403`. El endpoint declara la autorización mediante
`require_roles`, sin middleware.

```sh
curl -i http://localhost:8000/api/memberships \
  -H 'Authorization: Bearer <access_token_staff>' \
  -H 'Content-Type: application/json' \
  -d '{"member_id":42,"plan_id":1}'
```

El request solo admite `member_id` y `plan_id`, ambos obligatorios y enteros JSON
representables como BIGINT. Enviar `amount`, `price`, `employee_id`, `start_date`,
`end_date`, `duration_days` o cualquier campo adicional devuelve `422`.

Respuesta `201` para un alta el 1 de enero de 2026 y un plan de 350 MXN / 30 días:

```json
{
  "membership_id": 1,
  "member_id": 42,
  "plan_id": 1,
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "payment": {
    "payment_id": 1,
    "membership_id": 1,
    "employee_id": 8,
    "amount": "350.00",
    "currency": "MXN",
    "paid_at": "2026-01-01T18:00:00Z",
    "notes": null
  }
}
```

`amount` se representa como cadena decimal para conservar la precisión monetaria.
El cliente no proporciona ni el importe ni el empleado que recibió el efectivo.
Registrar la operación deja constancia del cobro en efectivo; no integra una
pasarela de pagos ni procesa cargos bancarios.

## Reglas del servicio

- `get_membership_start_date()` obtiene la fecha actual con
  `datetime.now(ZoneInfo("America/Monterrey")).date()`.
- `end_date = start_date + plans.duration_days`.
- Se cobra exactamente `plans.price`, obtenido en el backend. No hay descuentos,
  importes personalizados ni una política de precios nueva en la base de datos.
- El precio debe ser finito y mayor que cero. Un plan con precio cero devuelve
  `422` sin crear membresía ni pago. Los planes se administran mediante los endpoints exclusivos de ADMIN.
- `employee_id` se obtiene del `sub` del token STAFF. El empleado debe existir para
  satisfacer la clave foránea; si ya no existe, devuelve `401` y revierte el alta.
- `currency`, `paid_at` y `notes` conservan los valores predeterminados de la base:
  MXN, hora de la transacción y NULL.

La operación lee el plan con `FOR SHARE` y conserva ese bloqueo hasta confirmar
ambos INSERTs. Así se mantienen el precio y la duración leídos durante el alta.
El pago guarda el importe histórico; cambiar después `plans.price` no lo modifica.

El servicio controla una conexión compartida por los repositorios de planes,
membresías y pagos. Un fallo al insertar el pago, validar la respuesta o confirmar
la transacción revierte todo: nunca se confirma solo la membresía por este endpoint.
La respuesta se devuelve después de confirmar ambos registros.

## Restricciones existentes de PostgreSQL

- Deben existir el miembro, el plan, la membresía del pago y el empleado.
- `end_date` debe ser posterior a `start_date`.
- Las membresías del mismo miembro no pueden solaparse; se incluyen ambos extremos
  (`[]`). Una que termina el 31 de enero impide iniciar otra ese mismo día.
- Distintos miembros pueden tener membresías en el mismo periodo.
- Solo se permite un pago completo por membresía, en efectivo y MXN, con importe
  entre 0.01 y 99999999.99.

La inserción de membresías bloquea la fila del miembro con `FOR NO KEY UPDATE`
para serializar altas del mismo cliente y evitar interbloqueos entre ellas.
`no_overlap` sigue siendo la validación final de los periodos ante concurrencia.

La igualdad entre importe y tarifa se garantiza en el servicio usando directamente
el precio del plan. No se agregan restricciones SQL ni nuevas migraciones.
La base sigue admitiendo membresías sin pago e importes distintos por acceso
SQL directo; el flujo HTTP nuevo siempre registra ambos juntos. Las membresías
anteriores no se modifican ni se consideran pagadas automáticamente.

| Estado | Situación |
| --- | --- |
| `201` | Membresía y pago creados y confirmados |
| `401` | Token inválido, ausente, expirado, revocado, refresh o empleado inexistente |
| `403` | Cuenta autenticada sin rol STAFF |
| `404` | `Member not found` o `Plan not found` |
| `409` | `Membership dates overlap an existing membership` |
| `422` | Datos inválidos, precio no positivo/no finito o cálculo de fechas fuera de rango |
| `503` | PostgreSQL no disponible o fallo operativo de persistencia |

## Alcance

La base permite clientes inactivos; el endpoint conserva ese comportamiento.
Las fechas se calculan automáticamente y las membresías existentes se respetan.
No se implementan abonos, devoluciones, pagos con tarjeta, edición de cobros ni un
endpoint de pago separado. Este endpoint no crea planes ni incorpora descuentos; la administración de planes
está en `docs/admin.md`.

## Implementación y verificación

El router contiene únicamente el endpoint. `membership_service.py` coordina las
reglas y la transacción y devuelve `MembershipResponse` con `PaymentResponse`
anidado, ambos en `schemas/`. La persistencia usa consultas parametrizadas.
Requiere las migraciones existentes 001 y 002, PostgreSQL y Redis para validar
tokens; no requiere nuevas dependencias ni variables de entorno.

```sh
poetry run python -m pytest -q
poetry run ruff check .
```

Las pruebas cubren autorizaciones, fechas, precio exacto con centavos, rechazo de
campos manipulados, planes con precio inválido, rollback ante fallo del pago,
empleado inexistente, historial de importes, claves foráneas y solapamientos
concurrentes. Las de PostgreSQL usan `TEST_DATABASE_URL` y esquemas aislados.
