from collections import deque

import pytest

from qa_agent.agent.loop import Transition, repetition_feedback


def test_repetition_warns_only_for_ineffective_actions_on_current_state():
    click = (("click", "Open product"),)
    history = deque([Transition("catalog", "product", click)], maxlen=8)
    assert repetition_feedback(history, "catalog") is None
    history.extend([Transition("catalog", "catalog", click)] * 2)
    assert repetition_feedback(history, "catalog") is not None
    assert repetition_feedback(history, "product") is None


@pytest.mark.parametrize(
    "repetitions,severity",
    [(5, "Possible loop"), (8, "Repeated loop"), (12, "Persistent repetition")],
)
def test_scroll_repetition_warns_despite_page_changes(repetitions, severity):
    history = deque(maxlen=20)
    for index in range(repetitions):
        history.append(Transition(str(index), str(index + 1), (("scroll", "down"),)))
    feedback = repetition_feedback(history, "different-page")
    assert feedback is not None and severity in feedback


def test_alternating_scrolls_warn_and_old_actions_expire():
    history = deque(maxlen=20)
    for _ in range(5):
        history.extend(
            [
                Transition("top", "bottom", (("scroll", "down"),)),
                Transition("bottom", "top", (("scroll", "up"),)),
            ]
        )
    feedback = repetition_feedback(history, "top")
    assert feedback is not None and "5 times" in feedback
    for index in range(20):
        history.append(
            Transition(str(index), str(index + 1), (("click", f"Product {index}"),))
        )
    assert repetition_feedback(history, "top") is None


def test_waits_do_not_trigger_action_repetition():
    history = deque(
        [Transition(str(i), str(i + 1), (("wait", None),)) for i in range(20)]
    )
    assert repetition_feedback(history, "other") is None
