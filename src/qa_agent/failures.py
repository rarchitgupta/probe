from enum import StrEnum


class FailureCategory(StrEnum):
    MODEL_TIMEOUT = "model_timeout"
    MODEL_ERROR = "model_error"
    EXECUTION_TIMEOUT = "execution_timeout"
    POLICY_VIOLATION = "policy_violation"
    BROWSER_ERROR = "browser_error"
    ASSERTION_FAILURE = "assertion_failure"
    ACTION_FAILURE = "action_failure"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
