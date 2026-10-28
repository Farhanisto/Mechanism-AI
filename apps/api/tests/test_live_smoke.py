"""Env-gated live smoke test for both Meta model parsers.

Skipped by default. Set MECHANISM_AI_LIVE_SMOKE=1 and MECHANISM_AI_META_API_KEY
to run these against the real provider.
"""

import os

import pytest
from app.ai.candidate_parser import generate_candidate
from app.ai.meta_client import build_meta_client
from app.ai.requirements_parser import parse_requirements
from app.config import get_settings
from app.mechanism.schemas import MechanismType

pytestmark = pytest.mark.skipif(
    os.environ.get("MECHANISM_AI_LIVE_SMOKE") != "1",
    reason="set MECHANISM_AI_LIVE_SMOKE=1 to run the live smoke test",
)

PROMPT = "Design a four-bar linkage with 100 mm of travel in a 200 mm footprint."


def _client_or_skip():
    settings = get_settings()
    if settings.meta_api_key is None:
        pytest.skip("MECHANISM_AI_META_API_KEY is not set")
    return build_meta_client(settings)


async def test_live_requirements_parsing() -> None:
    client = _client_or_skip()
    try:
        brief, completion = await parse_requirements(PROMPT, client=client)
    finally:
        await client.aclose()

    assert brief.mechanism_type is MechanismType.FOUR_BAR_LINKAGE
    assert brief.target_motion.travel_distance > 0
    assert completion.model
    assert completion.usage


async def test_live_candidate_generation() -> None:
    client = _client_or_skip()
    try:
        brief, _ = await parse_requirements(PROMPT, client=client)
        candidate, completion = await generate_candidate(
            brief,
            client=client,
            attempt_number=1,
            max_attempts=3,
        )
    finally:
        await client.aclose()

    assert candidate.parameters.ground_length > 0
    assert candidate.parameters.crank_length > 0
    assert candidate.parameters.coupler_length > 0
    assert candidate.parameters.rocker_length > 0
    assert completion.model
    assert completion.usage
