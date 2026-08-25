from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from qa_agent.evaluation.models import (
    BenchmarkComparison,
    BenchmarkDeltas,
    BenchmarkReport,
    BenchmarkResult,
    EvaluationSuite,
    ReportMetadata,
)


def load_report(path: Path) -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))


def compare_reports(
    baseline: BenchmarkReport, candidate: BenchmarkReport
) -> BenchmarkComparison:
    if baseline.suite != candidate.suite:
        raise ValueError("Benchmark reports must contain the same evaluation suite")

    baseline_metrics = baseline.result.metrics
    candidate_metrics = candidate.result.metrics
    success_rate_delta = candidate_metrics.success_rate - baseline_metrics.success_rate
    false_pass_rate_delta = (
        candidate_metrics.false_pass_rate - baseline_metrics.false_pass_rate
    )
    return BenchmarkComparison(
        suite_name=candidate.suite.name,
        suite_version=candidate.suite.version,
        baseline_model=baseline.metadata.model,
        candidate_model=candidate.metadata.model,
        baseline_commit=baseline.metadata.git_commit,
        candidate_commit=candidate.metadata.git_commit,
        quality_regressed=success_rate_delta < 0 or false_pass_rate_delta > 0,
        deltas=BenchmarkDeltas(
            verdict_counts={
                verdict: candidate_metrics.verdict_counts.get(verdict, 0)
                - baseline_metrics.verdict_counts.get(verdict, 0)
                for verdict in baseline_metrics.verdict_counts
            },
            success_rate=success_rate_delta,
            false_pass_rate=false_pass_rate_delta,
            median_duration_ms=_optional_delta(
                baseline_metrics.median_duration_ms,
                candidate_metrics.median_duration_ms,
            ),
            p95_duration_ms=_optional_delta(
                baseline_metrics.p95_duration_ms,
                candidate_metrics.p95_duration_ms,
            ),
            average_requests=(
                candidate_metrics.average_requests - baseline_metrics.average_requests
            ),
            average_input_tokens=(
                candidate_metrics.average_input_tokens
                - baseline_metrics.average_input_tokens
            ),
            average_output_tokens=(
                candidate_metrics.average_output_tokens
                - baseline_metrics.average_output_tokens
            ),
            average_cache_read_tokens=(
                candidate_metrics.average_cache_read_tokens
                - baseline_metrics.average_cache_read_tokens
            ),
            average_cost=(
                candidate_metrics.average_cost - baseline_metrics.average_cost
            ),
        ),
    )


def write_report(
    result: BenchmarkResult,
    suite: EvaluationSuite,
    path: Path,
    *,
    model_name: str,
    git_commit: str | None = None,
) -> Path:
    report = BenchmarkReport(
        metadata=ReportMetadata(
            generated_at=datetime.now(UTC),
            model=model_name,
            probe_version=version("probe"),
            playwright_version=version("playwright"),
            python_version=platform.python_version(),
            platform=platform.platform(),
            git_commit=git_commit or _git_commit(),
        ),
        suite=suite,
        result=result,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    temporary_path.replace(path)
    return path


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        timeout=2,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _optional_delta(
    baseline: float | int | None, candidate: float | int | None
) -> float | int | None:
    return (
        candidate - baseline if baseline is not None and candidate is not None else None
    )
