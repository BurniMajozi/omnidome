"""Read-only live catalogue, quote and rendered pricing checks. No orders or charges."""
import httpx

expected = {"crm", "support", "portal", "retention", "products", "inventory"}
response = httpx.get("http://admin:8013/pricing/catalog", timeout=20)
response.raise_for_status()
catalog = response.json()
assert set(catalog["free_modules"]) == expected
response = httpx.post("http://admin:8013/pricing/quote", json={"bundle": "starter", "modules": {}, "period": "monthly"}, timeout=20)
response.raise_for_status()
quote = response.json()
assert quote["amount_cents"] == 0 and quote["tier"] == "FREE"
assert set(quote["entitlements"]) == expected
assert set(quote["selection"]["modules"].values()) == {"free"}
assert quote["usage_policy"]["monthly_credits"] == 50
assert all(row["writes_per_month"] == 100 for row in quote["usage_policy"]["module_limits"].values())
page = httpx.get("http://web:3000/pricing", timeout=30)
page.raise_for_status()
assert "Compare prices with other tools" in page.text
assert all(name in page.text for name in ("HubSpot", "Zoho Inventory", "Shopify"))
print("Free plan: six Free panels, R0, 50 shared credits, 100 writes per panel. Pricing comparison rendered.")
print("Tax policy:", {key: catalog["tax_policy"].get(key) for key in ("vat_registered", "prices_include_vat")})
