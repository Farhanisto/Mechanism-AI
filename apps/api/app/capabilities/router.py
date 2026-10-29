"""Capability routing: match a structured request to registered capabilities.

The router answers four questions (PRD §6 Step 4): which capability handles the
request, which operations are supported, which requirements are only partially
supported, and which required checks cannot currently be performed. The
assessment is recorded on the brief and in the evidence bundle, and unresolved
required checks block a pass.
"""

from app.capabilities.registry import CapabilityRegistry, default_registry
from app.mechanism.schemas import (
    CapabilityAssessment,
    CapabilitySupport,
    NormalizedBrief,
)

DEMAND_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "structural_strength",
        ("load", "loads", "force", "forces", "weight", "torque", "stress", "strength", "pressure"),
    ),
    ("thermal", ("temperature", "heat", "thermal")),
    ("dynamics", ("vibration", "frequency", "resonance")),
    (
        "safety_certification",
        (
            "helmet",
            "protective",
            "safety",
            "crash",
            "impact",
            "certif",
            "ppe",
            "child seat",
            "medical",
        ),
    ),
)

_SCOPE_WAIVER_QUESTION_ID = "verification_scope"


def detected_demand_categories(prompt: str) -> list[str]:
    lowered = prompt.lower()
    return [
        check
        for check, terms in DEMAND_CATEGORIES
        if any(term in lowered for term in terms)
    ]


def route_request(
    prompt: str,
    brief: NormalizedBrief | None = None,
    *,
    capability_id: str | None = None,
    requested_checks: tuple[str, ...] = (),
    clarification_answers: dict[str, str],
    registry: CapabilityRegistry | None = None,
) -> CapabilityAssessment:
    """Route a request and report what is supported, partial and unsupported."""
    registry = registry or default_registry()
    entry = (
        registry.get(capability_id)
        if capability_id is not None
        else registry.match_domain(prompt)
    )
    if entry is None:
        return CapabilityAssessment(
            capability_id="none",
            capability_version="0.0.0",
            status=CapabilitySupport.NOT_SUPPORTED,
            unsupported_requirements=[
                "the complete request - no registered capability matches the design domain"
            ],
            unavailable_checks=[],
        )

    unsupported_requirements: list[str] = []
    unavailable_checks: list[str] = []

    demanded = detected_demand_categories(prompt)
    waived = clarification_answers.get(_SCOPE_WAIVER_QUESTION_ID) == "yes"
    for check in demanded:
        if waived:
            unsupported_requirements.append(
                f"{check} (not evaluated - user confirmed kinematic-only scope)"
            )
        else:
            unavailable_checks.append(check)

    required_checks = list(requested_checks)
    if brief is not None:
        required_checks.extend(brief.requested_checks)
        required_checks.extend(brief.evaluator_config)
    for key in dict.fromkeys(required_checks):
        if key not in entry.evaluation_checks:
            unavailable_checks.append(key)

    if not entry.is_selectable():
        return CapabilityAssessment(
            capability_id=entry.capability_id,
            capability_version=entry.version,
            status=CapabilitySupport.NOT_SUPPORTED,
            unsupported_requirements=[
                f"{entry.capability_id} is not validated (test status: {entry.test_status})"
            ],
            unavailable_checks=[],
        )

    if unavailable_checks:
        status = CapabilitySupport.PARTIAL
    elif unsupported_requirements:
        status = CapabilitySupport.PARTIAL
    else:
        status = CapabilitySupport.SUPPORTED

    return CapabilityAssessment(
        capability_id=entry.capability_id,
        capability_version=entry.version,
        status=status,
        unsupported_requirements=unsupported_requirements,
        unavailable_checks=unavailable_checks,
    )


__all__ = [
    "DEMAND_CATEGORIES",
    "CapabilityAssessment",
    "detected_demand_categories",
    "route_request",
]
