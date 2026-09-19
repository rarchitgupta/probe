from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class QARunWorkflow:
    @workflow.run
    async def run(self, run_id: str) -> str:
        return await workflow.execute_activity(
            "execute_qa_run",
            run_id,
            result_type=str,
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
