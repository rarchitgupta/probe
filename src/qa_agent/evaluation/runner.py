from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from uuid import uuid4

from playwright.async_api import Page
from pydantic_ai.models import Model

from qa_agent.agent import AgentTask
from qa_agent.evaluation.grading import OutcomeGrade, grade_page
from qa_agent.evaluation.models import (
    BenchmarkMetrics,
    BenchmarkResult,
    EvaluationCase,
    EvaluationSuite,
    TrialResult,
    TrialVerdict,
)
from qa_agent.failures import FailureCategory
from qa_agent.runner import AGENT_EXECUTION_POLICY, AgentTaskResult, execute_agent_task


async def run_trial(
    case: EvaluationCase,
    *,
    trial_number: int = 1,
    model: Model | None = None,
    artifact_root: Path = Path(".eval-runs"),
    grader_timeout_ms: float = 5_000,
) -> TrialResult:
    outcome: OutcomeGrade | None = None

    async def grade_final_page(page: Page) -> None:
        nonlocal outcome
        outcome = await grade_page(page, case.checks, timeout_ms=grader_timeout_ms)

    trial_id = f"{case.id}-{trial_number}-{uuid4().hex[:8]}"
    result = await execute_agent_task(
        AgentTask(task_id=trial_id, start_url=case.start_url, goal=case.goal),
        model=model,
        policy=replace(
            AGENT_EXECUTION_POLICY,
            timeout_seconds=case.timeout_seconds,
        ),
        artifact_root=artifact_root,
        final_page_handler=grade_final_page,
    )
    return TrialResult(
        id=trial_id,
        case_id=case.id,
        trial_number=trial_number,
        agent_status=result.status,
        oracle_passed=outcome.passed if outcome else None,
        verdict=_verdict(result, outcome),
        checks=outcome.results if outcome else (),
        duration_ms=result.duration_ms,
        usage=result.usage,
        artifact_directory=result.artifact_directory,
        error=result.error,
        failure_category=result.failure_category,
        configuration=result.configuration,
    )


async def run_suite(
    suite: EvaluationSuite,
    *,
    trials_per_case: int = 1,
    model: Model | None = None,
    artifact_root: Path = Path(".eval-runs"),
    grader_timeout_ms: float = 5_000,
) -> BenchmarkResult:
    if trials_per_case < 1:
        raise ValueError("trials_per_case must be at least 1")

    results: list[TrialResult] = []
    for case in suite.cases:
        for trial_number in range(1, trials_per_case + 1):
            results.append(
                await run_trial(
                    case,
                    trial_number=trial_number,
                    model=model,
                    artifact_root=artifact_root,
                    grader_timeout_ms=grader_timeout_ms,
                )
            )
    return BenchmarkResult(
        suite_name=suite.name,
        suite_version=suite.version,
        trials_per_case=trials_per_case,
        trials=results,
        metrics=summarize_trials(tuple(results)),
    )


def summarize_trials(trials: tuple[TrialResult, ...]) -> BenchmarkMetrics:
    if not trials:
        raise ValueError("At least one trial is required")

    verdict_counts: dict[TrialVerdict, int] = {
        verdict: 0
        for verdict in (
            "true_pass",
            "false_pass",
            "false_failure",
            "failed",
            "blocked",
            "timeout",
            "infrastructure_error",
        )
    }
    for trial in trials:
        verdict_counts[trial.verdict] += 1

    durations = sorted(
        duration for trial in trials if (duration := trial.duration_ms) is not None
    )
    total = len(trials)
    costs = [_usage_decimal(trial, "cost") for trial in trials]
    total_cost = sum(costs, start=Decimal())
    return BenchmarkMetrics(
        total_trials=total,
        verdict_counts=verdict_counts,
        success_rate=verdict_counts["true_pass"] / total,
        false_pass_rate=verdict_counts["false_pass"] / total,
        median_duration_ms=median(durations) if durations else None,
        p95_duration_ms=durations[max(0, (95 * len(durations) + 99) // 100 - 1)]
        if durations
        else None,
        average_requests=mean(_usage_number(trial, "requests") for trial in trials),
        average_input_tokens=mean(
            _usage_number(trial, "input_tokens") for trial in trials
        ),
        average_output_tokens=mean(
            _usage_number(trial, "output_tokens") for trial in trials
        ),
        average_cache_read_tokens=mean(
            _usage_number(trial, "cache_read_tokens") for trial in trials
        ),
        total_cost=total_cost,
        average_cost=total_cost / total,
    )


def _usage_number(trial: TrialResult, key: str) -> float:
    value = trial.usage.get(key, 0)
    return float(value) if isinstance(value, int | float | str) else 0


def _usage_decimal(trial: TrialResult, key: str) -> Decimal:
    value = trial.usage.get(key, 0)
    return Decimal(str(value)) if isinstance(value, int | float | str) else Decimal()


def _verdict(result: AgentTaskResult, outcome: OutcomeGrade | None) -> TrialVerdict:
    if result.failure_category in {
        FailureCategory.MODEL_TIMEOUT,
        FailureCategory.EXECUTION_TIMEOUT,
    }:
        return "timeout"
    if result.error:
        return "infrastructure_error"
    if outcome and outcome.passed:
        return "true_pass" if result.status == "passed" else "false_failure"
    if result.status == "passed":
        return "false_pass"
    if result.status == "blocked":
        return "blocked"
    if result.status == "error":
        return "infrastructure_error"
    return "failed"
