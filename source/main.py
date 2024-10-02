import asyncio

from inverterchargecontroller import InverterChargeController

if __name__ == "__main__":
    inverter_charge_controller = InverterChargeController()
    asyncio.run(inverter_charge_controller.run())
