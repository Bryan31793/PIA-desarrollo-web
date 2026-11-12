# Autenticación y roles

La autenticación identifica la cuenta y la autorización comprueba qué rutas puede
usar. Las dos comprobaciones se ejecutan mediante dependencias en los endpoints;
no hay middleware de autenticación. Una ruta nueva no queda protegida por
comenzar con `/api`: debe declarar su dependencia.

## Roles fijos

`app/core/roles.py` define `Role(StrEnum)` con `ADMIN = "admin"`,
`STAFF = "staff"` y `MEMBER = "member"`.

El cliente nunca elige su rol al iniciar sesión ni al registrarse. Un cliente
recibe siempre `Role.MEMBER`. Los empleados reciben `Role.ADMIN` o `Role.STAFF`
según su registro en PostgreSQL; los nombres existentes `Admin` y `Staff` se
mapean explícitamente al enum. Los roles desconocidos impiden el login.

El rol de un empleado se asigna al crear su cuenta y no puede cambiarse. Aplicar
`migrations/003_immutable_employee_roles.sql` después de las migraciones
anteriores: agrega triggers que rechazan modificar `employees.role_id` y renombrar
`roles.name`. Sí permite actualizar otros datos y reasignar el mismo valor.
No se agregan endpoints para crear empleados ni para cambiar roles.

## Inicio de sesión

| Endpoint | Cuenta consultada | Rol |
| --- | --- | --- |
| `POST /auth/login` | `members` | `member` |
| `POST /auth/employees/login` | `employees JOIN roles` | `admin` o `staff` |

Los servicios `authenticate()` y `authenticate_employee()` devuelven el schema
`TokenPairResponse` de `app/schemas/auth.py` o lanzan `InvalidCredentialsError`,
traducido a HTTP 401 por el manejador de errores. La construcción de la respuesta
y la emisión de tokens permanecen en `auth_service.py`; los routers delegan en
estos servicios.

Ambos reciben formulario con `username` (correo) y `password` y requieren una
cuenta activa. El mismo correo puede existir en las dos tablas; cada endpoint
consulta exclusivamente su tipo de cuenta, sin intentar iniciar sesión en la otra.

```sh
curl -i http://localhost:8000/auth/employees/login \
  --data-urlencode 'username=staff@example.com' \
  --data-urlencode 'password=tu contraseña'
```

Respuesta `200`:

```json
{
  "access_token": "<JWT de acceso>",
  "refresh_token": "<JWT de renovación>",
  "token_type": "bearer",
  "expires_in": 600
}
```

Contraseña incorrecta, cuenta inexistente, inactiva o rol desconocido devuelven
`401` con `{"detail":"Invalid username or password"}`. Se verifica un hash
Argon2 ficticio cuando no existe la cuenta para evitar omitir ese trabajo.
PostgreSQL no disponible devuelve `503`. Se necesita Redis para persistir tokens.

## Claims e identidad

El access token conserva `jti`, `iat`, `exp`, `iss`, `aud` y `token_type`, y utiliza:

```json
{
  "sub": "employee:42",
  "role": "staff",
  "token_type": "access"
}
```

Para un cliente, `sub` sería `member:42` y `role` sería `member`. La identidad se
basa en el ID estable, no en un correo que puede cambiar. Los prefijos evitan
colisiones entre IDs de las tablas. `AuthenticatedIdentity` es inmutable y
comprueba la correspondencia entre tipo de cuenta y rol.

El servidor comprueba firma, expiración, emisor, audiencia, claims obligatorios,
formato del sujeto, rol válido, tipo de token y vigencia de su `jti` en Redis.
Los errores de autenticación devuelven `401` y `WWW-Authenticate: Bearer`.

## Protección de endpoints

Usar `Depends(verify_access_token)` cuando basta con estar autenticado. Para
restringir por rol:

```python
identity: Annotated[
    AuthenticatedIdentity,
    Depends(require_roles(Role.ADMIN, Role.STAFF)),
]
```

`require_roles` permite cualquiera de los roles indicados; no implica una
jerarquía automática. Un usuario autenticado sin el rol requerido recibe `403`
con `{"detail":"Insufficient permissions"}`. Los permisos sobre recursos
propios requieren además comparar el propietario con la identidad autenticada.

`GET /api/protected` admite los tres roles y responde:

```json
{"message":"Access granted","subject":"member:42","role":"member"}
```

`GET /api/employees/protected` admite únicamente `ADMIN` y `STAFF`, con el mismo
formato de respuesta. Estas rutas permiten comprobar la autenticación y los roles;
no consultan datos de negocio.

## Renovación

Enviar el refresh token en el encabezado Bearer:

```sh
curl -i -X POST http://localhost:8000/auth/refresh \
  -H 'Authorization: Bearer <refresh_token>'
```

El refresh token identifica la cuenta con el mismo `sub`, sin un claim de rol.
Antes de emitir la nueva pareja, se consulta PostgreSQL para comprobar que la
cuenta existe y sigue activa y obtener su rol fijo. Se conserva el consumo único
y atómico en Redis: al renovar, se elimina el refresh anterior y se revoca el
access asociado. Un refresh consumido no puede reutilizarse.

Los access tokens duran 10 minutos y los refresh tokens, 7 días. Desactivar una
cuenta impide renovar; el access ya emitido puede funcionar hasta su expiración
o revocación en Redis. La renovación ahora requiere también PostgreSQL.

## Compatibilidad y despliegue

- Aplicar `003_immutable_employee_roles.sql` para imponer los roles fijos en la base.
- Los JWT antiguos con correo en `sub` o sin `role` no son compatibles: volver a
  iniciar sesión. No se migran ni se aceptan esos tokens.
- `/api/protected` devuelve `subject` y `role` en lugar de `username`.
- El login de clientes conserva URL, formulario y formato de respuesta.
- El registro público sigue creando únicamente clientes con rol implícito `MEMBER`.
- No se agregan dependencias ni variables de entorno.
- Swagger utiliza `/auth/login` como URL del flujo OAuth2. Para probar empleados,
  obtener su token en `/auth/employees/login` y enviar el encabezado Bearer.

## Verificación

```sh
poetry run python -m pytest -q
poetry run ruff check .
```

Las pruebas sin servicios externos cubren login por tipo de cuenta, contraseña,
estado activo, roles inválidos, separación de identidades, permisos por endpoint,
claims inválidos, expiración, revocación y rotación con rechazo de reutilización.
Las pruebas de PostgreSQL son opcionales y requieren `TEST_DATABASE_URL`; pytest
lee esta variable desde `.env` si no está exportada. Un valor exportado, incluso
vacío, tiene prioridad. Usan un
esquema aislado y comprueban también la inmutabilidad de roles con la migración 003.

Resultado de la verificación con PostgreSQL local: **68 pruebas aprobadas, sin
omisiones**. Se aplicó la migración 003 en `mi_proyecto` y se verificaron sus dos
triggers. Los tres planes de la 004 ya existían con los mismos precios y duraciones
en esa base, por lo que no se repitió el insert.

Se creó `mi_proyecto_test`, se aplicaron las migraciones 001–004 y se configuró
`TEST_DATABASE_URL` en `.env` sin registrar credenciales en archivos versionados.
Las pruebas crearon y eliminaron sus esquemas aislados correctamente.
`ruff check .` y `git diff --check` finalizaron correctamente. Pytest reportó una
advertencia de deprecación de Starlette sobre el uso de httpx en TestClient;
no impidió ejecutar las pruebas.
