"""Capabilities with source publishers, shared by designer and editor."""
EVENT_LABELS = {
 "iot.home.offline":"HomeDome: home connection offline", "iot.home.recovered":"HomeDome: home connection recovered",
 "iot.support.requested":"HomeDome: support access requested",
 "portal.cart.abandoned":"Portal: basket abandoned", "portal.quote.requested":"Portal: quote requested", "portal.registration.inactive":"Portal: registration inactive",
 "sales.lead.created":"Sales: lead created", "sales.lead.stage_changed":"Sales: lead stage changed", "sales.lead.assigned":"Sales: lead assigned",
 "sales.lead.escalated":"Sales: lead escalated", "sales.lead.email_requested":"Sales: lead email requested", "sales.lead.outbound_requested":"Sales: outbound requested",
 "sales.lead.campaign_requested":"Sales: campaign requested", "sales.deal.stage_changed":"Sales: deal stage changed", "sales.deal.won":"Sales: deal won", "sales.deal.lost":"Sales: deal lost",
 "platform.billing.credits.low":"Platform billing: credits low", "platform.billing.credits.exhausted":"Platform billing: credit limit reached",
 "platform.billing.credits.topped_up":"Platform billing: credits topped up", "platform.billing.subscription.payment_failed":"Platform billing: payment failed",
 "platform.billing.plan.activated":"Platform billing: plan activated", "platform.billing.payment.review":"Platform billing: payment review",
}
NODE_TYPES = {"trigger", "agent_invoke", "http_request", "notification", "transform", "condition", "end"}

def activation_errors(definition, event=None):
    errors=[]
    nodes=definition.get("nodes",[]) if isinstance(definition,dict) else []
    edges=definition.get("edges",[]) if isinstance(definition,dict) else []
    if not isinstance(nodes,list) or not isinstance(edges,list) or not nodes or len(nodes)>100 or len(edges)>200:
        return ["Use a graph with 1–100 steps and at most 200 connections"]
    ids={n.get("id") for n in nodes if isinstance(n,dict) and isinstance(n.get("id"),str)}
    if len(ids)!=len(nodes): return ["Each step needs a unique text ID"]
    types={n["id"]:n.get("type") for n in nodes}
    if any(not isinstance(n.get("config",{}),dict) for n in nodes): return ["Each step configuration must be an object"]
    if any(kind not in NODE_TYPES for kind in types.values()):errors.append("A step type is not supported by the runner")
    starts=[ident for ident,kind in types.items() if kind=="trigger"]
    if len(starts)!=1:errors.append("Use exactly one trigger")
    if "end" not in types.values():errors.append("Connect at least one End step")
    graph={ident:[] for ident in ids}
    for edge in edges:
        if not isinstance(edge,dict) or edge.get("from") not in ids or edge.get("to") not in ids:
            errors.append("A connection points to a missing step");continue
        source,target=edge["from"],edge["to"]
        if source==target or target in graph[source] or types[source]=="end" or types[target]=="trigger":errors.append("Remove invalid or duplicate connections")
        graph[source].append(target)
    for ident,targets in graph.items():
        if types[ident]=="condition":
            labels=[str(e.get("condition","")).lower() for e in edges if isinstance(e,dict) and e.get("from")==ident]
            if sorted(labels)!=["false","true"]:errors.append("A condition needs one true and one false connection")
        elif types[ident]!="end" and len(targets)!=1:errors.append("Every non-condition step needs one outgoing connection")
        if types[ident]=="agent_invoke" and not str(next(n for n in nodes if n["id"]==ident).get("config",{}).get("message","")).strip():errors.append("Agent steps need instructions")
    active,visited=set(),set()
    def visit(ident):
        if ident in active:errors.append("Loops are not supported");return
        if ident in visited:return
        active.add(ident)
        for target in graph[ident]:visit(target)
        active.remove(ident);visited.add(ident)
    if len(starts)==1:
        visit(starts[0])
        if visited!=ids:errors.append("Connect every step to the trigger")
    if event and event not in EVENT_LABELS:errors.append(f"No verified publisher for '{event}'. Save as a draft or choose an available event.")
    return list(dict.fromkeys(errors))
