export const money = (amount: string, currency = 'MXN'): string => new Intl.NumberFormat('es-MX', { style: 'currency', currency }).format(Number(amount));
export const date = (value: string): string => new Intl.DateTimeFormat('es-MX', { dateStyle: 'long' }).format(new Date(`${value}T12:00:00`));
export const dateTime = (value: string): string => new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Monterrey' }).format(new Date(value));
export const currentDate = (): string => new Intl.DateTimeFormat('es-MX', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'America/Monterrey' }).format(new Date());
