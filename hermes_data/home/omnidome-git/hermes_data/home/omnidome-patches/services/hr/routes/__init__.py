"""HR Service route exports."""

from hr.routes.employees import router as employees_router
from hr.routes.departments import router as departments_router
from hr.routes.leave import router as leave_router
from hr.routes.performance import router as performance_router

__all__ = [
    "employees_router",
    "departments_router",
    "leave_router",
    "performance_router",
]
