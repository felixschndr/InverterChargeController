# InverterChargeController

This project aims to charge the battery pack of a photovoltaic system when the energy rates are as low as possible.

There is a solar panel on the roof of the house that produces a certain amount of electricity. This power is fed into
the system's battery, where it is stored for use in the house. Every day this script is started (using a systemd timer)
and does the following:
  1. Check the power consumption of the last week and calculate an average. This value is then used as the expected power consumption of the upcoming day.
     - This is done in the [SemsPortalApiHandler](source/sems_portal_api_handler.py).
     - The inverter is a model from Goodwe (GW5KN-ET) which sends its data (state of charge, power input, power output, ...) into the SEMS portal. The values are retrieved from there via the API.
  2. An estimate of the expected solar output from the panels is made.
     - This is done in the [SunForecastAPIHandler](source/sun_forecast_api_handler.py).
     - In the .env file the user has to specify some parameters about his solar panels. See the [.env.example](.env.example) for more details about the configuration.
     - The data about the photovoltaic system is used to query https://forecast.solar/ via their API for an estimate of power production during the day.
  3. If the expected power consumption of the house is less than the expected solar output, the script will exit as
     there is nothing to do.
  4. If the expected power consumption of the house is greater than the expected solar output, the script will use
     energy prices to work out when it is cheapest to charge the battery pack.
     - This is done in the [TibberAPIHandler](source/tibber_api_handler.py) and in the [InverterChargeController](source/inverterchargecontroller.py).
     - The code pulls energy price data for the coming day and works out which time of day will be the cheapest over the
       estimated charging time.
  5. It then waits until that time, sets the inverter to charge, waits for the charging process to be completed and then
     sets the inverter back to normal operation.

## Usage

1. Create a virtual environment
   ```bash
   python -m venv .venv
   ```
2. Activate the virtual environment
   ```bash
   source .venv/bin/activate
   ```
3. Install the requirements
   ```bash
   pip install -r requirements.txt
   ```
4. Run the script
   ```bash
   python3 source/main.py
   ```
