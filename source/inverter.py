import asyncio

import goodwe
from goodwe.et import OperationMode

from source.environment_variable_getter import EnvironmentVariableGetter


class Inverter:
    def __init__(self):
        self.device = None

        self.inverter_hostname = EnvironmentVariableGetter.get("INVERTER_HOSTNAME")

    async def connect(self) -> None:
        self.device = await goodwe.connect(self.inverter_hostname)

    async def get_operation_mode(self) -> OperationMode:
        return await self.device.get_operation_mode()

    async def get_operation_mode_name(self) -> str:
        operation_mode = await self.get_operation_mode()
        return operation_mode.name

    async def set_operation_mode(self, mode: OperationMode) -> None:
        await self.device.set_operation_mode(mode)

        if await self.get_operation_mode() != mode:
            raise RuntimeError(
                f"Setting the Operation mode {mode.name} was not successful"
            )


inverter = Inverter()
asyncio.run(inverter.connect())
asyncio.run(inverter.set_operation_mode(OperationMode.GENERAL))
