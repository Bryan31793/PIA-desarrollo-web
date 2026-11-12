import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import type { Employee, Plan, PlanInput } from '../lib/types';
import { useAction } from '../lib/useAction';
import { money } from '../lib/format';
import { Button, Card, Field, Icon, Notice, SectionIntro, SelectField } from '../components/ui';

export function AdminPage({ section }: { section: string }) {
  const [latest, setLatest] = useState<Plan | null>(null);
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [duration, setDuration] = useState('');
  const [editId, setEditId] = useState('');
  const [editName, setEditName] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [editDuration, setEditDuration] = useState('');
  const [employeeName, setEmployeeName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'staff' | 'admin'>('staff');
  const plan = useAction<Plan>();
  const patch = useAction<Plan>();
  const employee = useAction<Employee>();
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const result = await plan.run(() =>
      api.createPlan({ name, price, duration_days: Number(duration) }),
    );
    if (result) {
      setLatest(result);
      setEditId(String(result.plan_id));
      setName('');
      setPrice('');
      setDuration('');
    }
  };
  const update = async (event: FormEvent) => {
    event.preventDefault();
    const data: Partial<PlanInput> = {};
    if (editName.trim()) data.name = editName;
    if (editPrice) data.price = editPrice;
    if (editDuration) data.duration_days = Number(editDuration);
    if (!Object.keys(data).length) {
      patch.setError('Indica al menos un campo para actualizar.');
      return;
    }
    const result = await patch.run(() => api.patchPlan(Number(editId), data));
    if (result) {
      setLatest(result);
      setEditName('');
      setEditPrice('');
      setEditDuration('');
    }
  };
  const register = async (event: FormEvent) => {
    event.preventDefault();
    const result = await employee.run(() =>
      api.registerEmployee({ name: employeeName, email, password, role }),
    );
    if (result) {
      setPassword('');
      setEmployeeName('');
      setEmail('');
    }
  };
  if (section === 'employees')
    return (
      <>
        <SectionIntro eyebrow="ADMINISTRACIÓN / EQUIPO" title="Un gran equipo hace la diferencia.">
          Crea cuentas para quienes ayudan a que todo siga en movimiento.
        </SectionIntro>
        <div className="two-columns">
          <Card
            title="Registrar empleado"
            subtitle="El rol se asigna al crear la cuenta y queda fijo."
            icon="users"
          >
            <form onSubmit={register} className="form-stack">
              <Field
                label="Nombre completo"
                value={employeeName}
                onChange={(e) => setEmployeeName(e.target.value)}
                required
                maxLength={100}
                autoComplete="name"
                placeholder="Nombre del empleado"
              />
              <Field
                label="Correo electrónico"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                maxLength={254}
                autoComplete="email"
                placeholder="equipo@correo.com"
              />
              <Field
                label="Contraseña inicial"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                hint="Al menos 8 caracteres."
              />
              <SelectField
                label="Rol del empleado"
                value={role}
                onChange={(e) => setRole(e.target.value as 'staff' | 'admin')}
              >
                <option value="staff">Staff · Recepción y accesos</option>
                <option value="admin">Admin · Planes y empleados</option>
              </SelectField>
              <Notice>{employee.error}</Notice>
              <Button type="submit" busy={employee.busy}>
                Crear cuenta de empleado
                <Icon name="plus" size={18} />
              </Button>
            </form>
          </Card>
          <Card title="Cuenta creada" icon="shield">
            {employee.result ? (
              <div className="result-body">
                <span className="pill lime">Cuenta activa</span>
                <h3>{employee.result.name}</h3>
                <p>{employee.result.email}</p>
                <dl className="detail-list">
                  <div>
                    <dt>ID del empleado</dt>
                    <dd>#{employee.result.employee_id}</dd>
                  </div>
                  <div>
                    <dt>Rol</dt>
                    <dd>{employee.result.role === 'admin' ? 'Administrador' : 'Staff'}</dd>
                  </div>
                </dl>
                <p className="body-copy">
                  Ya puede iniciar sesión desde la opción Equipo con el correo y la contraseña que
                  registraste.
                </p>
              </div>
            ) : (
              <div className="empty-state">
                <Icon name="users" size={46} />
                <p>Los datos de la nueva cuenta aparecerán aquí.</p>
              </div>
            )}
          </Card>
        </div>
      </>
    );
  return (
    <>
      <SectionIntro eyebrow="ADMINISTRACIÓN / PLANES" title="Diseña la siguiente meta.">
        Configura los planes que acompañan el progreso de tus miembros.
      </SectionIntro>
      <div className="two-columns">
        <Card title="Crear plan" subtitle="Define su nombre, precio y duración." icon="plus">
          <form onSubmit={create} className="form-stack">
            <Field
              label="Nombre del plan"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={50}
              placeholder="Ej. Plan Semestral"
            />
            <div className="field-row">
              <Field
                label="Precio en MXN"
                type="number"
                step="0.01"
                min="0.01"
                max="99999999.99"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                required
                placeholder="0.00"
              />
              <Field
                label="Duración en días"
                type="number"
                step={1}
                min={1}
                max={2147483647}
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                required
                placeholder="Ej. 30"
              />
            </div>
            <Notice>{plan.error}</Notice>
            <Button type="submit" busy={plan.busy}>
              Crear plan
              <Icon name="arrow" size={18} />
            </Button>
          </form>
        </Card>
        <Card
          title="Actualizar plan"
          subtitle="Completa solo los campos que quieras cambiar."
          icon="plans"
        >
          <form onSubmit={update} className="form-stack">
            <Field
              label="ID del plan a actualizar"
              type="number"
              required
              min={1}
              max={Number.MAX_SAFE_INTEGER}
              step={1}
              value={editId}
              onChange={(e) => setEditId(e.target.value)}
              placeholder="Ej. 1"
            />
            <Field
              label="Nuevo nombre"
              maxLength={50}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="Sin cambios"
            />
            <div className="field-row">
              <Field
                label="Nuevo precio en MXN"
                type="number"
                step="0.01"
                min="0.01"
                max="99999999.99"
                value={editPrice}
                onChange={(e) => setEditPrice(e.target.value)}
                placeholder="Sin cambios"
              />
              <Field
                label="Nueva duración en días"
                type="number"
                min={1}
                max={2147483647}
                step={1}
                value={editDuration}
                onChange={(e) => setEditDuration(e.target.value)}
                placeholder="Sin cambios"
              />
            </div>
            <Notice>{patch.error}</Notice>
            <Button type="submit" variant="secondary" busy={patch.busy}>
              Guardar cambios
              <Icon name="check" size={18} />
            </Button>
          </form>
        </Card>
      </div>
      {latest && (
        <section className="plan-result">
          <span className="icon-tile">
            <Icon name="check" />
          </span>
          <div>
            <span className="eyebrow">PLAN GUARDADO · ID #{latest.plan_id}</span>
            <h3>{latest.name}</h3>
          </div>
          <strong>
            {money(latest.price)}
            <small>{latest.duration_days} días</small>
          </strong>
        </section>
      )}
      <div className="info-strip below">
        <Icon name="shield" />
        <p>
          Los cambios aplican a nuevas membresías. Las fechas e importes ya registrados se
          conservan.
        </p>
      </div>
    </>
  );
}
