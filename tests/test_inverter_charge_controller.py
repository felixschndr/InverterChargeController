from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from goodwe import InverterError, OperationMode

from source.energy_classes import StateOfCharge
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


@pytest.fixture
def charging_controller_stub(controller_stub) -> Mock:
    controller_stub.current_energy_rate.maximum_charging_duration = timedelta(hours=1)
    controller_stub.inverter.get_operation_mode.return_value = OperationMode.ECO_CHARGE
    controller_stub.inverter.get_state_of_charge.return_value = StateOfCharge.from_percentage(50)
    return controller_stub


def test_charge_inverter_sets_the_inverter_back_to_normal_mode_once_the_target_is_reached(charging_controller_stub):
    charging_controller_stub.inverter.get_state_of_charge.return_value = StateOfCharge.from_percentage(90)

    InverterChargeController._charge_inverter(charging_controller_stub, StateOfCharge.from_percentage(80))

    charging_controller_stub._set_operation_mode_back_to_general.assert_called_once()


def test_charge_inverter_sets_the_inverter_back_to_normal_mode_when_an_unexpected_exception_occurs(
    charging_controller_stub,
):
    charging_controller_stub.inverter.get_state_of_charge.side_effect = ValueError("the inverter returned garbage")

    with pytest.raises(ValueError):
        InverterChargeController._charge_inverter(charging_controller_stub, StateOfCharge.from_percentage(80))

    charging_controller_stub._set_operation_mode_back_to_general.assert_called_once()


def test_charge_inverter_sets_the_inverter_back_to_normal_mode_after_too_many_communication_errors(
    charging_controller_stub,
):
    charging_controller_stub.inverter.get_operation_mode.side_effect = InverterError

    InverterChargeController._charge_inverter(charging_controller_stub, StateOfCharge.from_percentage(80))

    assert charging_controller_stub.inverter.get_operation_mode.call_count == 3
    charging_controller_stub._set_operation_mode_back_to_general.assert_called_once()


def test_charge_inverter_leaves_the_operation_mode_alone_when_the_user_changed_it(charging_controller_stub):
    charging_controller_stub.inverter.get_operation_mode.return_value = OperationMode.GENERAL

    InverterChargeController._charge_inverter(charging_controller_stub, StateOfCharge.from_percentage(80))

    charging_controller_stub._set_operation_mode_back_to_general.assert_not_called()


@pytest.mark.parametrize("raised_exception", [InverterError, RuntimeError])
def test_set_operation_mode_back_to_general_swallows_a_failure_of_an_unresponsive_inverter(
    controller_stub, raised_exception
):
    controller_stub.inverter.set_operation_mode.side_effect = raised_exception

    InverterChargeController._set_operation_mode_back_to_general(controller_stub)

    controller_stub.log.error.assert_called_once()
