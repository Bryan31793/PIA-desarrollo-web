import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { AccessPass, MembershipStatus } from '../lib/types';
import { date } from '../lib/format';
import { useAction } from '../lib/useAction';
import { Button, Card, Icon, Notice, SectionIntro } from '../components/ui';

export function MemberPage() {
  const [status, setStatus] = useState<MembershipStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [pass, setPass] = useState<AccessPass | null>(null);
  const [image, setImage] = useState('');
  const [remaining, setRemaining] = useState(0);
  const [entered, setEntered] = useState(false);
  const [copied, setCopied] = useState(false);
  const generate = useAction<AccessPass>();
  const load = useCallback(async () => {
    setLoading(true); setStatusError(null);
    try { setStatus(await api.membershipStatus()); }
    catch (error) { setStatusError(error instanceof Error ? error.message : 'No se pudo consultar la membresía.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!pass) { setImage(''); setRemaining(0); return; }
    let active = true;
    const tick = () => setRemaining(Math.max(0, Math.ceil((Date.parse(pass.expires_at) - Date.now()) / 1000)));
    tick();
    const interval = window.setInterval(tick, 1000);
    void import('qrcode').then((qr) => qr.toDataURL(pass.pass_token, { width: 320, margin: 2, errorCorrectionLevel: 'M', color: { dark: '#192520', light: '#ffffff' } })).then((url) => { if (active) setImage(url); }).catch(() => generate.setError('No se pudo dibujar el QR. Genera un nuevo pase.'));
    return () => { active = false; window.clearInterval(interval); };
  }, [pass]);
  const createPass = async () => {
    setPass(null); setCopied(false);
    const result = await generate.run(() => api.generatePass());
    if (result) { setPass(result); setEntered(false); }
  };
  useEffect(() => { if (generate.error?.includes('entrada de hoy ya fue registrada')) { setEntered(true); setPass(null); } }, [generate.error]);
  const membership = status?.membership;
  return <>
    <SectionIntro eyebrow="TU ESPACIO PERSONAL" title="Hoy también cuenta.">Consulta tu membresía y lleva tu pase listo para tu próxima sesión.</SectionIntro>
    <div className="member-grid">
      <div className="stack">
        <section className={`membership-card ${status?.has_active_plan ? 'active' : ''}`}>
          <div className="membership-top"><span className="eyebrow">MI MEMBRESÍA</span><span className={`pill ${status?.has_active_plan ? 'lime' : 'muted'}`}>{loading ? 'Consultando' : status?.has_active_plan ? 'Vigente' : 'Sin plan vigente'}</span></div>
          <Icon name="card" size={34} /><h2>{loading ? 'Cargando tu plan…' : membership?.plan_name || 'Tu siguiente paso empieza aquí.'}</h2>
          <p>{membership ? 'Todo listo para seguir avanzando.' : 'Acércate a recepción para activar una membresía.'}</p>
          {membership && <div className="membership-dates"><div><span>FECHA DE INICIO</span><strong>{date(membership.start_date)}</strong></div><div><span>VIGENTE HASTA</span><strong>{date(membership.end_date)}</strong></div></div>}
          <span className="membership-decoration" aria-hidden="true">↗</span>
        </section>
        <Notice>{statusError}</Notice>
        <Button variant="secondary" onClick={() => void load()} busy={loading}><Icon name="refresh" size={16} />Actualizar membresía</Button>
        <Card title="Un poco de constancia, todos los días." icon="clock"><p className="body-copy">Tu membresía incluye sus fechas de inicio y fin. El acceso se valida con la fecha de Monterrey al llegar al gimnasio.</p></Card>
      </div>
      <Card className="pass-card" title="Tu pase de entrada" subtitle="Muéstralo en recepción para entrar." icon="scan">
        <div className={`qr-frame ${image && remaining > 0 ? 'ready' : ''}`}>
          {image && remaining > 0 ? <img src={image} alt="Código QR de tu pase de entrada" width={256} height={256} /> : <div className="qr-placeholder"><Icon name={entered ? 'check' : 'scan'} size={58} /><strong>{entered ? 'Nos vemos mañana' : pass ? 'El pase expiró' : 'Tu próximo entrenamiento te espera'}</strong><span>{entered ? 'La entrada de hoy ya fue registrada.' : 'Genera tu QR cuando estés por entrar.'}</span></div>}
        </div>
        {pass && remaining > 0 && <div className="countdown"><span><span className="live-dot" />Pase listo para escanear</span><strong>{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}</strong><progress max={pass.expires_in} value={remaining} aria-label="Tiempo restante del pase" /></div>}
        <Notice>{generate.error}</Notice>
        <Button onClick={() => void createPass()} busy={generate.busy} disabled={!status?.has_active_plan || entered || loading}><Icon name={pass ? 'refresh' : 'scan'} size={18} />{pass ? 'Generar nuevo QR' : 'Generar pase QR'}</Button>
        <p className="fine-print">Válido por 2 minutos · Una entrada por día.<br />Al generar otro pase, el anterior deja de funcionar.</p>
        {pass && remaining > 0 && <details className="token-details"><summary>¿Usas un lector sin cámara?</summary><input readOnly aria-label="Código del pase" value={pass.pass_token} onFocus={(e) => e.target.select()} /><Button variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(pass.pass_token); setCopied(true); } catch { setCopied(false); } }}>{copied ? 'Código copiado' : 'Copiar código'}</Button></details>}
      </Card>
    </div>
  </>;
}
