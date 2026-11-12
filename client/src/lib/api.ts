import type { AccessPass, CheckIn, Employee, EmployeeInput, Identity, Member, MemberInput, Membership, MembershipStatus, Plan, PlanInput, Session, TokenPair } from './types';

const SESSION_KEY = 'gymflow.session';
const messages: Record<string, string> = {
  'Invalid username or password': 'El correo o la contraseña son incorrectos.',
  'Storage is temporarily unavailable': 'El servicio no está disponible por el momento. Intenta de nuevo.',
  'Member has already checked in today': 'Tu entrada de hoy ya fue registrada. Podrás generar otro pase mañana.',
  'Member account is inactive': 'La cuenta del miembro está inactiva. Consulta con recepción.',
  'An active membership is required': 'Necesitas una membresía vigente para entrar al gimnasio.',
  'Access pass is invalid, expired, or already used': 'Este pase expiró, ya se utilizó o fue reemplazado. Solicita uno nuevo.',
  'Membership dates overlap an existing membership': 'El miembro ya tiene una membresía que coincide con estas fechas.',
  'Member not found': 'No se encontró al miembro. Revisa su ID.',
  'Plan not found': 'No se encontró el plan. Revisa su ID.',
  'Email is already registered': 'Este correo ya tiene una cuenta de miembro.',
  'Employee email is already registered': 'Este correo ya tiene una cuenta de empleado.',
  'Plan name is already registered': 'Ya existe un plan con ese nombre.',
  'Insufficient permissions': 'Tu cuenta no tiene permiso para realizar esta operación.',
  'Plan price must be greater than zero': 'El plan debe tener un precio mayor que cero.',
};

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(messages[detail] || detail);
    this.name = 'ApiError';
  }
}

function errorDetail(value: unknown): string {
  if (typeof value !== 'object' || value === null || !('detail' in value)) return 'No se pudo completar la operación.';
  const detail = value.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { loc?: unknown[]; msg?: string }) => {
      const field = item.loc?.filter((part) => part !== 'body' && part !== 'path').join(' · ');
      return `${field ? `${field}: ` : ''}${item.msg || 'Revisa este dato.'}`;
    }).join('\n');
  }
  return 'Revisa los datos e intenta de nuevo.';
}

function decodeAccess(token: string): Identity & { exp: number } {
  const encoded = token.split('.')[1];
  if (!encoded) throw new Error('Invalid token');
  const payload = encoded.replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')), (c) => c.charCodeAt(0));
  const claims: Record<string, unknown> = JSON.parse(new TextDecoder().decode(bytes));
  if (!['member', 'staff', 'admin'].includes(String(claims.role)) || typeof claims.sub !== 'string' || typeof claims.exp !== 'number') throw new Error('Invalid token');
  // Solo controla la presentación. El backend valida firma, rol y autorización.
  return { subject: claims.sub, role: claims.role as Identity['role'], exp: claims.exp };
}

function browserStorage(): Storage | undefined {
  try { return globalThis.sessionStorage; } catch { return undefined; }
}

export class ApiClient {
  private session: Session | null = null;
  private listeners = new Set<() => void>();
  private refreshFlight: { epoch: number; promise: Promise<void> } | null = null;
  private epoch = 0;

  constructor(private fetcher: typeof fetch = (...args) => fetch(...args), private storage: Storage | undefined = browserStorage()) {
    try {
      const saved = this.storage?.getItem(SESSION_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Session;
        if (!parsed.tokens?.refresh_token || typeof parsed.email !== 'string') throw new Error('Invalid session');
        this.session = { ...parsed, identity: decodeAccess(parsed.tokens.access_token) };
      }
    } catch { try { this.storage?.removeItem(SESSION_KEY); } catch { /* Almacenamiento no disponible. */ } }
  }

  getSession = (): Session | null => this.session;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(session: Session | null): void {
    this.session = session;
    try {
      if (session) this.storage?.setItem(SESSION_KEY, JSON.stringify(session));
      else this.storage?.removeItem(SESSION_KEY);
    } catch { /* La sesión sigue en memoria si el navegador bloquea el almacenamiento. */ }
    this.listeners.forEach((listener) => listener());
  }

  logout = (): void => {
    this.epoch += 1;
    this.refreshFlight = null;
    this.publish(null);
  };

  private async send(path: string, init: RequestInit = {}): Promise<Response> {
    try { return await this.fetcher(path, { ...init, cache: 'no-store' }); }
    catch { throw new ApiError(0, 'No se pudo conectar con el servidor. Comprueba tu conexión e intenta de nuevo.'); }
  }

  private async read<T>(response: Response): Promise<T> {
    const value: unknown = await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, errorDetail(value));
    if (value === null) throw new ApiError(502, 'El servidor no devolvió una respuesta válida.');
    return value as T;
  }

  async login(kind: 'member' | 'employee', email: string, password: string): Promise<void> {
    const epoch = ++this.epoch;
    const response = await this.send(kind === 'member' ? '/auth/login' : '/auth/employees/login', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }),
    });
    const tokens = await this.read<TokenPair>(response);
    if (epoch !== this.epoch) throw new ApiError(401, 'La sesión cambió. Inicia sesión de nuevo.');
    this.refreshFlight = null;
    this.publish({ tokens, identity: decodeAccess(tokens.access_token), email });
  }

  private async renew(): Promise<void> {
    const session = this.session;
    if (!session) throw new ApiError(401, 'Inicia sesión para continuar.');
    const epoch = this.epoch;
    if (this.refreshFlight?.epoch === epoch) return this.refreshFlight.promise;
    const promise = (async () => {
      const response = await this.send('/auth/refresh', { method: 'POST', headers: { Authorization: `Bearer ${session.tokens.refresh_token}` } });
      if (epoch !== this.epoch) throw new ApiError(401, 'La sesión cambió. Inicia sesión de nuevo.');
      if (response.status === 401) {
        this.logout();
        throw new ApiError(401, 'Tu sesión terminó. Inicia sesión de nuevo.');
      }
      const tokens = await this.read<TokenPair>(response);
      if (epoch !== this.epoch) throw new ApiError(401, 'La sesión cambió. Inicia sesión de nuevo.');
      this.publish({ tokens, identity: decodeAccess(tokens.access_token), email: session.email });
    })();
    const flight = { epoch, promise };
    this.refreshFlight = flight;
    try { await promise; }
    finally { if (this.refreshFlight === flight) this.refreshFlight = null; }
  }

  async request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
    if (!authenticated) return this.read<T>(await this.send(path, init));
    const epoch = this.epoch;
    if (!this.session) throw new ApiError(401, 'Inicia sesión para continuar.');
    if (decodeAccess(this.session.tokens.access_token).exp * 1000 <= Date.now() + 5000) await this.renew();
    if (epoch !== this.epoch || !this.session) throw new ApiError(401, 'Tu sesión terminó.');
    const token = this.session.tokens.access_token;
    const authenticatedInit = (access: string): RequestInit => {
      const headers = new Headers(init.headers);
      headers.set('Authorization', `Bearer ${access}`);
      return { ...init, headers };
    };
    let response = await this.send(path, authenticatedInit(token));
    if (response.status === 401) {
      if (epoch !== this.epoch || !this.session) throw new ApiError(401, 'Tu sesión terminó.');
      if (this.session.tokens.access_token === token) await this.renew();
      if (epoch !== this.epoch || !this.session) throw new ApiError(401, 'Tu sesión terminó.');
      response = await this.send(path, authenticatedInit(this.session.tokens.access_token));
      if (epoch !== this.epoch) throw new ApiError(401, 'La sesión cambió.');
      if (response.status === 401) this.logout();
    }
    return this.read<T>(response);
  }

  private json<T>(path: string, body: unknown, method = 'POST', authenticated = true): Promise<T> {
    return this.request<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, authenticated);
  }

  registerMember = (data: MemberInput): Promise<Member> => this.json('/auth/register', data, 'POST', false);
  membershipStatus = (): Promise<MembershipStatus> => this.request('/api/memberships/me');
  generatePass = (): Promise<AccessPass> => this.request('/api/access-passes', { method: 'POST' });
  checkIn = (pass_token: string): Promise<CheckIn> => this.json('/api/check-ins', { pass_token });
  registerMembership = (member_id: number, plan_id: number): Promise<Membership> => this.json('/api/memberships', { member_id, plan_id });
  createPlan = (data: PlanInput): Promise<Plan> => this.json('/api/plans', data);
  patchPlan = (id: number, data: Partial<PlanInput>): Promise<Plan> => this.json(`/api/plans/${id}`, data, 'PATCH');
  registerEmployee = (data: EmployeeInput): Promise<Employee> => this.json('/api/employees', data);
}

export const api = new ApiClient();
