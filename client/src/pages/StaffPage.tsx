import { useRef, useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import type { CheckIn, Member, Membership } from '../lib/types';
import { date, dateTime, money } from '../lib/format';
import { useAction } from '../lib/useAction';
import { Button, Card, Field, Icon, Notice, SectionIntro } from '../components/ui';
import { Scanner } from '../components/Scanner';
import { MemberForm } from '../components/MemberForm';

export function StaffPage({ section }: { section: string }) {
  const [memberId, setMemberId] = useState('');
  const [planId, setPlanId] = useState('');
  const [createdMember, setCreatedMember] = useState<Member | null>(null);
  const [code, setCode] = useState('');
  const checking = useRef(false);
  const checkIn = useAction<CheckIn>();
  const membership = useAction<Membership>();
  const submitScan = async (value: string) => {
    if (checking.current) return;
    if (!/^[A-Za-z0-9_-]{43}$/.test(value.trim())) {
      checkIn.setError('Este QR no contiene un pase válido de GymFlow.');
      return;
    }
    checking.current = true;
    try {
      await checkIn.run(() => api.checkIn(value.trim()));
      setCode('');
    } finally {
      checking.current = false;
    }
  };
  const registerMembership = async (event: FormEvent) => {
    event.preventDefault();
    await membership.run(() => api.registerMembership(Number(memberId), Number(planId)));
  };
  if (section === 'members')
    return (
      <>
        <SectionIntro eyebrow="RECEPCIÓN / MIEMBROS" title="Una nueva meta comienza aquí.">
          Registra al miembro y usa su ID para activar una membresía.
        </SectionIntro>
        <div className="two-columns">
          <Card
            title="Registrar miembro"
            subtitle="Una cuenta para gestionar su entrenamiento."
            icon="users"
          >
            <MemberForm
              label="Registrar miembro"
              onCreated={(member) => {
                setCreatedMember(member);
                setMemberId(String(member.member_id));
              }}
            />
          </Card>
          <Card title="Cuenta registrada" icon="check">
            {createdMember ? (
              <div className="result-body">
                <span className="pill lime">Registro exitoso</span>
                <h3>{createdMember.name}</h3>
                <p>{createdMember.email}</p>
                <div className="id-display">
                  <span>ID DEL MIEMBRO</span>
                  <strong>#{createdMember.member_id}</strong>
                </div>
                <p className="body-copy">
                  Comparte este ID con el miembro y úsalo al activar su plan.
                </p>
              </div>
            ) : (
              <div className="empty-state">
                <Icon name="users" size={42} />
                <p>Los datos del nuevo miembro aparecerán aquí.</p>
              </div>
            )}
          </Card>
        </div>
      </>
    );
  if (section === 'membership')
    return (
      <>
        <SectionIntro eyebrow="RECEPCIÓN / MEMBRESÍAS" title="Activa su siguiente etapa.">
          Registra la membresía y el cobro completo en efectivo en una sola operación.
        </SectionIntro>
        <div className="two-columns">
          <Card
            title="Nueva membresía"
            subtitle="El precio y la duración corresponden al plan elegido."
            icon="card"
          >
            <form className="form-stack" onSubmit={registerMembership}>
              <Field
                label="ID del miembro"
                type="number"
                min={1}
                max={Number.MAX_SAFE_INTEGER}
                step={1}
                required
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                placeholder="Ej. 12"
              />
              <Field
                label="ID del plan"
                type="number"
                min={1}
                max={Number.MAX_SAFE_INTEGER}
                step={1}
                required
                value={planId}
                onChange={(e) => setPlanId(e.target.value)}
                placeholder="Ej. 1"
              />
              <div className="info-strip">
                <Icon name="clock" />
                <p>Comienza hoy. La fecha de fin se calcula con la duración del plan.</p>
              </div>
              <Notice>{membership.error}</Notice>
              <Button busy={membership.busy} type="submit">
                Registrar membresía y cobro
                <Icon name="arrow" size={18} />
              </Button>
              <p className="fine-print left">
                Confirma el efectivo recibido antes de registrar. Se cobra el precio exacto del
                plan.
              </p>
            </form>
          </Card>
          <Card title="Comprobante del registro" icon="plans">
            {membership.result ? (
              <div className="result-body">
                <span className="pill lime">Membresía y pago confirmados</span>
                <h3>{money(membership.result.payment.amount)}</h3>
                <p>Cobro completo en efectivo · MXN</p>
                <dl className="detail-list">
                  <div>
                    <dt>Miembro</dt>
                    <dd>#{membership.result.member_id}</dd>
                  </div>
                  <div>
                    <dt>Plan</dt>
                    <dd>#{membership.result.plan_id}</dd>
                  </div>
                  <div>
                    <dt>Inicio</dt>
                    <dd>{date(membership.result.start_date)}</dd>
                  </div>
                  <div>
                    <dt>Termina</dt>
                    <dd>{date(membership.result.end_date)}</dd>
                  </div>
                  <div>
                    <dt>Pago</dt>
                    <dd>#{membership.result.payment.payment_id}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <div className="empty-state">
                <Icon name="card" size={42} />
                <p>Al confirmar, aquí verás las fechas y el importe registrado.</p>
              </div>
            )}
          </Card>
        </div>
      </>
    );
  return (
    <>
      <SectionIntro eyebrow="RECEPCIÓN / ACCESO" title="Cada entrada, un nuevo comienzo.">
        Escanea el pase del miembro. La entrada se registra en cuanto se valida.
      </SectionIntro>
      <div className="two-columns">
        <Card title="Escanear pase" subtitle="Una entrada por miembro y por día." icon="scan">
          <Scanner onScan={(value) => void submitScan(value)} disabled={checkIn.busy} />
          <form
            className="manual-scan"
            onSubmit={(e) => {
              e.preventDefault();
              void submitScan(code);
            }}
          >
            <Field
              label="O ingresa el código del pase"
              value={code}
              required
              minLength={43}
              maxLength={43}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Código de 43 caracteres"
              autoComplete="off"
            />
            <Button type="submit" variant="secondary" busy={checkIn.busy}>
              Registrar entrada
              <Icon name="arrow" size={16} />
            </Button>
          </form>
          <Notice>{checkIn.error}</Notice>
        </Card>
        <Card
          title="Última entrada registrada"
          subtitle="Confirmación de esta sesión de recepción."
          icon="check"
        >
          {checkIn.result ? (
            <div className="result-body entry-success">
              <span className="success-circle">
                <Icon name="check" size={34} />
              </span>
              <span className="pill lime">Entrada autorizada</span>
              <h3>{checkIn.result.member_name}</h3>
              <p>¡A darlo todo en esta sesión!</p>
              <dl className="detail-list">
                <div>
                  <dt>Miembro</dt>
                  <dd>#{checkIn.result.member_id}</dd>
                </div>
                <div>
                  <dt>Membresía</dt>
                  <dd>#{checkIn.result.membership_id}</dd>
                </div>
                <div>
                  <dt>Registro</dt>
                  <dd>#{checkIn.result.check_in_id}</dd>
                </div>
                <div>
                  <dt>Hora de acceso</dt>
                  <dd>{dateTime(checkIn.result.checked_in_at)}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="empty-state">
              <Icon name="shield" size={46} />
              <h3>Esperando el siguiente pase</h3>
              <p>La confirmación del miembro aparecerá aquí cuando se registre su entrada.</p>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
