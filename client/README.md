# Cliente GymFlow

SPA en React y TypeScript, construida con Vite. Su interfaz es adaptable a móvil y
escritorio y está en español. Consume los endpoints existentes del backend.

## Iniciar

Desde la raíz del repositorio:

```sh
npm --prefix client ci
npm --prefix client run dev
```

Vite escucha en http://localhost:5173 y redirige `/api` y `/auth` a
http://127.0.0.1:8000. Cambia `BACKEND_URL` en `client/.env` si necesitas otro destino.
El proxy se aplica también a `npm --prefix client run preview` (puerto 4173).

Con Docker, `docker compose up --build` construye el cliente y lo sirve con Nginx
en el puerto 5173, junto al backend, PostgreSQL y Redis. La configuración de Nginx
redirige las mismas rutas a `backend:8000`. No se modificaron reglas del backend
ni se añadieron endpoints para el cliente.

## Pantallas y contratos

| Pantalla            | Operación                                                         |
| ------------------- | ----------------------------------------------------------------- |
| Login de miembro    | Formulario OAuth2 a `POST /auth/login`                            |
| Login de equipo     | Formulario OAuth2 a `POST /auth/employees/login`                  |
| Registro de miembro | JSON a `POST /auth/register`                                      |
| Mi membresía        | `GET /api/memberships/me`                                         |
| Pase QR             | `POST /api/access-passes` y dibujo del código devuelto con qrcode |
| Registrar entrada   | `POST /api/check-ins` con el código leído por ZXing               |
| Activar membresía   | `POST /api/memberships`, solo member_id y plan_id                 |
| Crear plan          | `POST /api/plans`                                                 |
| Actualizar plan     | `PATCH /api/plans/{id}`, solo campos completados                  |
| Registrar empleado  | `POST /api/employees`, rol admin o staff                          |

El API no ofrece listados ni búsquedas de miembros o planes. Se ingresan sus IDs
en recepción y en la edición de planes. Las pantallas muestran los identificadores
y los comprobantes devueltos por registros exitosos. No simulan catálogos ni
historiales persistidos. Al registrar un miembro desde recepción, su ID queda
preseleccionado al abrir la activación de membresía.

El precio se envía como cadena decimal al crear o editar planes; el cobro de
membresía lo determina el servidor. El PATCH omite campos vacíos. Los formularios
muestran errores de validación y negocio sin reintentar automáticamente cobros
ni registros cuando hay conflictos o errores de conexión.

## Sesiones

El cliente guarda la pareja de tokens en `sessionStorage`, limitada a la pestaña,
y mantiene una copia en memoria. Si el navegador bloquea el almacenamiento, la
sesión funciona en memoria y se pierde al recargar. La contraseña no se guarda.
Cerrar sesión elimina estas credenciales locales; la API actual no tiene endpoint
de revocación de sesión.

Al expirar el access token o recibir 401, se usa `POST /auth/refresh` con el refresh
token en Bearer. La rotación se comparte entre solicitudes concurrentes de la
misma pestaña; se reemplazan ambos tokens y la solicitud original se reintenta
como máximo una vez. Un refresh inválido cierra la sesión local. Los errores de
red o 503 no provocan reintentos de operaciones de negocio.

Los claims decodificados solo eligen la pantalla. El backend sigue validando la
firma, la vigencia, Redis y el rol de cada operación. Al entrar se verifica la
sesión con `/api/protected`.

## QR y cámara

El miembro ve el QR, el tiempo restante y la opción de regenerarlo. Al expirar,
la imagen deja de mostrarse. Si el backend informa que ya entró hoy, se bloquea la
generación y se muestra el aviso; el bloqueo visual se restablece al cambiar el
día de Monterrey. La autoridad final del límite diario siempre es el backend.

STAFF puede:

- Abrir la cámara y escanear el QR.
- Cargar una imagen del código.
- Pegar o leer con un lector USB el código de 43 caracteres.

La cámara requiere permiso del navegador y un contexto seguro: HTTPS o localhost.
Para un teléfono conectado a una IP de red local, usar HTTPS. Al salir de la
pantalla, cerrar sesión o terminar la lectura, se detiene la cámara. Un resultado
se procesa una sola vez para evitar escaneos repetidos del mismo cuadro.

## Pruebas

```sh
npm --prefix client test
npm --prefix client run build
npm --prefix client run format:check
```

Las pruebas de Vitest comprueban los contratos de login, almacenamiento,
renovación concurrente, cierre de sesión durante un refresh, manejo de errores,
registro público y precisión de importes/PATCH.

### Navegador contra el backend real

Necesitas `TEST_DATABASE_URL` en `.env` o exportada, PostgreSQL y Redis. El helper
crea un esquema temporal, aplica las migraciones y prepara ADMIN y STAFF solo en
ese esquema. Sus claves Redis se aíslan por ejecución en la base 15 (configurable
con `E2E_REDIS_URL`); nunca hace FLUSHDB. Al detenerlo con Ctrl+C se elimina el
esquema y sus claves. No prepara cuentas en la base real de la aplicación.

```sh
# Una sola vez, instalar Chromium:
cd client
npx playwright install chromium
cd ..

# Terminal 1:
poetry run python scripts/client_e2e_server.py

# Terminal 2:
BACKEND_URL=http://127.0.0.1:8001 npm --prefix client run dev

# Terminal 3:
npm --prefix client run test:e2e
```

El backend temporal escucha únicamente en 127.0.0.1:8001. El recorrido automatizado
usa e2e-admin@example.com y e2e-staff@example.com con la contraseña de pruebas
Client-Test-1234. Esas cuentas solo existen en el esquema temporal y no son
credenciales de producción.

Playwright verifica registro/login de miembro, activación y cobro, QR como imagen
real, lectura de esa imagen por STAFF, límite diario, creación/PATCH de planes,
registro/login de empleado y persistencia de sesión al recargar. También captura
escritorio y móvil y comprueba el desbordamiento horizontal. Las capturas y trazas
quedan en `client/test-results/`, ignorado por Git. La cámara física requiere una
comprobación manual en el dispositivo final; la prueba automatizada usa imagen.
