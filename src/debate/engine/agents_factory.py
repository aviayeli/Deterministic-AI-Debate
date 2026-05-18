"""Factory that constructs a topic-routed (PRO, CON) agent pair in one call."""
from ..agents.con import ConAgent
from ..agents.pro import ProAgent
from ..gatekeeper import ApiGatekeeper
from ..router import TopicRouter


def make_agents(gk: ApiGatekeeper, topic: str | None) -> tuple[ProAgent, ConAgent]:
    """Run the TopicRouter once, then build both agents with the selected skill hints."""
    skills = TopicRouter().route(topic or "")
    return (
        ProAgent(gk, topic=topic, extra_instructions=skills),
        ConAgent(gk, topic=topic, extra_instructions=skills),
    )
