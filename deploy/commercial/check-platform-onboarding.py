"""Live read-only and rejected-input checks; no booking, invitation or payment."""
import json
import uuid
import httpx
from sqlalchemy import text
from services.common.db import get_engine
from services.common.internal_auth import sign_headers

with get_engine().connect() as conn:
    tenant=str(conn.execute(text("SELECT id FROM tenants ORDER BY created_at LIMIT 1")).scalar_one())
headers={"x-tenant-id":tenant,"x-user-id":str(uuid.UUID(int=0)),"x-roles":"platform_admin","x-modules":"admin"}
path="/platform/onboarding"
signed={**headers,**sign_headers(headers,"GET",path)}
with httpx.Client(timeout=40) as client:
    result=client.get("http://admin:8013"+path,headers=signed)
    result.raise_for_status()
    payload=result.json()
    checks={"private_admin":True,"demo_configured":payload["config"]["enabled"]}
    for page in ("trial","demo"):
        response=client.get("http://web:3000/"+page)
        response.raise_for_status()
        checks[page+"_page"]=True
    root=client.get("http://web:3000/")
    root.raise_for_status()
    assert "Try it For Free" in root.text and 'href="/demo"' in root.text
    assert "Start Your Free Trial" not in root.text
    checks["live_cta_copy_and_link"]=True
    products=client.get("http://web:3000/products/sales")
    products.raise_for_status()
    assert "Sales Dome" in products.text and "Sales Hub" not in products.text
    checks["live_product_branding"]=True
    calendar=client.get("http://web:3000/api/platform-public/demo")
    calendar.raise_for_status()
    assert set(calendar.json())=={"enabled","timezone","duration_minutes","slots"}
    checks["public_calendar_no_identity"]=True
    invalid=client.post("http://web:3000/api/platform-public/trial-request",json={"email":"invalid"},headers={"x-user-id":str(uuid.uuid4()),"x-roles":"platform_admin"})
    assert invalid.status_code==422,invalid.status_code
    demo_request=client.post("http://web:3000/api/platform-public/demo/request",json={"email":"invalid"})
    assert demo_request.status_code==422,demo_request.status_code
    checks["demo_request_endpoint"]=True
    private=client.get("http://web:3000/svc/admin/platform/onboarding")
    assert private.status_code==401,private.status_code
    checks["public_input_validation"]=True
    checks["anonymous_admin_denied"]=True
    print(json.dumps(checks,sort_keys=True))
