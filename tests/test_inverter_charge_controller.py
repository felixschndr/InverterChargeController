from unittest.mock import Mock, patch

import pytest

from source.inverter_charge_controller import InverterChargeController


@pytest.fixture
def controller_stub() -> Mock:
    return Mock()


@pytest.fixture(autouse=True)
def do_not_wait_between_retries():
    with patch("source.inverter_charge_controller.pause.seconds") as patched_pause:
        yield patched_pause


def test_retry_returns_the_result_of_the_function_on_the_first_attempt(controller_stub):
    always_succeeding_function = Mock(return_value="the result")

    result = InverterChargeController.retry(controller_stub, always_succeeding_function, "an argument", a_keyword=1)

    assert result == "the result"
    always_succeeding_function.assert_called_once_with("an argument", a_keyword=1)


def test_retry_returns_the_result_once_a_transient_exception_stops_occurring(controller_stub):
    eventually_succeeding_function = Mock(side_effect=[TimeoutError, TimeoutError, "the result"])

    result = InverterChargeController.retry(controller_stub, eventually_succeeding_function, retries=5)

    assert result == "the result"
    assert eventually_succeeding_function.call_count == 3


def test_retry_reraises_the_last_exception_after_exhausting_all_attempts(controller_stub):
    always_failing_function = Mock(side_effect=TimeoutError("the external system is unreachable"))

    with pytest.raises(TimeoutError, match="the external system is unreachable"):
        InverterChargeController.retry(controller_stub, always_failing_function, retries=3)

    assert always_failing_function.call_count == 3
    controller_stub.log.critical.assert_called_once()


def test_retry_waits_between_attempts_but_not_after_the_last_one(controller_stub, do_not_wait_between_retries):
    always_failing_function = Mock(side_effect=TimeoutError)

    with pytest.raises(TimeoutError):
        InverterChargeController.retry(controller_stub, always_failing_function, retries=3)

    assert do_not_wait_between_retries.call_count == 2


def test_retry_does_not_catch_an_exception_outside_of_the_configured_ones(controller_stub):
    function_raising_an_unexpected_exception = Mock(side_effect=KeyError("an unexpected key"))

    with pytest.raises(KeyError):
        InverterChargeController.retry(controller_stub, function_raising_an_unexpected_exception, retries=3)

    function_raising_an_unexpected_exception.assert_called_once()


def test_start_reraises_unexpected_exceptions_instead_of_calling_sys_exit(controller_stub):
    controller_stub.retry.side_effect = RuntimeError("the tibber api is down")

    with pytest.raises(RuntimeError, match="the tibber api is down"):
        InverterChargeController.start(controller_stub)

    controller_stub.log.critical.assert_called_once()
