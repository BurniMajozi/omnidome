import copy
import json
import pytest
from services.agent_orchestrator.workflow_catalog import activation_errors,EVENT_LABELS
from services.agent_orchestrator.workflow_designer import validate_proposal

GRAPH={"nodes":[{"id":"start","type":"trigger","config":{}},{"id":"ask","type":"agent_invoke","config":{"agent_type":"assistant","message":"Summarise"}},{"id":"end","type":"end","config":{}}],"edges":[{"from":"start","to":"ask"},{"from":"ask","to":"end"}]}
def test_sequential_graph_and_sales_publisher_are_valid():
    assert not activation_errors(GRAPH,"sales.deal.won")
    assert "platform.billing.credits.low" in EVENT_LABELS
@pytest.mark.parametrize("change",["dangling","cycle","parallel","duplicate","disconnected","missing_end","missing_instructions"])
def test_invalid_graphs_cannot_activate(change):
    graph=copy.deepcopy(GRAPH)
    if change=="dangling":graph["edges"].append({"from":"ask","to":"gone"})
    if change=="cycle":graph["edges"].append({"from":"ask","to":"start"})
    if change=="parallel":graph["edges"].append({"from":"start","to":"end"})
    if change=="duplicate":graph["edges"].append(graph["edges"][0])
    if change=="disconnected":graph["nodes"].append({"id":"extra","type":"end"})
    if change=="missing_end":graph["nodes"][2]["type"]="transform"
    if change=="missing_instructions":graph["nodes"][1]["config"]={}
    assert activation_errors(graph)
def test_unknown_event_retained_but_cannot_activate():
    proposal={"draft":{"name":"Future payroll","definition":GRAPH,"trigger_event":"payroll.money.sent"}}
    result=validate_proposal(json.dumps(proposal))
    assert result["draft"]["trigger_event"]=="payroll.money.sent"
    assert activation_errors(result["draft"]["definition"],result["draft"]["trigger_event"])
def test_sales_event_is_kept_by_designer():
    result=validate_proposal(json.dumps({"draft":{"name":"Sales follow-up","definition":GRAPH,"trigger_event":"sales.deal.won"}}))
    assert result["draft"]["trigger_event"]=="sales.deal.won"
def test_condition_needs_one_true_and_one_false_path():
    graph=copy.deepcopy(GRAPH);graph["nodes"][1]={"id":"ask","type":"condition","config":{}}
    assert activation_errors(graph)
    graph["nodes"].append({"id":"other","type":"end"});graph["edges"][1]["condition"]="true";graph["edges"].append({"from":"ask","to":"other","condition":"false"})
    assert not activation_errors(graph)
