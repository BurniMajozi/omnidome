from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid
import pytest
from services.admin.tests.test_iam import client,sb,make_tenant,platform,as_user,add_user,q


def receipt_body():
    return {"provider":"AgentMail","reference":"test-"+uuid.uuid4().hex,"amount":"20.00","currency":"USD","period_start":"2026-10-01","period_end":"2026-11-01"}


def allocation_body(receipt,amount):
    return {"id":str(uuid.uuid4()),"receipt_id":receipt,"amount":amount,"quantity":"1","unit":"subscription months","reason":"Measured shared supplier subscription"}


def test_supplier_evidence_scope_retry_and_correctable_allocation(client):
    tenant=make_tenant(client);other=make_tenant(client);member,_=add_user(tenant,["org_admin"])
    data=receipt_body()
    assert client.post("/provider-costs/receipts",headers=as_user(tenant,member),json=data).status_code==403
    original=client.post("/provider-costs/receipts",headers=platform(tenant),json=data)
    assert original.status_code==200,original.text
    receipt=original.json()["id"]
    assert client.post("/provider-costs/receipts",headers=platform(tenant),json={**data,"reference":data["reference"].upper()}).json()["id"]==receipt
    assert client.post("/provider-costs/receipts",headers=platform(tenant),json={**data,"amount":"21"}).status_code==409
    assert client.get("/provider-costs/receipts",headers=as_user(tenant,member)).status_code==403
    allocation=allocation_body(receipt,"12.00")
    url=f"/tenants/{tenant}/usage/cost-allocations"
    assert client.post(url,headers=as_user(tenant,member),json=allocation).status_code==403
    assert client.post(url,headers=platform(tenant),json=allocation).status_code==200
    assert client.post(url,headers=platform(tenant),json=allocation).json()["duplicate"] is True
    assert client.post(url,headers=platform(tenant),json={**allocation,"amount":"11"}).status_code==409
    assert client.post(f"/tenants/{other}/usage/cost-allocations",headers=platform(other),json=allocation_body(receipt,"8")).status_code==200
    assert client.post(url,headers=platform(tenant),json=allocation_body(receipt,"0.01")).status_code==409
    for table,key,ident in (("platform_provider_receipts","id",receipt),("platform_provider_cost_allocations","id",allocation["id"])):
        with pytest.raises(Exception):q(f"DELETE FROM {table} WHERE {key}=:id",id=ident)
    void_url=url+"/"+allocation["id"]+"/void"
    assert client.post(void_url,headers=platform(tenant),json={"reason":"Allocation assigned to wrong cost centre"}).status_code==200
    assert client.post(void_url,headers=platform(tenant),json={"reason":"Repeat the same void request"}).json()["duplicate"] is True
    assert not client.get(f"/tenants/{tenant}/usage/costs",headers=platform(tenant)).json()["costs"]
    assert client.post(url,headers=platform(tenant),json=allocation_body(receipt,"10")).status_code==200
    rows=client.get("/provider-costs/receipts",headers=platform(tenant)).json()
    row=next(row for row in rows if row["id"]==receipt)
    assert Decimal(row["allocated"])==18 and Decimal(row["remaining"])==2
    assert row["evidence_source"]=="platform_owner_entry"
    assert q("SELECT count(*) FROM platform_cost_events WHERE tenant_id=:t",t=tenant)[0][0]==2
    costs=client.get(f"/tenants/{tenant}/usage/costs",headers=platform(tenant)).json()
    assert Decimal(str(costs["costs"][0]["amount"]))==10 and costs["margin_available"] is False


def test_shared_invoice_cannot_be_overallocated_concurrently(client):
    tenants=[make_tenant(client),make_tenant(client)]
    response=client.post("/provider-costs/receipts",headers=platform(tenants[0]),json=receipt_body())
    receipt=response.json()["id"]
    def assign(tenant):
        return client.post(f"/tenants/{tenant}/usage/cost-allocations",headers=platform(tenant),json=allocation_body(receipt,"15")).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(assign,tenants))
    assert sorted(statuses)==[200,409]
    assert q("SELECT sum(amount) FROM platform_provider_cost_allocations WHERE receipt_id=:id",id=receipt)[0][0]==15
