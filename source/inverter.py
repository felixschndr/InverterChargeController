import asyncio
import os

import goodwe
from dotenv import load_dotenv
from goodwe.et import OperationMode

load_dotenv()


class Inverter:
    def __init__(self):
        self.device = None

        inverter_hostname_environment_variable_name = "INVERTER_HOSTNAME"
        try:
            self.inverter_hostname = os.environ[
                inverter_hostname_environment_variable_name
            ]
        except KeyError:
            raise RuntimeError(
                f"Environment variable {inverter_hostname_environment_variable_name} is not set!"
            )

    async def connect(self) -> None:
        self.device = await goodwe.connect(self.inverter_hostname)

    async def get_operation_mode(self) -> OperationMode:
        return await self.device.get_operation_mode()

    async def get_operation_mode_name(self) -> str:
        operation_mode = await self.get_operation_mode()
        return operation_mode.name

    async def set_operation_mode(self, mode: OperationMode) -> None:
        await self.device.set_operation_mode(mode)

        try:
            assert await self.get_operation_mode() == mode
        except AssertionError:
            raise RuntimeError(
                f"Setting the Operation mode {mode.name} was not successful"
            )


inverter = Inverter()
asyncio.run(inverter.connect())
asyncio.run(inverter.set_operation_mode(OperationMode.GENERAL))
