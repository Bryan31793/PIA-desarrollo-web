BEGIN;

CREATE TABLE access_passes (
    access_pass_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash     VARCHAR(64) NOT NULL UNIQUE,
    member_id      BIGINT NOT NULL REFERENCES members(member_id) ON DELETE RESTRICT,
    created_at     TIMESTAMPTZ NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    consumed_at    TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT access_passes_expiry_valid CHECK (expires_at > created_at),
    CONSTRAINT access_passes_state_valid CHECK (
        consumed_at IS NULL OR invalidated_at IS NULL
    )
);

-- Incluye pases expirados pendientes: al generar otro se invalidan también.
CREATE UNIQUE INDEX access_passes_one_pending_per_member
ON access_passes (member_id)
WHERE consumed_at IS NULL AND invalidated_at IS NULL;
CREATE INDEX access_passes_member_created_idx ON access_passes (member_id, created_at);

CREATE TABLE check_ins (
    check_in_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    access_pass_id BIGINT NOT NULL UNIQUE REFERENCES access_passes(access_pass_id) ON DELETE RESTRICT,
    membership_id  BIGINT NOT NULL REFERENCES memberships(membership_id) ON DELETE RESTRICT,
    employee_id    BIGINT NOT NULL,
    checked_in_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT check_ins_employee_fk FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id) ON DELETE RESTRICT
);

CREATE INDEX check_ins_membership_time_idx ON check_ins (membership_id, checked_in_at);
CREATE INDEX check_ins_employee_idx ON check_ins (employee_id);

COMMENT ON TABLE access_passes IS
    'Pases QR temporales de un uso. Solo se almacena el hash del código.';
COMMENT ON TABLE check_ins IS
    'Entradas autorizadas por STAFF. El miembro se obtiene del pase utilizado.';

COMMIT;
