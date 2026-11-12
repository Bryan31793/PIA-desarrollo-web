import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { useAction } from '../lib/useAction';
import type { Member } from '../lib/types';
import { Button, Field, Icon, Notice } from './ui';

export function MemberForm({
  onCreated,
  label = 'Crear cuenta',
}: {
  onCreated: (member: Member) => void;
  label?: string;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const action = useAction<Member>();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const member = await action.run(() => api.registerMember({ name, email, password }));
    if (member) {
      setPassword('');
      onCreated(member);
    }
  };
  return (
    <form onSubmit={submit} className="form-stack">
      <Field
        label="Nombre completo"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        maxLength={100}
        autoComplete="name"
        placeholder="Tu nombre y apellido"
      />
      <Field
        label="Correo electrónico"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        maxLength={254}
        autoComplete="email"
        placeholder="nombre@correo.com"
      />
      <Field
        label="Contraseña"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={8}
        maxLength={128}
        autoComplete="new-password"
        hint="Al menos 8 caracteres."
        placeholder="Elige una contraseña"
      />
      <Notice>{action.error}</Notice>
      <Button busy={action.busy} type="submit">
        {label}
        <Icon name="arrow" size={18} />
      </Button>
    </form>
  );
}
