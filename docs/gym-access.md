# Pases QR y registro de entradas

El backend genera el contenido de un pase QR temporal y registra la entrada
cuando STAFF lo escanea. Se utilizan PostgreSQL para los pases y las entradas,
y el mecanismo existente de JWT/Redis para autenticar a los usuarios.

## Reglas implementadas

- El pase dura **120 segundos**, dentro del rango solicitado de 60–120.
- Cada pase se puede usar una sola vez. A los 120 segundos exactos ya expiró.
- Generar otro invalida todos los pases anteriores pendientes del mismo miembro.
- Se permite **una sola entrada registrada por miembro y por día** en
  America/Monterrey. Después de registrar la entrada, generar otro QR devuelve
  `409` (`Member has already checked in today`). El escaneo también comprueba
  ese límite para impedir que otro pase permita una segunda entrada.
- Antes de registrar la entrada se puede regenerar el pase; el anterior queda
  invalidado. El límite se reinicia a medianoche local, no después de 24 horas.
- La cuenta del miembro debe existir y estar activa; debe tener una membresía
  vigente. Se comprueba al generar y al escanear.
- La membresía está vigente cuando `start_date <= hoy <= end_date`, con fecha
  local America/Monterrey. No se exige un pago registrado para esta consulta.
- Un escaneo válido de STAFF registra inmediatamente la entrada; no hay una
  segunda confirmación. ADMIN no tiene acceso a estos endpoints.

## Generación: MEMBER

```sh
curl -i -X POST http://localhost:8000/api/access-passes \
  -H 'Authorization: Bearer <access_token_member>'
```

No requiere body. El miembro se obtiene del token, no de un ID enviado por el
cliente. Devuelve `201` y `Cache-Control: no-store`:

```json
{
  "pass_token": "<codigo aleatorio de 43 caracteres>",
  "expires_at": "2026-01-15T18:02:00Z",
  "expires_in": 120
}
```

El frontend debe convertir **exactamente `pass_token`** en la imagen QR y mostrar
la expiración. El código es opaco: no contiene el nombre, el ID del miembro ni
credenciales JWT. Esta API entrega el contenido; el repositorio no tiene frontend
ni implementa una pantalla de cámara o un lector físico.

## Escaneo: STAFF

El lector decodifica el texto del QR y lo envía mediante el body de un POST:

```sh
curl -i http://localhost:8000/api/check-ins \
  -H 'Authorization: Bearer <access_token_staff>' \
  -H 'Content-Type: application/json' \
  -d '{"pass_token":"<codigo leído del QR>"}'
```

Solo admite `pass_token`, una cadena de 43 caracteres. El miembro se obtiene del
pase y el empleado, del token STAFF. No se aceptan IDs ni fechas en el request.

Devuelve `201` después de confirmar la transacción:

```json
{
  "check_in_id": 1,
  "member_id": 42,
  "member_name": "Ana",
  "membership_id": 7,
  "employee_id": 8,
  "checked_in_at": "2026-01-15T18:01:00Z"
}
```

La interfaz puede mostrar el nombre y la confirmación de entrada al recibir esa
respuesta. Un QR presentado no autoriza por sí solo el acceso: es la respuesta
exitosa del backend la que confirma que la entrada quedó registrada.

| Estado | Situación |
| --- | --- |
| `201` | Pase generado o entrada registrada |
| `401` | JWT inválido, expirado, revocado, ausente o de tipo refresh; empleado del escaneo inexistente |
| `403` | Rol incorrecto, cuenta del miembro inactiva o sin membresía vigente |
| `404` | Cuenta de miembro inexistente |
| `409` | Pase desconocido, expirado, invalidado o ya utilizado; o miembro con entrada ya registrada hoy |
| `422` | Payload de escaneo inválido o con campos adicionales |
| `503` | Persistencia no disponible |

## Almacenamiento y concurrencia

Aplicar una vez `migrations/005_access_passes.sql`. Crea:

- `access_passes`: hash SHA-256 único del código, miembro, creación, expiración,
  consumo e invalidación. El código se genera con `secrets.token_urlsafe(32)` y
  nunca se guarda en texto plano.
- `check_ins`: pase único utilizado, membresía, empleado y hora de entrada. El
  miembro se obtiene mediante el pase, evitando duplicarlo en el historial.

La generación bloquea la fila del miembro, comprueba la elegibilidad e invalida
los pases pendientes antes de guardar el nuevo. Todo ocurre en una transacción:
si falla la creación, el pase anterior no queda invalidado.

El escaneo primero identifica al miembro mediante el hash y toma el mismo bloqueo
del miembro, luego bloquea el pase y la membresía. Consumo y entrada se guardan en
una sola transacción. Si falla la entrada, el pase no queda consumido. La cuenta
activa se conserva bajo bloqueo durante la comprobación; la membresía se bloquea
para evitar cambios mientras se autoriza.

Dos escaneos concurrentes del mismo pase producen una sola entrada. Generación y
escaneo simultáneos del mismo miembro se serializan: si se confirmó primero la
regeneración, el pase anterior ya no sirve; si se autorizó primero el escaneo, esa
entrada queda registrada y se rechaza la regeneración durante el resto del día.

La comprobación diaria consulta el historial de entradas del miembro entre la
medianoche local de hoy (incluida) y la siguiente (excluida). Se ejecuta bajo el
mismo bloqueo de miembro y dentro de la transacción de generación o escaneo. Así,
las solicitudes concurrentes no pueden superar el límite. No requiere migraciones
adicionales y también cuenta las entradas que ya existían en el historial.

Los códigos no se envían en URLs ni deben registrarse en logs. Usar HTTPS en el
entorno publicado. Una captura compartida antes del consumo o expiración sigue
siendo utilizable; la caducidad y el uso único no verifican identidad física.
Los registros se conservan para mantener la relación con las entradas; no se
implementa borrado automático del historial.

## Configuración y pruebas

No añade dependencias ni variables de entorno. Después de las migraciones previas:

```sh
docker compose exec -T db psql -U admin -d mi_proyecto -v ON_ERROR_STOP=1 < migrations/005_access_passes.sql
poetry run python -m pytest -q
poetry run ruff check .
```

La migración 005 se aplicó en las bases locales `mi_proyecto` y `mi_proyecto_test`.
No repetir el script en ellas. Las pruebas crean y eliminan esquemas aislados.
Cubren expiración, invalidación, límite diario y reinicio a medianoche, elegibilidad al escanear,
medianoche de Monterrey, ausencia de pago como requisito, roles, JWT, rollback y
concurrencia tanto de escaneos como de regeneración.
