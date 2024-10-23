import goodwe
from energy_amount import EnergyAmount
from environment_variable_getter import EnvironmentVariableGetter
from goodwe.et import OperationMode
from logger import LoggerMixin


class Inverter(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.device = None

        self.hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")

        self.battery_capacity = EnergyAmount(float(EnvironmentVariableGetter.get("INVERTER_BATTERY_CAPACITY")))
        self.charging_amperage_cc_phase = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE")
        )
        self.charging_amperage_cv_phase = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE")
        )
        self.cc_phase_limit = int(EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_CC_PHASE_LIMIT", 80))
        self.charging_voltage = int(EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_VOLTAGE"))
        self.charging_efficiency = float(
            EnvironmentVariableGetter.get("INVERTER_BATTERY_CHARGING_EFFICIENCY", 0.9),
        )

        self.dry_run = EnvironmentVariableGetter.get(name_of_variable="DRY_RUN", default_value=True)

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
            self.log.info(f"Would set the inverter to {mode.name} but dry run is enabled")
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

    def calculate_energy_missing_from_battery_from_state_of_charge(self, state_of_charge: int) -> EnergyAmount:
        """
        Calculates the amount of energy missing in the battery in watt-hours from the state of charge

        Args:
            state_of_charge: The current state of charge of the battery as a percentage.

        Returns:
            The energy missing in watt-hours corresponding to the given state of charge.
        """
        return self.battery_capacity - self.calculate_energy_saved_in_battery_from_state_of_charge(state_of_charge)

    def calculate_energy_saved_in_battery_from_state_of_charge(self, state_of_charge: int) -> EnergyAmount:
        """
        Calculates the amount of energy saved in the battery in watt-hours from the state of charge

        Args:
            state_of_charge: The current state of charge of the battery as a percentage.

        Returns:
            The energy saved in watt-hours corresponding to the given state of charge.
        """
        return self.battery_capacity * (state_of_charge / 100)
