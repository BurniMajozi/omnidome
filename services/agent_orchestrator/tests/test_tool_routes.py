"""Every agent tool must call a route its service actually serves.

Checkpoint 1 found 25 of 35 tools pointing at paths like /api/pipeline while the
services serve /pipeline, so agents answered "service unavailable" for data that
exists. This reads the route decorators from each service's source (no running
services needed) and matches every tool's method + endpoint against them.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from services.agent_orchestrator.tools import tool_registry  # noqa: E402
SERVICE_DIRS = {
    "crm": "crm", "billing": "billing", "network": "network", "retention": "retention",
    "support": "support", "analytics": "analytics", "sales": "sales", "finance": "finance",
    "call_center": "call_center", "communication": "communication", "memory": "tenant_memory",
    "fno_intelligence": "fno_intelligence", "hr": "hr", "portal": "portal_builder", "inventory": "inventory",
}
IN_PROCESS = {"orchestrator", "internal"}  # handled inside the agent loop, no HTTP call
METHODS = {"get", "post", "put", "patch", "delete"}


def _str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _prefix(call: ast.Call) -> str:
    return next((_str(k.value) for k in call.keywords if k.arg == "prefix"), None) or ""


def service_routes(service_dir: Path) -> set:
    """(METHOD, path) pairs from @app/@router decorators, with APIRouter(prefix=)
    and include_router(prefix=) applied, through nested routers (router.include_router(child))."""
    decorated, router_prefix, includes = [], {}, []
    for f in service_dir.rglob("*.py"):
        if "tests" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                            and d.func.attr in METHODS and isinstance(d.func.value, ast.Name)
                            and d.args and _str(d.args[0]) is not None):
                        decorated.append((f.stem, d.func.value.id, d.func.attr.upper(), _str(d.args[0]), str(f)))
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if getattr(fn, "id", None) == "APIRouter" or getattr(fn, "attr", None) == "APIRouter":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            router_prefix[(str(f), target.id)] = _prefix(node.value)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "include_router" and node.args):
                includes.append((f.stem, str(f), ast.unparse(node.func.value), ast.unparse(node.args[0]), _prefix(node)))

    def full_prefixes(module, fpath, var, seen=()):
        """Every URL prefix a router ends up under: its own prefix, then each include's prefix and its parent's."""
        own = router_prefix.get((fpath, var), "")
        found = set()
        for inc_module, inc_path, parent, child, prefix in includes:
            if (module in child or child == var) and (inc_module, parent) not in seen:
                parent_prefixes = {""} if parent == "app" else full_prefixes(inc_module, inc_path, parent, seen + ((inc_module, parent),))
                found |= {pp + prefix for pp in parent_prefixes}
        return {fp + own for fp in found} or {own}

    routes = set()
    for module, var, method, path, fpath in decorated:
        if var == "app":
            routes.add((method, path))
            continue
        for p in full_prefixes(module, fpath, var):
            routes.add((method, p + path))
    return routes


def _matches(route_path: str, endpoint: str) -> bool:
    pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", route_path.rstrip("/") or "/") + "$"
    return re.match(pattern, re.sub(r"\{[^}]+\}", "X", endpoint.rstrip("/"))) is not None


def test_every_tool_endpoint_exists_in_its_service():
    cache, broken = {}, []
    for tool in tool_registry._tools.values():
        if tool.service in IN_PROCESS:
            continue
        assert tool.service in SERVICE_DIRS, f"{tool.name}: unknown service {tool.service!r}"
        d = SERVICE_DIRS[tool.service]
        if d not in cache:
            cache[d] = service_routes(REPO / "services" / d)
        if not any(m == tool.method and _matches(p, tool.endpoint) for m, p in cache[d]):
            broken.append(f"{tool.name}: {tool.method} {tool.endpoint} not served by services/{d}")
    assert not broken, "\n".join(sorted(broken))


def test_route_reader_sees_router_prefixes():
    # Guard the reader itself: sales serves GET /pipeline, network's topology
    # router is mounted under /network.
    assert ("GET", "/pipeline") in service_routes(REPO / "services" / "sales")
    assert ("GET", "/network/bandwidth/summary") in service_routes(REPO / "services" / "network")
