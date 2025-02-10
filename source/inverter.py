import asyncio

import goodwe
from energy_classes import EnergyAmount
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import inverter as GoodweInverter
from goodwe.et import OperationMode
from logger import LoggerMixin
from sems_portal_api_handler import SemsPortalApiHandler


class Inverter(LoggerMixin):
    def __init__(self, controlled_by_bash_script: bool = False):
        super().__init__()

        self._device = None
        self.hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")
        self.battery_capacity = EnergyAmount(float(EnvironmentVariableGetter.get("INVERTER_BATTERY_CAPACITY")))

        self.sems_portal_api_handler = SemsPortalApiHandler()

        # Add a notice to the loggers name to make to easier to identify actions taken by a user manually
        if controlled_by_bash_script:
            self.log.name += " USER"
            self.sems_portal_api_handler.log.name += " USER"

    @property
    def device(self) -> GoodweInverter:
        """
        @property
        Retrieves the inverter device instance. If not already connected, it establishes a connection to the inverter

        Returns:
            GoodweInverter: The instance of the connected inverter.
        """
        if self._device is None:
            self.log.debug(f"Connecting to inverter on {self.hostname}...")
            self._device = asyncio.run(goodwe.connect(self.hostname))
            self.log.info("Successfully connected to inverter")

        return self._device

    def get_operation_mode(self, log_new_mode: bool = False) -> OperationMode:
        """
        Gets the current operation mode of the device.

        Args:
            log_new_mode (bool): Whether to log the current operation mode. Default is False.

        Returns:
            OperationMode: The current operation mode of the device.
        """
        self.log.debug("Getting current operation mode...")
        operation_mode = asyncio.run(self.device.get_operation_mode())
        if log_new_mode:
            self.log.info(f"The current Operation mode is {operation_mode.name}")
        return operation_mode

    def set_operation_mode(self, mode: OperationMode) -> None:
        """
        Sets the current operation mode of the device.

        Args:
            mode: The desired operation mode to be set for the inverter.

        Raises:
            RuntimeError: If the operation mode could not be set successfully.
        """
        self.log.debug(f"Setting new operation mode: {mode.name}...")
        asyncio.run(self.device.set_operation_mode(mode))

        current_operation_mode = self.get_operation_mode()
        if current_operation_mode != mode:
            raise RuntimeError(
                f"Setting the Operation mode was not successful: Expected {mode.name}, Actual: {current_operation_mode.name}"
            )

        self.log.info(f"Successfully set new operation mode {mode.name}")

    def calculate_energy_missing_from_battery_from_state_of_charge(self, state_of_charge: int) -> EnergyAmount:
        """
        Args:
            state_of_charge (int): The current state of charge of the battery as a percentage.

        Returns:
            EnergyAmount: The amount of energy missing from the battery based on the current state of charge.
        """
        return self.battery_capacity - self.calculate_energy_saved_in_battery_from_state_of_charge(state_of_charge)

    def calculate_energy_saved_in_battery_from_state_of_charge(self, state_of_charge: int) -> EnergyAmount:
        """
        Args:
            state_of_charge (int): The current state of charge of the battery as a percentage.

        Returns:
            EnergyAmount: The amount of energy saved in the battery corresponding to the given state of charge.
        """
        return self.battery_capacity * (state_of_charge / 100)

    def calculate_state_of_charge_from_energy_amount(self, energy_amount: EnergyAmount) -> int:
        """
        Args:
            energy_amount: An instance of EnergyAmount.

        Returns:
            int: The state of charge of the inverter depending on the battery size as a percentage, capped at 100%.
        """
        state_of_charge = int(energy_amount.watt_hours / self.battery_capacity.watt_hours * 100)
        if state_of_charge > 100:
            self.log.info(f"The calculated state of charge is {state_of_charge} %, capping it at 100 %")
            return 100
        return state_of_charge

    def get_state_of_charge(self, log_state_of_charge: bool = False) -> int:
        """
        Gets the current state of charge of the device's battery.

        Args:
            log_state_of_charge (bool): Whether to log the state of charge information. Default is False.

        Returns:
            int: The current state of charge in percentage.
        """
        self.log.debug("Getting current state of charge...")
        runtime_data = asyncio.run(self.device.read_runtime_data())
        state_of_charge = runtime_data["battery_soc"]
        if log_state_of_charge:
            self.log.info(f"The current state of charge is {state_of_charge} %")
        return state_of_charge
