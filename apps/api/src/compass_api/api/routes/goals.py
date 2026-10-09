"""Financial goals: the terms the user sets, and what the engine makes of them.

Only the terms are stored. Every projection is computed on request, so a goal can never
serve a stale forecast - and a forecast always says which contribution it assumed and
where that figure came from.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from compass_api.api.deps import CurrentUserId, SessionDep
from compass_api.db.models import FinancialGoal
from compass_api.domain.goals import (
    GoalGap,
    GoalPath,
    GoalPathOption,
    GoalSimulation,
    GoalStatus,
    GoalTerms,
)
from compass_api.repositories.goals import GoalNameTakenError
from compass_api.services.goals import (
    ContributionSource,
    GoalChanges,
    GoalDraft,
    GoalForecast,
    GoalService,
    UnknownUserError,
)

router = APIRouter(prefix="/goals", tags=["goals"])

#: A yearly return above 100% is not a plan Compass should help model.
MAX_ANNUAL_RETURN_RATE = Decimal("1")

MAX_COMPARISON_OPTIONS = 6

ContributionQuery = Annotated[
    Decimal | None,
    Query(
        ge=0,
        description=(
            "Monthly contribution to assume. Defaults to the goal's own plan, or to the "
            "saving capacity measured from the user's history."
        ),
    ),
]
ReturnRateQuery = Annotated[
    Decimal,
    Query(
        ge=0,
        le=MAX_ANNUAL_RETURN_RATE,
        description=(
            "Expected effective annual return, as a fraction (0.11 for 11% a year). "
            "Compass does not know what any product pays, so this is always the "
            "caller's assumption."
        ),
    ),
]


# --- Responses -----------------------------------------------------------------------


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    target_amount: Decimal
    target_date: date | None
    initial_amount: Decimal
    current_amount: Decimal
    monthly_contribution: Decimal | None
    started_on: date
    status: GoalStatus


class GoalListResponse(BaseModel):
    items: list[GoalResponse]


class SimulationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monthly_contribution: Decimal
    annual_return_rate: Decimal
    #: Null when the target is not reached within the engine's horizon.
    months_to_target: int | None
    projected_completion: date | None
    projected_amount: Decimal
    total_contributed: Decimal
    total_return: Decimal
    is_feasible: bool


class GapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_date: date
    months_available: int
    required_monthly: Decimal
    planned_monthly: Decimal
    projected_amount: Decimal
    shortfall_total: Decimal
    shortfall_monthly: Decimal
    on_track: bool


class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    current_amount: Decimal
    target_amount: Decimal
    progress_share: Decimal
    expected_amount: Decimal | None
    ahead_by: Decimal | None
    on_track: bool | None


class ForecastResponse(BaseModel):
    goal: GoalResponse
    monthly_contribution: Decimal
    contribution_source: ContributionSource
    annual_return_rate: Decimal
    simulation: SimulationResponse
    gap: GapResponse | None
    progress: ProgressResponse

    @classmethod
    def of(cls, forecast: GoalForecast) -> ForecastResponse:
        return cls(
            goal=GoalResponse.model_validate(forecast.goal),
            monthly_contribution=forecast.monthly_contribution,
            contribution_source=forecast.contribution_source,
            annual_return_rate=forecast.annual_return_rate,
            simulation=_simulation(forecast.simulation),
            gap=_gap(forecast.gap),
            progress=ProgressResponse.model_validate(forecast.progress),
        )


def _simulation(simulation: GoalSimulation) -> SimulationResponse:
    return SimulationResponse.model_validate(simulation)


def _gap(gap: GoalGap | None) -> GapResponse | None:
    return GapResponse.model_validate(gap) if gap is not None else None


class PathResponse(BaseModel):
    label: str
    simulation: SimulationResponse


class ComparisonResponse(BaseModel):
    """Scenarios ordered by how soon the goal is reached, unreachable ones last."""

    goal_id: UUID
    paths: list[PathResponse]

    @classmethod
    def of(cls, goal_id: UUID, paths: tuple[GoalPath, ...]) -> ComparisonResponse:
        return cls(
            goal_id=goal_id,
            paths=[
                PathResponse(label=path.label, simulation=_simulation(path.simulation))
                for path in paths
            ],
        )


class DraftSimulationResponse(BaseModel):
    """A projection for a goal that has not been created."""

    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None
    monthly_contribution: Decimal
    contribution_source: ContributionSource
    simulation: SimulationResponse
    gap: GapResponse | None


# --- Requests ------------------------------------------------------------------------


class GoalCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0)
    target_date: date | None = None
    initial_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    monthly_contribution: Decimal | None = Field(default=None, ge=0)
    started_on: date | None = None

    @model_validator(mode="after")
    def check_dates(self) -> GoalCreateRequest:
        start = self.started_on or date.today()
        if self.target_date is not None and self.target_date <= start:
            raise ValueError("target_date must be after the goal starts")
        return self


class GoalUpdateRequest(BaseModel):
    """Every field optional: what is absent is left as it is."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Decimal | None = Field(default=None, gt=0)
    target_date: date | None = None
    current_amount: Decimal | None = Field(default=None, ge=0)
    monthly_contribution: Decimal | None = Field(default=None, ge=0)
    status: GoalStatus | None = None


class PathOptionRequest(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    monthly_contribution: Decimal = Field(ge=0)
    annual_return_rate: Decimal = Field(default=Decimal("0"), ge=0, le=MAX_ANNUAL_RETURN_RATE)


class ComparisonRequest(BaseModel):
    options: list[PathOptionRequest] = Field(min_length=1, max_length=MAX_COMPARISON_OPTIONS)


class DraftSimulationRequest(BaseModel):
    """ "Could I do this?" - asked before any goal exists."""

    target_amount: Decimal = Field(gt=0)
    current_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    target_date: date | None = None
    monthly_contribution: Decimal | None = Field(default=None, ge=0)
    annual_return_rate: Decimal = Field(default=Decimal("0"), ge=0, le=MAX_ANNUAL_RETURN_RATE)

    @model_validator(mode="after")
    def check_target_date(self) -> DraftSimulationRequest:
        if self.target_date is not None and self.target_date <= date.today():
            raise ValueError("target_date must be in the future")
        return self


# --- Routes --------------------------------------------------------------------------

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "No such goal for this user"}
}


async def _require_goal(service: GoalService, user_id: UUID, goal_id: UUID) -> FinancialGoal:
    goal = await service.get(user_id, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No such user"},
        status.HTTP_409_CONFLICT: {"description": "The user already has a goal with that name"},
    },
)
async def create_goal(
    request: GoalCreateRequest, user_id: CurrentUserId, session: SessionDep
) -> GoalResponse:
    service = GoalService(session)
    draft = GoalDraft(
        name=request.name,
        target_amount=request.target_amount,
        target_date=request.target_date,
        initial_amount=request.initial_amount,
        monthly_contribution=request.monthly_contribution,
        started_on=request.started_on,
    )
    try:
        goal = await service.create(user_id, draft)
    except UnknownUserError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from error
    except GoalNameTakenError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A goal with that name already exists"
        ) from error
    return GoalResponse.model_validate(goal)


@router.get("", summary="List the user's goals")
async def list_goals(user_id: CurrentUserId, session: SessionDep) -> GoalListResponse:
    goals = await GoalService(session).list(user_id)
    return GoalListResponse(items=[GoalResponse.model_validate(goal) for goal in goals])


@router.post("/simulate", summary="Simulate a goal without creating it")
async def simulate_draft(
    request: DraftSimulationRequest, user_id: CurrentUserId, session: SessionDep
) -> DraftSimulationResponse:
    """Answers the first question a user asks, before committing to anything."""
    terms = GoalTerms(
        target_amount=request.target_amount,
        current_amount=request.current_amount,
        started_on=date.today(),
        target_date=request.target_date,
        initial_amount=request.current_amount,
    )
    contribution, source, simulation, gap = await GoalService(session).simulate_draft(
        user_id,
        terms,
        monthly_contribution=request.monthly_contribution,
        annual_return_rate=request.annual_return_rate,
    )
    return DraftSimulationResponse(
        target_amount=request.target_amount,
        current_amount=request.current_amount,
        target_date=request.target_date,
        monthly_contribution=contribution,
        contribution_source=source,
        simulation=_simulation(simulation),
        gap=_gap(gap),
    )


@router.get("/{goal_id}", summary="Get one goal", responses=NOT_FOUND)
async def get_goal(goal_id: UUID, user_id: CurrentUserId, session: SessionDep) -> GoalResponse:
    goal = await _require_goal(GoalService(session), user_id, goal_id)
    return GoalResponse.model_validate(goal)


@router.patch("/{goal_id}", summary="Update a goal or record progress", responses=NOT_FOUND)
async def update_goal(
    goal_id: UUID, request: GoalUpdateRequest, user_id: CurrentUserId, session: SessionDep
) -> GoalResponse:
    """A goal whose balance reaches its target is marked achieved automatically."""
    changes = GoalChanges(
        name=request.name,
        target_amount=request.target_amount,
        target_date=request.target_date,
        current_amount=request.current_amount,
        monthly_contribution=request.monthly_contribution,
        status=request.status,
    )
    goal = await GoalService(session).update(user_id, goal_id, changes)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return GoalResponse.model_validate(goal)


@router.get(
    "/{goal_id}/forecast", summary="Simulate, measure the gap, report progress", responses=NOT_FOUND
)
async def get_forecast(
    goal_id: UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    monthly_contribution: ContributionQuery = None,
    annual_return_rate: ReturnRateQuery = Decimal("0"),
) -> ForecastResponse:
    service = GoalService(session)
    goal = await _require_goal(service, user_id, goal_id)
    forecast = await service.forecast(
        user_id,
        goal,
        monthly_contribution=monthly_contribution,
        annual_return_rate=annual_return_rate,
    )
    return ForecastResponse.of(forecast)


@router.post(
    "/{goal_id}/comparison",
    summary="Compare contribution and return scenarios",
    responses=NOT_FOUND,
)
async def compare_paths(
    goal_id: UUID, request: ComparisonRequest, user_id: CurrentUserId, session: SessionDep
) -> ComparisonResponse:
    service = GoalService(session)
    goal = await _require_goal(service, user_id, goal_id)
    options = [
        GoalPathOption(
            label=option.label,
            monthly_contribution=option.monthly_contribution,
            annual_return_rate=option.annual_return_rate,
        )
        for option in request.options
    ]
    return ComparisonResponse.of(goal.id, await service.compare(goal, options))
