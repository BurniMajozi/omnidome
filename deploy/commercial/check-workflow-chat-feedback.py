"""Read only the owner's recent workflow conversations; bound and redact excerpts."""
import json
import re
from sqlalchemy import text
from services.common.db import get_engine
with get_engine().connect() as db:
    owner=db.execute(text("SELECT id,tenant_id FROM users WHERE is_owner AND is_active ORDER BY created_at LIMIT 1")).first()
    rows=db.execute(text("""SELECT m.role,m.content,m.created_at FROM agent_messages m JOIN agent_conversations c ON c.id=m.conversation_id
      WHERE c.tenant_id=:t AND c.context->>'owner_user_id'=:u AND c.id IN (
        SELECT DISTINCT conversation_id FROM agent_messages WHERE content ILIKE '%workflow%')
      ORDER BY m.created_at DESC LIMIT 12"""),{'t':str(owner.tenant_id),'u':str(owner.id)}).mappings().all()
    for row in reversed(rows):
        content=re.sub(r'(?i)(bearer\s+\S+|(?:sk|pk|key|token)[_-][A-Za-z0-9_-]{16,})','[redacted]',row['content'] or '')
        print(json.dumps({'role':row['role'],'at':str(row['created_at']),'excerpt':content[:500]}))
