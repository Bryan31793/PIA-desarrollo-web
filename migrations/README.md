# Migraciones de PostgreSQL

Aplicar los archivos numerados en orden, una sola vez por base de datos.
`compose.yaml` no ejecuta estas migraciones automáticamente. Con PostgreSQL
disponible mediante Compose, desde la raíz del repositorio:

```sh
# Solo en una base nueva, sin las tablas del modelo:
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/001_init.sql

# Tanto en una base nueva como en una existente que ya tenga 001:
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/002_cash_payments.sql

# Aplicar solo si aún no están presentes:
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/003_immutable_employee_roles.sql
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/004_membership_plans.sql
```

`002` es transaccional: si falla, no deja una tabla parcialmente creada.
No modifica ni genera pagos para las membresías existentes. No se puede inferir
que esas membresías ya hayan sido pagadas.

## Pagos en efectivo

Relaciones: `members → memberships → payments ← employees`.
El plan se consulta mediante `memberships.plan_id`.

- Cada membresía admite como máximo un pago completo. Puede existir sin pago;
  la ausencia de un registro indica que no hay cobro registrado. No se admiten
  abonos, devoluciones ni otros conceptos de cobro en este modelo.
- `payment_id` identifica el registro; `membership_id` identifica la membresía
  pagada y, mediante ella, al cliente. No se duplica `member_id`, evitando que el
  pago señale a un cliente distinto del dueño de la membresía.
- `employee_id` identifica a quien recibió el efectivo. Ambas claves foráneas
  son obligatorias e impiden borrar una membresía o empleado con pagos asociados.
  Los empleados pueden desactivarse con el campo existente `is_active`.
- `amount` conserva el importe neto realmente cobrado, sin el efectivo entregado
  de más ni el cambio. Es decimal exacto, positivo y con dos decimales. No se
  recalcula desde `plans.price`: los cambios de tarifa no alteran el historial y
  se permiten precios acordados distintos de la tarifa actual.
- `currency` solo admite `MXN`; se adopta una única moneda para evitar sumar
  importes de monedas diferentes. Todos los registros representan efectivo.
- `paid_at` registra el momento del cobro con zona horaria; por defecto usa la
  hora de la transacción. Se puede proporcionar la fecha real de un cobro previo.
  `notes` permite añadir una observación opcional, como el motivo de un descuento.
- Los índices permiten buscar cobros por empleado y por fecha. La restricción
  única de membresía también aporta un índice para consultar su pago.

El endpoint `POST /api/memberships` ahora registra membresía y pago juntos en una
transacción, cobrando exactamente la tarifa vigente del plan desde el backend.
La base no impone esa igualdad ni exige pago para una membresía creada por SQL
directo. Las membresías previas no se modifican. Ver
`docs/membership-registration.md`.

La base garantiza las relaciones, la unicidad y los importes válidos. No verifica
que el empleado esté activo ni modifica la vigencia de una membresía al registrar
un pago. Esas reglas requieren lógica de negocio adicional. Las claves de la
membresía y los pagos deben tratarse como historial al implementar su edición;
esta migración no incorpora auditoría ni bloquea modificaciones o borrados de pagos.

Ejemplo (reemplazar los identificadores por registros existentes):

```sql
INSERT INTO payments (membership_id, employee_id, amount, notes)
VALUES (1, 1, 500.00, 'Cobro en recepción')
RETURNING payment_id, paid_at;

SELECT p.payment_id, m.member_id, m.name AS member_name,
       p.amount, p.currency, p.paid_at, e.name AS received_by
FROM payments p
JOIN memberships ms ON ms.membership_id = p.membership_id
JOIN members m ON m.member_id = ms.member_id
JOIN employees e ON e.employee_id = p.employee_id
ORDER BY p.paid_at DESC;
```

## Verificación de integridad

Después de aplicar las migraciones en una base de pruebas:

```sh
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < tests/sql/test_cash_payments.sql
```

El script crea datos temporales dentro de una transacción, verifica las reglas y
revierte sus cambios. Las secuencias pueden avanzar aun después del rollback;
por eso debe ejecutarse en una base de pruebas.

## Roles fijos y planes iniciales

`003_immutable_employee_roles.sql` impide modificar `employees.role_id` y renombrar
`roles.name`. Es transaccional; debe aplicarse una sola vez. Se puede comprobar su
presencia mediante los triggers `employees_role_immutable` y `roles_name_immutable`.

`004_membership_plans.sql` inserta Plan Básico (350.00, 30 días), Plan Premium
(900.00, 90 días) y Plan Anual (3000.00, 365 días). No es idempotente: antes de
aplicarla a una base existente, comprobar si esos nombres, precios y duraciones
ya están presentes para no repetir el insert ni provocar una violación de unicidad.

## Base para pytest

Usar una base separada de la de desarrollo. En este entorno está preparada
`mi_proyecto_test` con las migraciones 001–004. Para preparar otra desde cero,
crear la base y ejecutar los cuatro scripts en orden, sustituyendo `-d mi_proyecto`
por `-d mi_proyecto_test` en los comandos anteriores.

Configurar en `.env` (archivo ignorado por Git):

```dotenv
TEST_DATABASE_URL='postgresql://admin:<password>@127.0.0.1:5432/mi_proyecto_test'
```

Usar la contraseña real y codificar los caracteres reservados si aparecen en la
URL. `tests/conftest.py` carga únicamente esta variable desde `.env`; una variable
exportada tiene prioridad. La suite se ejecuta con:

```sh
poetry run python -m pytest -q
```

Las pruebas de integración crean esquemas aislados y los eliminan al terminar.
La cuenta necesita permisos para crear esos esquemas. Sin `TEST_DATABASE_URL`,
las pruebas de PostgreSQL se omiten.


## Pases QR y entradas

`005_access_passes.sql` crea `access_passes` y `check_ins`. Aplicar una sola vez,
después de las migraciones anteriores:

```sh
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/005_access_passes.sql
```

Ya se aplicó en las bases locales `mi_proyecto` y `mi_proyecto_test`. Los pases
conservan únicamente un hash del código. Solo puede existir un pase pendiente por
miembro y una entrada por pase. El backend permite una sola entrada registrada
por miembro y por día en America/Monterrey; generación y escaneo comprueban el
historial bajo el bloqueo del miembro. Este límite no requiere otra migración. Las comprobaciones de cuenta activa y membresía vigente se
realizan en el servicio bajo bloqueos de PostgreSQL. Ver `docs/gym-access.md`.


## Validación de precios en el backend

`006_plan_price_validation_backend.sql` elimina `plans_price_check`. El precio se
valida en los schemas de creación y PATCH de planes: positivo, finito, máximo
99999999.99 y hasta dos decimales. No cambia los datos existentes ni elimina el
tipo NUMERIC(10,2), NOT NULL o la duración positiva. Aplicar después de las
migraciones anteriores, también en instalaciones nuevas que partan de 001:

```sh
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/006_plan_price_validation_backend.sql
```

Ya está aplicada en las bases locales `mi_proyecto` y `mi_proyecto_test`.
Los endpoints de planes y registro de empleados requieren ADMIN; ver `docs/admin.md`.
