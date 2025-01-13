import asyncio

import goodwe
from energy_classes import EnergyAmount
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import inverter as GoodweInverter
from goodwe.et import OperationMode
from logger import LoggerMixin
from sems_portal_api_handler import SemsPortalApiHandler


class Inverter(LoggerMixin):
    def __init__(self):
        super().__init__()

        self._device = None
        self.hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")

        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.battery_capacity = None
        self.update_battery_capacity()

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

    def update_battery_capacity(self) -> None:
        """
        Updates the battery capacity by retrieving the value using the SemsPortalApiHandler and comparing it
        against the current stored capacity. Logs information about the current and updated battery
        capacity if changes occur.
        """
        battery_capacity = self.sems_portal_api_handler.get_battery_capacity()

        if self.battery_capacity is None:
            self.log.info(f"The battery capacity is {battery_capacity}")
            self.battery_capacity = battery_capacity
            return

        if battery_capacity != self.battery_capacity:
            self.log.info(f"The battery capacity was updated from {self.battery_capacity} to {battery_capacity}")
            self.battery_capacity = battery_capacity

    def get_operation_mode(self) -> OperationMode:
        """
        Gets the current operation mode of the device.

        Returns:
            OperationMode: The current operation mode of the device.
        """
        self.log.debug("Getting current operation mode...")
        operation_mode = asyncio.run(self.device.get_operation_mode())
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

    def get_state_of_charge(self) -> int:
        """
        Gets the current state of charge of the device's battery.

        Returns:
            int: The current state of charge in percentage.
        """
        self.log.debug("Getting current state of charge...")
        runtime_data = asyncio.run(self.device.read_runtime_data())
        state_of_charge = runtime_data["battery_soc"]
        return state_of_charge
