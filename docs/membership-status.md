# Estado actual de la membresía

`GET /api/memberships/me` permite a una cuenta con rol `MEMBER` consultar su plan
vigente. El miembro se obtiene del `sub` del access token; no se recibe un ID de
miembro ni una fecha de consulta. Las cuentas STAFF y ADMIN reciben `403`.

```sh
curl -i http://localhost:8000/api/memberships/me \
  -H 'Authorization: Bearer <access_token_member>'
```

Respuesta `200` cuando existe una membresía vigente:

```json
{
  "has_active_plan": true,
  "membership": {
    "membership_id": 1,
    "plan_id": 1,
    "plan_name": "Plan Básico",
    "start_date": "2026-01-01",
    "end_date": "2026-01-31"
  }
}
```

Respuesta `200` si el miembro no tiene ninguna membresía, todas terminaron o
ninguna ha comenzado:

```json
{
  "has_active_plan": false,
  "membership": null
}
```

La vigencia se evalúa como `start_date <= hoy <= end_date`. Ambos días se incluyen,
como en los intervalos de la restricción `no_overlap` de PostgreSQL. La fecha
actual usa America/Monterrey, igual que el alta de membresías. La exclusión de
solapamientos garantiza como máximo una membresía vigente por miembro.

`has_active_plan` informa exclusivamente de la vigencia temporal de la membresía;
no es el campo `members.is_active` ni un estado de pago. El alta actual exige pago,
pero esta consulta no agrega condiciones para las membresías históricas. No
incluye historial, próximas membresías ni datos de pagos o de otros miembros.

Un token ausente, inválido, expirado, revocado o de tipo refresh devuelve `401`.
Si la cuenta del token ya no existe, devuelve `404` (`Member not found`). Si
PostgreSQL no está disponible, devuelve `503`.

La validación de rol ocurre en la dependencia del endpoint. El servicio devuelve
schemas de `app/schemas/memberships.py`; el repositorio consulta con parámetros
SQL y usa LEFT JOIN para distinguir una cuenta inexistente de una cuenta sin plan
vigente. No requiere migraciones ni nuevas variables de entorno.
