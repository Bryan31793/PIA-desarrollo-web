import { expect, test, type Page } from '@playwright/test';

const password = 'Client-Test-1234';
async function login(page: Page, email: string, employee = false) {
  await page.goto('/');
  if (employee) await page.getByRole('button', { name: 'Equipo', exact: true }).click();
  await page.getByLabel('Correo electrónico', { exact: true }).fill(email);
  await page.getByLabel('Contraseña', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible();
}

test('member, staff and admin complete real backend flows', async ({ browser, page }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', (error) => consoleErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('Qué bueno verte aquí.')).toBeVisible();
  await page.screenshot({ path: 'test-results/login-desktop.png', fullPage: true });
  const email = `client-${Date.now()}@example.com`;
  await page.getByRole('button', { name: 'Crea tu cuenta' }).click();
  await page.getByLabel('Nombre completo').fill('Miembro E2E');
  await page.getByLabel('Correo electrónico', { exact: true }).fill(email);
  await page.getByLabel('Contraseña', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Crear cuenta', exact: true }).click();
  const notice = page.getByRole('status');
  await expect(notice).toContainText('Tu cuenta está lista');
  const memberId = (await notice.textContent())?.match(/miembro es (\d+)/)?.[1];
  expect(memberId).toBeTruthy();
  await page.getByLabel('Contraseña', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await expect(page.getByText('Sin plan vigente', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generar pase QR' })).toBeDisabled();

  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  staff.on('pageerror', (error) => consoleErrors.push(error.message));
  await login(staff, 'e2e-staff@example.com', true);
  await staff.getByRole('button', { name: 'Activar membresía', exact: true }).click();
  await staff.getByLabel('ID del miembro', { exact: true }).fill(memberId!);
  await staff.getByLabel('ID del plan', { exact: true }).fill('1');
  await staff.getByRole('button', { name: 'Registrar membresía y cobro' }).click();
  await expect(staff.getByText('Membresía y pago confirmados', { exact: true })).toBeVisible();
  await expect(staff.getByText('$350.00', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Actualizar membresía' }).click();
  await expect(page.getByRole('heading', { name: 'Plan Básico', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Generar pase QR', exact: true }).click();
  const qr = page.getByRole('img', { name: 'Código QR de tu pase de entrada' });
  await expect(qr).toBeVisible();
  const image = await qr.getAttribute('src');
  expect(image).toMatch(/^data:image\/png;base64,/);
  await page.screenshot({ path: 'test-results/member-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Generar nuevo QR' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/member-mobile.png', fullPage: true });

  await staff.getByRole('button', { name: 'Control de acceso', exact: true }).click();
  await staff.getByLabel('Imagen del QR').setInputFiles({ name: 'pass.png', mimeType: 'image/png', buffer: Buffer.from(image!.split(',')[1], 'base64') });
  await expect(staff.getByText('Entrada autorizada', { exact: true })).toBeVisible();
  await expect(staff.getByRole('heading', { name: 'Miembro E2E', exact: true })).toBeVisible();
  await staff.screenshot({ path: 'test-results/staff-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Generar nuevo QR', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Tu entrada de hoy ya fue registrada');

  await staff.getByRole('button', { name: 'Registrar miembro', exact: true }).click();
  await staff.getByLabel('Nombre completo').fill('Segundo Miembro');
  await staff.getByLabel('Correo electrónico', { exact: true }).fill(`other-${Date.now()}@example.com`);
  await staff.getByLabel('Contraseña', { exact: true }).fill(password);
  await staff.getByRole('button', { name: 'Registrar miembro', exact: true }).last().click();
  await expect(staff.getByText('Registro exitoso', { exact: true })).toBeVisible();

  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  admin.on('pageerror', (error) => consoleErrors.push(error.message));
  await login(admin, 'e2e-admin@example.com', true);
  const planName = `Plan E2E ${Date.now()}`;
  await admin.getByLabel('Nombre del plan', { exact: true }).fill(planName);
  await admin.getByLabel('Precio en MXN', { exact: true }).fill('400.25');
  await admin.getByLabel('Duración en días', { exact: true }).fill('45');
  await admin.getByRole('button', { name: 'Crear plan', exact: true }).click();
  await expect(admin.getByRole('heading', { name: planName, exact: true })).toBeVisible();
  await admin.getByLabel('Nuevo precio en MXN', { exact: true }).fill('450.25');
  await admin.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(admin.getByText('$450.25', { exact: true })).toBeVisible();
  await admin.screenshot({ path: 'test-results/admin-plans-desktop.png', fullPage: true });
  await admin.getByRole('button', { name: 'Registrar empleado', exact: true }).click();
  const employeeEmail = `employee-${Date.now()}@example.com`;
  await admin.getByLabel('Nombre completo').fill('Equipo E2E');
  await admin.getByLabel('Correo electrónico', { exact: true }).fill(employeeEmail);
  await admin.getByLabel('Contraseña inicial').fill(password);
  await admin.getByRole('button', { name: 'Crear cuenta de empleado' }).click();
  await expect(admin.getByText('Cuenta activa', { exact: true })).toBeVisible();
  await admin.getByRole('button', { name: 'Cerrar sesión' }).click();
  await login(admin, employeeEmail, true);
  await expect(admin.getByRole('button', { name: 'Control de acceso', exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText('Plan Básico', { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
  await staffContext.close();
  await adminContext.close();
});
