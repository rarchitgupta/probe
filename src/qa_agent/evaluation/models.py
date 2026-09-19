from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from qa_agent.agent.assertions import AssertionResult, PageAssertion
from qa_agent.configuration import AgentConfiguration
from qa_agent.failures import FailureCategory


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


OutcomeCheck = Annotated[
    PageAssertion,
    Field(discriminator="assertion"),
]
TrialVerdict = Literal[
    "true_pass",
    "false_pass",
    "false_failure",
    "failed",
    "blocked",
    "timeout",
    "infrastructure_error",
]


class EvaluationCase(EvaluationModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    start_url: HttpUrl
    goal: str = Field(min_length=1)
    tags: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    checks: tuple[OutcomeCheck, ...] = Field(min_length=1)


class EvaluationSuite(EvaluationModel):
    name: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    cases: tuple[EvaluationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> EvaluationSuite:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Evaluation case IDs must be unique")
        return self


class TrialResult(EvaluationModel):
    id: str
    case_id: str
    trial_number: int = Field(ge=1)
    agent_status: Literal["passed", "failed", "blocked", "error"]
    oracle_passed: bool | None
    verdict: TrialVerdict
    checks: tuple[AssertionResult, ...]
    duration_ms: int | None
    usage: dict[str, object]
    artifact_directory: str
    error: str | None
    failure_category: FailureCategory | None = None
    configuration: AgentConfiguration | None = None


class BenchmarkMetrics(EvaluationModel):
    total_trials: int = Field(ge=1)
    verdict_counts: dict[TrialVerdict, int]
    success_rate: float = Field(ge=0, le=1)
    false_pass_rate: float = Field(ge=0, le=1)
    median_duration_ms: float | None
    p95_duration_ms: int | None
    average_requests: float
    average_input_tokens: float
    average_output_tokens: float
    average_cache_read_tokens: float
    total_cost: Decimal
    average_cost: Decimal


class BenchmarkResult(EvaluationModel):
    suite_name: str
    suite_version: int
    trials_per_case: int = Field(ge=1)
    trials: tuple[TrialResult, ...]
    metrics: BenchmarkMetrics


class ReportMetadata(EvaluationModel):
    generated_at: datetime
    model: str
    prompt_version: str
    model_config_version: str
    probe_version: str
    playwright_version: str
    python_version: str
    platform: str
    git_commit: str | None


class BenchmarkReport(EvaluationModel):
    schema_version: Literal[2] = 2
    metadata: ReportMetadata
    suite: EvaluationSuite
    result: BenchmarkResult


class BenchmarkDeltas(EvaluationModel):
    verdict_counts: dict[TrialVerdict, int]
    success_rate: float
    false_pass_rate: float
    median_duration_ms: float | None
    p95_duration_ms: int | None
    average_requests: float
    average_input_tokens: float
    average_output_tokens: float
    average_cache_read_tokens: float
    average_cost: Decimal


class BenchmarkComparison(EvaluationModel):
    schema_version: Literal[1] = 1
    suite_name: str
    suite_version: int
    baseline_model: str
    candidate_model: str
    baseline_prompt_version: str
    candidate_prompt_version: str
    baseline_model_config_version: str
    candidate_model_config_version: str
    baseline_commit: str | None
    candidate_commit: str | None
    quality_regressed: bool
    deltas: BenchmarkDeltas


def load_evaluation_suite(path: Path) -> EvaluationSuite:
    return EvaluationSuite.model_validate_json(path.read_text(encoding="utf-8"))
