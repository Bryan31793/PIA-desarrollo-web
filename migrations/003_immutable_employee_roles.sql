BEGIN;

-- El rol se elige al crear el empleado y permanece fijo durante su vida.
CREATE FUNCTION prevent_employee_role_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.role_id IS DISTINCT FROM OLD.role_id THEN
        RAISE EXCEPTION 'Employee role cannot be changed'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER employees_role_immutable
BEFORE UPDATE OF role_id ON employees
FOR EACH ROW EXECUTE FUNCTION prevent_employee_role_change();

-- Los nombres del catálogo definen el significado de los roles existentes.
CREATE FUNCTION prevent_role_name_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        RAISE EXCEPTION 'Role name cannot be changed'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER roles_name_immutable
BEFORE UPDATE OF name ON roles
FOR EACH ROW EXECUTE FUNCTION prevent_role_name_change();

COMMIT;
