CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;  -- emails case-insensitive

-- 1. Roles (solo empleados)
CREATE TABLE IF NOT EXISTS roles (
    role_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(50)  NOT NULL UNIQUE,
    description VARCHAR(100) NOT NULL
);

INSERT INTO roles (name, description) VALUES
    ('Admin', 'configure plans, pricing, employees and reports'),
    ('Staff', 'register members, charge memberships, make check-in')
ON CONFLICT (name) DO NOTHING;

-- 2. Plans
CREATE TABLE IF NOT EXISTS plans (
    plan_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(50)   NOT NULL UNIQUE,
    price         NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    duration_days INT           NOT NULL CHECK (duration_days > 0)
);

-- 3. Employees
CREATE TABLE IF NOT EXISTS employees (
    employee_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         CITEXT       NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    role_id       BIGINT       NOT NULL REFERENCES roles(role_id) ON DELETE RESTRICT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 4. Members (clientes)
CREATE TABLE IF NOT EXISTS members (
    member_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         CITEXT       NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 5. Memberships
CREATE TABLE IF NOT EXISTS memberships (
    membership_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id     BIGINT NOT NULL REFERENCES members(member_id) ON DELETE RESTRICT,
    plan_id       BIGINT NOT NULL REFERENCES plans(plan_id) ON DELETE RESTRICT,
    start_date    DATE   NOT NULL,
    end_date      DATE   NOT NULL,
    CHECK (end_date > start_date),
    CONSTRAINT no_overlap EXCLUDE USING gist (
        member_id WITH =,
        daterange(start_date, end_date, '[]') WITH &&
    )
);

CREATE INDEX IF NOT EXISTS idx_memberships_member_id ON memberships (member_id);
CREATE INDEX IF NOT EXISTS idx_employees_role_id     ON employees (role_id);    