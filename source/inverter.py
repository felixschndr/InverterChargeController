import goodwe
from environment_variable_getter import EnvironmentVariableGetter
from goodwe.et import OperationMode
from logger import LoggerMixin


class Inverter(LoggerMixin):
    BATTERY_CAPACITY = 7100  # Wh

    def __init__(self):
        super().__init__()

        self.device = None

        self.hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")

    async def connect(self) -> None:
        self.log.info(f"Connecting to inverter on {self.hostname}")
        self.device = await goodwe.connect(self.hostname)
        self.log.info("Successfully connected")

    async def get_operation_mode(self) -> OperationMode:
        if self.device is None:
            await self.connect()

        self.log.info("Getting current operation mode")
        operation_mode = await self.device.get_operation_mode()
        self.log.info(f"Current Operation mode is {operation_mode.name}")
        return operation_mode

    async def set_operation_mode(self, mode: OperationMode) -> None:
        if self.device is None:
            await self.connect()

        self.log.info(f"Setting new operation mode: {mode.name}")
        await self.device.set_operation_mode(mode)

        current_operation_mode = await self.get_operation_mode()
        if current_operation_mode != mode:
            raise RuntimeError(
                f"Setting the Operation mode was not successful: Expected {mode.name}, Actual: {current_operation_mode.name}"
            )

        self.log.info("Successfully set new operation mode")

    @staticmethod
    def calculate_necessary_duration_to_charge(amount_of_energy: float) -> int:
        """
        Calculates how long the inverter needs to be fully charged.

        :param amount_of_energy: The amount of energy (in Wh) required to fully charge the battery.
        :return: The necessary duration (in hours) to charge the specified amount of energy.
        """
        return 3
