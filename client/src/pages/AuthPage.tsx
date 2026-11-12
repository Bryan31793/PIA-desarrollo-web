import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { useAction } from '../lib/useAction';
import { Brand, Button, Field, Icon, Notice } from '../components/ui';
import { MemberForm } from '../components/MemberForm';

export function AuthPage() {
  const [kind, setKind] = useState<'member' | 'employee'>('member');
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const action = useAction<void>();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await action.run(() => api.login(kind, email, password));
    setPassword('');
  };
  return <main className="auth-layout">
    <section className="auth-story">
      <Brand />
      <div className="story-copy"><span className="pill outlined">UN DÍA MÁS CERCA</span><h1>Haz espacio<br />para tu<br /><em>mejor versión.</em></h1><p>Tu entrenamiento empieza mucho antes de la primera repetición. Empieza con la decisión de estar aquí.</p></div>
      <div className="orbit-art" aria-hidden="true"><span className="orbit o1" /><span className="orbit o2" /><span className="orbit o3" /><span className="orbit-line" /><span className="orbit-label">MOVE WITH PURPOSE ↗</span></div>
      <footer className="story-footer"><span>CONSTANCIA. ENERGÍA. PROGRESO.</span><span>01 — ∞</span></footer>
    </section>
    <section className="auth-content">
      <div className="auth-mobile-brand"><Brand /></div>
      <div className="auth-card">
        <span className="eyebrow">BIENVENIDO A TU GIMNASIO</span>
        <h2>{register ? 'El primer paso es tuyo.' : 'Qué bueno verte aquí.'}</h2>
        <p className="auth-subtitle">{register ? 'Crea tu cuenta de miembro y continúa en recepción para activar tu plan.' : 'Ingresa para continuar con tu día.'}</p>
        {!register && <div className="segmented" aria-label="Tipo de cuenta"><button type="button" aria-pressed={kind === 'member'} onClick={() => { setKind('member'); action.setError(null); }}>Soy miembro</button><button type="button" aria-pressed={kind === 'employee'} onClick={() => { setKind('employee'); action.setError(null); }}>Equipo</button></div>}
        <Notice kind="success">{notice}</Notice>
        {register ? <MemberForm onCreated={(member) => { setRegister(false); setKind('member'); setEmail(member.email); setNotice(`Tu cuenta está lista. Tu ID de miembro es ${member.member_id}. Inicia sesión para continuar.`); }} /> : <form onSubmit={submit} className="form-stack">
          <Field label="Correo electrónico" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" placeholder="nombre@correo.com" />
          <Field label="Contraseña" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" placeholder="Tu contraseña" />
          <Notice>{action.error}</Notice><Button busy={action.busy} type="submit">Iniciar sesión<Icon name="arrow" size={18} /></Button>
        </form>}
        <div className="auth-switch">{register ? '¿Ya tienes una cuenta?' : '¿Es tu primera vez aquí?'} <button type="button" onClick={() => { setRegister(!register); setNotice(null); action.setError(null); }}>{register ? 'Inicia sesión' : 'Crea tu cuenta'}</button></div>
        <div className="auth-note"><Icon name="shield" size={17} /><span>Tu espacio, siempre contigo.</span></div>
      </div>
      <footer className="auth-footer">GYMFLOW <span>Hecho para seguir avanzando.</span></footer>
    </section>
  </main>;
}
