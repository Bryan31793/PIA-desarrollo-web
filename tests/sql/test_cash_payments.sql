\set ON_ERROR_STOP on
BEGIN;

CREATE FUNCTION pg_temp.expect_error(statement TEXT, expected_state TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = expected_state THEN
            RETURN;
        END IF;
        RAISE;
    END;
    RAISE EXCEPTION 'Se esperaba SQLSTATE % para: %', expected_state, statement;
END;
$$;

DO $$
DECLARE
    test_plan BIGINT;
    test_member BIGINT;
    test_employee BIGINT;
    test_memberships BIGINT[] := '{}';
    new_membership BIGINT;
    test_payment BIGINT;
    row_payment payments%ROWTYPE;
    suffix TEXT := txid_current()::TEXT;
    candidate TEXT;
    i INT;
BEGIN
    INSERT INTO plans (name, price, duration_days)
    VALUES ('payment-test-' || suffix, 500, 30) RETURNING plan_id INTO test_plan;
    INSERT INTO members (name, email, password_hash)
    VALUES ('Test member', 'payment-member-' || suffix || '@example.invalid', 'test')
    RETURNING member_id INTO test_member;
    INSERT INTO employees (name, email, password_hash, role_id)
    SELECT 'Test employee', 'payment-employee-' || suffix || '@example.invalid',
           'test', role_id FROM roles WHERE name = 'Staff'
    RETURNING employee_id INTO test_employee;

    FOR i IN 0..2 LOOP
        INSERT INTO memberships (member_id, plan_id, start_date, end_date)
        VALUES (test_member, test_plan, CURRENT_DATE + i * 60,
                CURRENT_DATE + i * 60 + 30)
        RETURNING membership_id INTO new_membership;
        test_memberships := array_append(test_memberships, new_membership);
    END LOOP;

    -- Un cobro puede diferir del precio actual del plan.
    INSERT INTO payments (membership_id, employee_id, amount)
    VALUES (test_memberships[1], test_employee, 450.25)
    RETURNING payment_id INTO test_payment;
    UPDATE plans SET price = 600 WHERE plan_id = test_plan;
    SELECT * INTO STRICT row_payment FROM payments WHERE payment_id = test_payment;
    IF row_payment.amount <> 450.25 OR row_payment.currency <> 'MXN'
       OR row_payment.paid_at IS NULL THEN
        RAISE EXCEPTION 'El cobro debe conservar importe, moneda y fecha';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM payments p JOIN memberships ms USING (membership_id)
        WHERE p.payment_id = test_payment AND ms.member_id = test_member
    ) THEN
        RAISE EXCEPTION 'El pago debe relacionarse con el cliente';
    END IF;

    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount) VALUES (%s, %s, 500)',
        test_memberships[1], test_employee), '23505');

    FOREACH candidate IN ARRAY ARRAY['0', '-1', '''NaN''', '100000000', 'NULL'] LOOP
        PERFORM pg_temp.expect_error(format(
            'INSERT INTO payments (membership_id, employee_id, amount) VALUES (%s, %s, %s)',
            test_memberships[2], test_employee, candidate),
            CASE candidate
                WHEN 'NULL' THEN '23502'
                WHEN '100000000' THEN '22003'
                ELSE '23514'
            END);
    END LOOP;

    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount, currency) VALUES (%s, %s, 1, ''USD'')',
        test_memberships[2], test_employee), '23514');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount) VALUES (-1, %s, 1)',
        test_employee), '23503');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount) VALUES (%s, -1, 1)',
        test_memberships[2]), '23503');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount) VALUES (NULL, %s, 1)',
        test_employee), '23502');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payments (membership_id, employee_id, amount) VALUES (%s, NULL, 1)',
        test_memberships[2]), '23502');
    PERFORM pg_temp.expect_error(format(
        'DELETE FROM memberships WHERE membership_id = %s', test_memberships[1]), '23503');
    PERFORM pg_temp.expect_error(format(
        'DELETE FROM employees WHERE employee_id = %s', test_employee), '23503');

    -- El mismo empleado puede cobrar otra membresía del cliente.
    INSERT INTO payments (membership_id, employee_id, amount, paid_at)
    VALUES (test_memberships[2], test_employee, 600, now() - INTERVAL '1 day');
    IF EXISTS (SELECT 1 FROM payments WHERE membership_id = test_memberships[3]) THEN
        RAISE EXCEPTION 'No se deben generar cobros para membresías sin pago';
    END IF;
END;
$$;

ROLLBACK;
