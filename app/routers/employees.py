from fastapi import APIRouter, Depends, status

from app.core.roles import Role
from app.schemas.employees import EmployeeRegistration, EmployeeResponse
from app.services.auth_service import require_roles
from app.services.employee_service import register_employee

router = APIRouter(
    prefix="/api/employees",
    tags=["Employees"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "Employee email already registered or role not configured"
        },
        503: {"description": "Storage unavailable"},
    },
)
def register(data: EmployeeRegistration) -> EmployeeResponse:
    return register_employee(data)
