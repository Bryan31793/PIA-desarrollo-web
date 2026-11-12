BEGIN;

-- Cada registro representa el pago completo, en efectivo, de una membresía.
-- El cliente se obtiene mediante memberships.member_id.
CREATE TABLE payments (
    payment_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    membership_id BIGINT NOT NULL,
    employee_id   BIGINT NOT NULL,
    amount        NUMERIC(10,2) NOT NULL,
    currency      VARCHAR(3) NOT NULL DEFAULT 'MXN',
    paid_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes         TEXT,
    CONSTRAINT payments_membership_unique UNIQUE (membership_id),
    CONSTRAINT payments_membership_fk FOREIGN KEY (membership_id)
        REFERENCES memberships(membership_id) ON DELETE RESTRICT,
    CONSTRAINT payments_employee_fk FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id) ON DELETE RESTRICT,
    -- El límite superior también rechaza NaN, que PostgreSQL ordena sobre números.
    CONSTRAINT payments_amount_valid CHECK (amount BETWEEN 0.01 AND 99999999.99),
    CONSTRAINT payments_currency_mxn CHECK (currency = 'MXN')
);

COMMENT ON TABLE payments IS
    'Pagos completos en efectivo de membresías, sin abonos ni devoluciones.';
COMMENT ON COLUMN payments.amount IS
    'Importe neto cobrado, sin incluir cambio. Histórico independiente del precio actual del plan.';
COMMENT ON COLUMN payments.employee_id IS
    'Empleado que recibió el efectivo.';

-- UNIQUE ya crea el índice de membership_id.
CREATE INDEX idx_payments_employee_id ON payments (employee_id);
CREATE INDEX idx_payments_paid_at ON payments (paid_at);

COMMIT;
