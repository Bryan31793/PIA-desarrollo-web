import { useEffect, useState, useSyncExternalStore } from 'react';
import { api } from './lib/api';
import type { Session } from './lib/types';
import { currentDate } from './lib/format';
import { Brand, Icon, Notice, type IconName } from './components/ui';
import { AuthPage } from './pages/AuthPage';
import { MemberPage } from './pages/MemberPage';
import { StaffPage } from './pages/StaffPage';
import { AdminPage } from './pages/AdminPage';

const navigation: Record<string, { id: string; label: string; icon: IconName }[]> = {
  member: [{ id: 'home', label: 'Mi membresía', icon: 'card' }],
  staff: [{ id: 'access', label: 'Control de acceso', icon: 'scan' }, { id: 'members', label: 'Registrar miembro', icon: 'users' }, { id: 'membership', label: 'Activar membresía', icon: 'card' }],
  admin: [{ id: 'plans', label: 'Planes', icon: 'plans' }, { id: 'employees', label: 'Registrar empleado', icon: 'users' }],
};
const roleNames = { member: 'Miembro', staff: 'Recepción', admin: 'Administración' };
function Workspace({ session }: { session: Session }) {
  const items = navigation[session.identity.role];
  const [section, setSection] = useState(items[0].id);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.request('/api/protected').catch((error: unknown) => { if (!cancelled) setConnectionError(error instanceof Error ? error.message : 'No se pudo comprobar la sesión.'); });
    return () => { cancelled = true; };
  }, []);
  return <div className="app-layout">
    <aside className="sidebar"><Brand /><div className="workspace-label">TU GIMNASIO, CONECTADO</div><nav aria-label="Navegación principal">{items.map((item) => <button key={item.id} onClick={() => setSection(item.id)} className={section === item.id ? 'selected' : ''} aria-current={section === item.id ? 'page' : undefined}><Icon name={item.icon} /><span>{item.label}</span>{section === item.id && <span className="nav-dot" />}</button>)}</nav><div className="sidebar-bottom"><div className="sidebar-note"><span>UN PASO A LA VEZ.</span><p>El progreso empieza<br />por estar aquí.</p><span className="note-arrow">↗</span></div><div className="session-box"><span className="avatar">{session.email[0]?.toUpperCase()}</span><div><strong>{roleNames[session.identity.role]}</strong><small title={session.email}>{session.email}</small></div></div><button className="logout" onClick={api.logout}><Icon name="logout" size={18} />Cerrar sesión</button></div></aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb">GymFlow <span>/</span> {roleNames[session.identity.role]}</div><div className="topbar-date"><span className="live-dot" />{currentDate()}</div></header><main className="main-content"><Notice>{connectionError}</Notice>{session.identity.role === 'member' ? <MemberPage /> : session.identity.role === 'staff' ? <StaffPage section={section} /> : <AdminPage section={section} />}</main><footer className="workspace-footer"><span>GYMFLOW © {new Date().getFullYear()}</span><span>Tu espacio para avanzar.</span></footer></div>
  </div>;
}

export default function App() {
  const session = useSyncExternalStore(api.subscribe, api.getSession);
  return session ? <Workspace key={session.identity.subject} session={session} /> : <AuthPage />;
}
