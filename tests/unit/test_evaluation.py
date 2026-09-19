import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from qa_agent.agent.assertions import TextVisibleAssertion, UrlContainsAssertion
from qa_agent.evaluation.models import (
    BenchmarkReport,
    BenchmarkResult,
    EvaluationSuite,
    TrialResult,
    TrialVerdict,
    load_evaluation_suite,
)
from qa_agent.evaluation.reporting import compare_reports, load_report, write_report
from qa_agent.evaluation.runner import run_suite, summarize_trials


def _suite_data() -> dict[str, object]:
    return {
        "name": "smoke",
        "version": 1,
        "cases": [
            {
                "id": "login-success",
                "name": "Successful login",
                "start_url": "http://127.0.0.1:9000/login",
                "goal": "Log in and verify the dashboard",
                "tags": ["login", "forms"],
                "checks": [
                    {"assertion": "url_contains", "expected": "/dashboard"},
                    {
                        "assertion": "text_visible",
                        "expected": "Welcome back",
                        "exact": True,
                    },
                ],
            }
        ],
    }


def test_loads_versioned_suite_with_typed_checks(tmp_path) -> None:
    path = tmp_path / "smoke.json"
    path.write_text(json.dumps(_suite_data()), encoding="utf-8")

    suite = load_evaluation_suite(path)

    assert suite.name == "smoke"
    assert suite.version == 1
    assert isinstance(suite.cases[0].checks[0], UrlContainsAssertion)
    assert isinstance(suite.cases[0].checks[1], TextVisibleAssertion)


def test_rejects_duplicate_case_ids() -> None:
    data = _suite_data()
    cases = data["cases"]
    assert isinstance(cases, list)
    cases.append(cases[0])

    with pytest.raises(ValidationError, match="case IDs must be unique"):
        EvaluationSuite.model_validate(data)


def test_rejects_unknown_check_types() -> None:
    data = _suite_data()
    cases = data["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    case["checks"] = [{"assertion": "model_says_passed", "expected": True}]

    with pytest.raises(ValidationError):
        EvaluationSuite.model_validate(data)


def test_rejects_unknown_check_fields() -> None:
    data = _suite_data()
    cases = data["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    case["checks"] = [
        {"assertion": "url_contains", "expected": "/dashboard", "typo": True}
    ]

    with pytest.raises(ValidationError, match="Unexpected keyword argument"):
        EvaluationSuite.model_validate(data)


def test_repository_smoke_suite_is_valid() -> None:
    suite_path = Path(__file__).parents[2] / "evals/suites/saucedemo-smoke.json"

    suite = load_evaluation_suite(suite_path)

    assert suite.name == "saucedemo-smoke"
    assert [case.id for case in suite.cases] == [
        "login-success",
        "add-item-to-cart",
        "complete-checkout",
    ]


def _trial(number: int, verdict: TrialVerdict, duration_ms: int) -> TrialResult:
    return TrialResult.model_validate(
        {
            "id": f"trial-{number}",
            "case_id": "login-success",
            "trial_number": number,
            "agent_status": "passed",
            "oracle_passed": verdict == "true_pass",
            "verdict": verdict,
            "checks": [],
            "duration_ms": duration_ms,
            "usage": {
                "requests": number,
                "input_tokens": number * 100,
                "output_tokens": number * 10,
                "cache_read_tokens": number * 20,
                "cost": str(Decimal("0.001") * number),
            },
            "artifact_directory": f".eval-runs/trial-{number}",
            "error": None,
        }
    )


def _result(suite: EvaluationSuite, trials: tuple[TrialResult, ...]) -> BenchmarkResult:
    return BenchmarkResult(
        suite_name=suite.name,
        suite_version=suite.version,
        trials_per_case=len(trials),
        trials=trials,
        metrics=summarize_trials(trials),
    )


def test_summarizes_trials_using_hidden_verdicts() -> None:
    metrics = summarize_trials(
        (
            _trial(1, "true_pass", 100),
            _trial(2, "true_pass", 200),
            _trial(3, "false_pass", 900),
        )
    )

    assert metrics.total_trials == 3
    assert metrics.verdict_counts["true_pass"] == 2
    assert metrics.success_rate == pytest.approx(2 / 3)
    assert metrics.false_pass_rate == pytest.approx(1 / 3)
    assert metrics.median_duration_ms == 200
    assert metrics.p95_duration_ms == 900
    assert metrics.average_requests == 2
    assert metrics.total_cost == Decimal("0.006")
    assert metrics.average_cost == Decimal("0.002")


async def test_runs_every_case_for_each_requested_trial() -> None:
    suite = EvaluationSuite.model_validate(_suite_data())
    trial = _trial(1, "true_pass", 100)
    mocked_run_trial = AsyncMock(return_value=trial)

    with patch("qa_agent.evaluation.runner.run_trial", mocked_run_trial):
        result = await run_suite(suite, trials_per_case=3)

    assert len(result.trials) == 3
    assert result.metrics.total_trials == 3
    assert [
        call.kwargs["trial_number"] for call in mocked_run_trial.call_args_list
    ] == [
        1,
        2,
        3,
    ]


def test_writes_portable_json_report_atomically(tmp_path) -> None:
    suite = EvaluationSuite.model_validate(_suite_data())
    trials = (_trial(1, "true_pass", 100),)
    path = tmp_path / "benchmark.json"

    write_report(
        _result(suite, trials),
        suite,
        path,
        model_name="test-model",
        git_commit="abc123",
    )
    report = BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))

    assert report.schema_version == 2
    assert report.metadata.model == "test-model"
    assert report.metadata.prompt_version == "6"
    assert report.metadata.model_config_version == "2"
    assert report.metadata.git_commit == "abc123"
    assert report.suite.cases[0].goal == "Log in and verify the dashboard"
    assert report.result.metrics.success_rate == 1
    assert not path.with_suffix(".json.tmp").exists()


def test_compares_candidate_against_compatible_baseline(tmp_path) -> None:
    suite = EvaluationSuite.model_validate(_suite_data())
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_trials = tuple(
        _trial(number, "true_pass", number * 100) for number in range(1, 4)
    )
    candidate_trials = (
        _trial(1, "true_pass", 100),
        _trial(2, "true_pass", 200),
        _trial(3, "false_pass", 900),
    )
    write_report(
        _result(suite, baseline_trials),
        suite,
        baseline_path,
        model_name="baseline-model",
        git_commit="baseline-commit",
    )
    write_report(
        _result(suite, candidate_trials),
        suite,
        candidate_path,
        model_name="candidate-model",
        git_commit="candidate-commit",
    )

    comparison = compare_reports(
        load_report(baseline_path), load_report(candidate_path)
    )

    assert comparison.quality_regressed is True
    assert comparison.deltas.success_rate == pytest.approx(-1 / 3)
    assert comparison.deltas.false_pass_rate == pytest.approx(1 / 3)
    assert comparison.deltas.verdict_counts["true_pass"] == -1
    assert comparison.deltas.verdict_counts["false_pass"] == 1
    assert comparison.deltas.median_duration_ms == 0
    assert comparison.deltas.p95_duration_ms == 600
    assert comparison.baseline_commit == "baseline-commit"
    assert comparison.candidate_model == "candidate-model"
    assert comparison.baseline_prompt_version == "6"
    assert comparison.candidate_model_config_version == "2"


def test_rejects_comparison_between_different_suites(tmp_path) -> None:
    baseline_suite = EvaluationSuite.model_validate(_suite_data())
    candidate_suite = baseline_suite.model_copy(update={"version": 2})
    trial = (_trial(1, "true_pass", 100),)
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    write_report(
        _result(baseline_suite, trial),
        baseline_suite,
        baseline_path,
        model_name="test-model",
        git_commit="abc123",
    )
    write_report(
        _result(candidate_suite, trial),
        candidate_suite,
        candidate_path,
        model_name="test-model",
        git_commit="abc123",
    )

    with pytest.raises(ValueError, match="same evaluation suite"):
        compare_reports(load_report(baseline_path), load_report(candidate_path))
