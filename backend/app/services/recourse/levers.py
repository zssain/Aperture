"""The recourse lever registry - an explicit allow-list of ACTIONABLE levers.

A lever cannot be searched unless it is registered here, and registration REFUSES any lever
that targets a protected attribute or a non-actionable input. That is how protected and
immutable attributes are excluded by construction, not by reviewer vigilance: the only way to
suggest changing something is to register a lever for it, and the registry will not let you
register one for age, gender, or anything else the applicant cannot (or must not) act on.
"""

from dataclasses import dataclass

from app.registries.fairness_attributes import FAIRNESS_ATTRIBUTES

# The only inputs a lever is permitted to move. Everything else - including every protected
# attribute and the risk/manipulation signals themselves - is refused at registration.
ACTIONABLE_TARGETS: frozenset[str] = frozenset(
    {
        "coverage_score",  # ADD_SOURCE / EXTEND_HISTORY improve evidence coverage
        "requested_amount",  # REDUCE_AMOUNT lowers the ask
        "offer_band",  # ACCEPT_STARTER offers a lower band the applicant can accept
    }
)

# Attributes an applicant can never be asked to change (belt-and-braces alongside the
# ACTIONABLE_TARGETS allow-list; both must pass).
PROTECTED_TARGETS: frozenset[str] = FAIRNESS_ATTRIBUTES | frozenset(
    {"pd", "manipulation_band", "age", "gender", "religion", "caste", "marital_status"}
)


class LeverRegistrationError(Exception):
    """A lever targets a protected or non-actionable attribute and must not be registered."""


@dataclass(frozen=True)
class Lever:
    name: str
    target: str
    # Lower effort_rank = easier for the applicant; used to order the returned options.
    effort_rank: int


_REGISTRY: dict[str, Lever] = {}


def register_lever(lever: Lever) -> Lever:
    if lever.target in PROTECTED_TARGETS:
        raise LeverRegistrationError(
            f"lever {lever.name!r} targets protected attribute {lever.target!r}"
        )
    if lever.target not in ACTIONABLE_TARGETS:
        raise LeverRegistrationError(
            f"lever {lever.name!r} targets non-actionable input {lever.target!r}"
        )
    _REGISTRY[lever.name] = lever
    return lever


def registered_levers() -> tuple[Lever, ...]:
    return tuple(sorted(_REGISTRY.values(), key=lambda lever: lever.effort_rank))


def is_registered(name: str) -> bool:
    return name in _REGISTRY


# The four actionable levers, ordered by applicant effort (easiest first).
ACCEPT_STARTER = register_lever(Lever("ACCEPT_STARTER", "offer_band", effort_rank=0))
REDUCE_AMOUNT = register_lever(Lever("REDUCE_AMOUNT", "requested_amount", effort_rank=1))
ADD_SOURCE = register_lever(Lever("ADD_SOURCE", "coverage_score", effort_rank=2))
EXTEND_HISTORY = register_lever(Lever("EXTEND_HISTORY", "coverage_score", effort_rank=3))
