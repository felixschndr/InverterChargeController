from datetime import timedelta

import goodwe
from environment_variable_getter import EnvironmentVariableGetter
from goodwe.et import OperationMode
from logger import LoggerMixin


class Inverter(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.device = None

        self.hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")

        self.battery_capacity = int(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CAPACITY")
        )
        self.charging_amperage_cc_phase = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE")
        )
        self.charging_amperage_cv_phase = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE")
        )
        self.cc_phase_limit = int(
            EnvironmentVariableGetter.get(
                "INVERTER_BATTERY_CHARGING_CC_PHASE_LIMIT", 80
            )
        )
        self.charging_voltage = int(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_VOLTAGE")
        )
        self.charging_efficiency = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_EFFICIENCY", 0.9),
        )

        self.dry_run = EnvironmentVariableGetter.get(
            name_of_variable="DRY_RUN", default_value=True
        )

    async def connect(self) -> None:
        self.log.debug(f"Connecting to inverter on {self.hostname}...")
        self.device = await goodwe.connect(self.hostname)
        self.log.info("Successfully connected to inverter")

    async def get_operation_mode(self) -> OperationMode:
        if self.device is None:
            await self.connect()

        self.log.debug("Getting current operation mode...")
        operation_mode = await self.device.get_operation_mode()
        self.log.info(f"Current Operation mode is {operation_mode.name}")
        return operation_mode

    async def set_operation_mode(self, mode: OperationMode) -> None:
        if self.dry_run:
            self.log.info(
                f"Would set the inverter to {mode.name} but dry run is enabled"
            )
            return

        if self.device is None:
            await self.connect()

        self.log.debug(f"Setting new operation mode: {mode.name}...")
        await self.device.set_operation_mode(mode)

        current_operation_mode = await self.get_operation_mode()
        if current_operation_mode != mode:
            raise RuntimeError(
                f"Setting the Operation mode was not successful: Expected {mode.name}, Actual: {current_operation_mode.name}"
            )

        self.log.info(f"Successfully set new operation mode {mode.name}")

    def calculate_necessary_duration_to_charge(
        self, current_state_of_charge: int
    ) -> timedelta:
        """
        This function calculates the necessary duration to fully charge the battery.

        Charging a battery can be divided into two phases:
        1. The "Constant Current Phase" (CC phase):
            This phase is the first phase and goes roughly from 0% - 80% state of charge. In this phase the battery
            charges the fastest. In the CC phase the charging speed is roughly linear.
        2. The "Constant Voltage Phase" (CV phase):
            This phase is the second phase and goes roughly from 80% - 100% state of charge. In this phase the battery
            charges slower. In the CC phase the charging speed is not linear but exponentially slower. The exponential
            factor can be approximated by dividing the charging power of this phase by 2.
        To get the total duration necessary, the durations of the individual phases are calculated and summed.

        Args:
            current_state_of_charge: Current percentage of battery charge.

        Returns:
            timedelta: The total duration required to fully charge the battery from the given state of charge.

        """

        charging_efficiency_factor = 1 + (1 - self.charging_efficiency)

        self.log.info(
            f"Calculating necessary duration to charge from {current_state_of_charge}% to 100%..."
        )
        duration_to_charge_in_cc_phase = self._calculate_cc_phase_charging_duration(
            current_state_of_charge, charging_efficiency_factor
        )
        self.log.debug(
            f"Necessary charging duration in CC-Phase: {duration_to_charge_in_cc_phase}"
        )

        duration_to_charge_in_cv_phase = self._calculate_cv_phase_charging_duration(
            current_state_of_charge, charging_efficiency_factor
        )
        self.log.debug(
            f"Necessary charging duration in CV-Phase: {duration_to_charge_in_cv_phase}"
        )

        total_duration_to_charge = (
            duration_to_charge_in_cc_phase + duration_to_charge_in_cv_phase
        )
        self.log.info(f"Calculated duration to charge: {total_duration_to_charge}")

        return total_duration_to_charge

    def _calculate_cc_phase_charging_duration(
        self, state_of_charge: int, charging_efficiency_factor: float
    ) -> timedelta:
        """
        Args:
            state_of_charge: Current state of charge of the battery in percentage.
            charging_efficiency_factor: Efficiency factor of the charging process.

        Returns:
            Time duration required to charge the battery during constant current phase (CC phase) as a timedelta object.
        """
        if state_of_charge > self.cc_phase_limit:
            return timedelta()

        energy_to_charge_in_cc_phase = (
            (self.cc_phase_limit - state_of_charge) / 100 * self.battery_capacity
        )
        charging_power = self.charging_voltage * self.charging_amperage_cc_phase
        duration_to_charge_in_cc_phase = energy_to_charge_in_cc_phase / charging_power

        return timedelta(
            hours=duration_to_charge_in_cc_phase * charging_efficiency_factor
        )

    def _calculate_cv_phase_charging_duration(
        self, state_of_charge: int, charging_efficiency_factor: float
    ) -> timedelta:
        """
        Args:
            state_of_charge: Current state of charge of the battery in percentage.
            charging_efficiency_factor: Efficiency factor of the charging process.

        Returns:
            Time duration required to charge the battery during constant voltage phase (CV phase) as a timedelta object.
        """
        energy_to_charge_in_cv_phase = (
            (100 - max(state_of_charge, self.cc_phase_limit))
            / 100
            * self.battery_capacity
        )
        charging_power = self.charging_voltage * self.charging_amperage_cv_phase / 2
        duration_to_charge_in_cv_phase = energy_to_charge_in_cv_phase / charging_power

        return timedelta(
            hours=duration_to_charge_in_cv_phase * charging_efficiency_factor
        )

    def calculate_energy_missing_from_battery_from_state_of_charge(
        self, state_of_charge: int
    ) -> int:
        """
        Calculates the amount of energy missing in the battery in watt-hours from the state of charge

        Args:
            state_of_charge: The current state of charge of the battery as a percentage.

        Returns:
            The energy missing in watt-hours corresponding to the given state of charge.
        """
        return (
            self.battery_capacity
            - self.calculate_energy_saved_in_battery_from_state_of_charge(
                state_of_charge
            )
        )

    def calculate_energy_saved_in_battery_from_state_of_charge(
        self, state_of_charge: int
    ) -> int:
        """
        Calculates the amount of energy saved in the battery in watt-hours from the state of charge

        Args:
            state_of_charge: The current state of charge of the battery as a percentage.

        Returns:
            The energy saved in watt-hours corresponding to the given state of charge.
        """
        return int(self.battery_capacity * state_of_charge / 100)
