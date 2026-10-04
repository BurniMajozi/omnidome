import uuid

import pytest
from fastapi import HTTPException

from services.common.auth import AuthContext
from services.tenant_memory.main import require_skill_admin


def test_skill_mutation_requires_agent_admin():
    base = dict(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    with pytest.raises(HTTPException) as rejected:
        require_skill_admin(AuthContext(**base, roles=["org_user"]))
    assert rejected.value.status_code == 403
    assert require_skill_admin(AuthContext(**base, roles=["org_admin"])).tenant_id == base["tenant_id"]
    assert require_skill_admin(AuthContext(**base, roles=[], permissions=["agents.manage"])).tenant_id == base["tenant_id"]
