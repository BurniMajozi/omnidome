"""The Agent Manager must list every agent that can actually run.

OmniAssist ("assistant") runs all three lead-warming flows and MetricBot/StaffBot
are reached through orchestrator_consult_specialist, but GET /api/agents only
returned the five MCP agents, so their runs and flows showed up nowhere.

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.llm import SYSTEM_PROMPTS  # noqa: E402
from services.agent_orchestrator.routes.agents import PROMPT_ALIASES, list_builtin_agents  # noqa: E402


def test_every_agent_with_a_system_prompt_is_listed():
    # "auto" (Master Orchestrator) runs as an agent on the AG-UI/A2A paths;
    # "orchestrator" is the same agent under another name, listed once.
    listed = {a.agent_type for a in list_builtin_agents()}
    assert listed == set(SYSTEM_PROMPTS) - set(PROMPT_ALIASES)
    assert "auto" in listed


def test_listed_agents_carry_policies_and_a_named_description():
    for agent in list_builtin_agents():
        assert agent.description and " — " in agent.description, agent.agent_type
        assert len(agent.tool_policies) == len(agent.tools), agent.agent_type
