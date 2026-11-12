from app.core.passwords import password_hasher
from app.core.roles import Role
from app.infrastructure.employees.repository import employee_repository
from app.schemas.employees import EmployeeRegistration, EmployeeResponse

_EMPLOYEE_ROLE_NAMES = {Role.ADMIN: "Admin", Role.STAFF: "Staff"}


def register_employee(data: EmployeeRegistration) -> EmployeeResponse:
    password_hash = password_hasher.hash(data.password.get_secret_value())
    employee = employee_repository.create(
        data.name,
        str(data.email).lower(),
        password_hash,
        _EMPLOYEE_ROLE_NAMES[data.role],
    )
    return EmployeeResponse.model_validate({**employee, "role": data.role})
