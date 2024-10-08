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
      - This is done in the [InverterChargeController](source/inverterchargecontroller.py).
      - By default, the code will not actually change the operation mode of the inverter. To do this you have to set `DRY_RUN` to `False` in the environment.

## Usage

### Setup

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
   poetry install
   ```
4. Create an `.env` and fill in your values
   ```bash
   cp .env.example .env
   vi .env
   ```
   
   | Variable Name                                 | Description                                                                                                                                                                                            | Default Value | Possible Values                                                                                       |
   |-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|-------------------------------------------------------------------------------------------------------|
   | `DRY_RUN`                                     | Per default system work normally but not actually change the operation mode on the inverter for testing purposes.                                                                                      | `True`        | [`True`, `False`]                                                                                     |
   | `USE_DEBUG_SOLAR_OUTPUT`                      | Use a debug value for the expected solar output. This can be used when running the programm multiple times since the solar forecast API offers a very limited amount of API calls per day.             | `FALSE`       | [`True`, `False`]                                                                                     |
   | `PRINT_TIMESTAMP_IN_LOG`                      | Decide whether you want to print a timestamp in the log messages. Set this to `False` if you use the service with systemd as the log messages will be prepended with a timestamp in `/var/log/syslog`. | `True`        | [`True`, `False`]                                                                                     |
   | `LOGLEVEL`                                    | The level to log at.                                                                                                                                                                                   | `INFO`        | [`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`]                                                     |
   | `TIBBER_API_TOKEN`                            | The token to crawl the Tibber API. See https://developer.tibber.com/docs/guides/calling-api for more information.                                                                                      | -             | A string, example: `my-secret-token`                                                                  |
   | `INVERTER_HOSTNAME`                           | The hostname or IP of the inverter.                                                                                                                                                                    | -             | [`inverter.mydomain.com`, `192.168.5.10`, ...]                                                        |
   | `INVERTER_BATTERY_CAPACITY`                   | The capacity of the battery in watt hours.                                                                                                                                                             | -             | A number, typically between `5,000` and `15,000`                                                      |
   | `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE` | See below.                                                                                                                                                                                             | -             | A number, typically between `5` and `30`.                                                             |
   | `INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE` | See below.                                                                                                                                                                                             | -             | A number, typically between `5` and `30` and smaller as `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE` |
   | `INVERTER_BATTERY_CHARGING_CC_PHASE_LIMIT`    | State of charge to use the `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE`. After that use the `INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE`                                                             | `80`          | A number between `0` and `100`, typically between `70` and `90`                                       |
   | `INVERTER_BATTERY_CHARGING_VOLTAGE`           | The voltage to battery charges at. Typically the same voltage as all the outlets in your house.                                                                                                        | -             | A number, typically between `120` and `240`.                                                          |
   | `INVERTER_BATTERY_CHARGING_EFFICIENCY`        | The efficiency your battery charges at. This can be found on the datasheet of the battery of the inverter.                                                                                             | `0.95`        | A number between `0` and `1`, typically between `0.8` and `0.95`                                      |
   | `INVERTER_TARGET_STATE_OF_CHARGE`             | The state of charge at which the battery is considered full.                                                                                                                                           | `98`          | A number between `0` and `100`, typically between `70` and `100`                                      |
   | `SEMSPORTAL_USERNAME`                         | The username to login into the SEMSPortal.                                                                                                                                                             | -             | A string, example: `mail@mydomain.com`                                                                |
   | `SEMSPORTAL_PASSWORD`                         | The password to login into the SEMSPortal.                                                                                                                                                             | -             | A string, example: `my-secret-password`                                                               |
   | `SEMSPORTAL_POWERSTATION_ID`                  | The ID of the inverter in the SEMSPortal. This can be found at the end of the URL in the browser after logging in.                                                                                     | -             | A string, example: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`                                             |
   | `LOCATION_LATITUDE`                           | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                            | -             | A string, example: `48.8778244909298`                                                                 |
   | `LOCATION_LONGITUDE`                          | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                            | -             | A string, example: `2.3321814528287352`                                                               |
   | `LOCATION_PLANE_DECLINATION`                  | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                            | -             | A number between `0` and `90`                                                                         |
   | `LOCATION_PLANE_AZIMUTH`                      | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                            | -             | A number between `-180` and `180`                                                                     |
   | `LOCATION_NUMBER_OF_PANELS`                   | The number of installed solar panels.                                                                                                                                                                  | -             | A string, example: `48.8778244909298`                                                                 |
   | `LOCATION_MAXIMUM_POWER_OUTPUT_PER_PANEL`     | The maximum power output per solar panel in watts.                                                                                                                                                     | -             | A number, typically between `100` and `600`.                                                          |
   
   Note for `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE` and `INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE`:
   
   Charging a battery can be divided into two phases:
   1. The "Constant Current Phase" (CC phase):
      - This phase is the first phase and goes roughly from `0%` - `80%` state of charge. In this phase the battery charges the fastest. In the CC phase the charging speed is roughly linear.
   2. The "Constant Voltage Phase" (CV phase):
      - This phase is the second phase and goes roughly from `80%` - `100%` state of charge. In this phase the battery charges slower. In the CV phase the charging speed is not linear but exponentially slower. The exponential factor can be approximated by dividing the charging power of this phase by 2. 
   
   You can usually find these values on the battery datasheet of your inverter.
   

### Running
#### Manually
You can run the program manually
```bash
python3 source/main.py
```

#### Systemd
or you can install the programm as a systemd service
```bash
cp systemd/inverter-charge-controller.service.example systemd/inverter-charge-controller.service
vi systemd/inverter-charge-controller.service
sudo ln -s <path to repository>/InverterChargeController/systemd/inverter-charge-controller.service /etc/systemd/system
sudo ln -s <path to repository>/InverterChargeController/systemd/inverter-charge-controller.timer /etc/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable --now inverter-charge-controller.timer
systemctl list-timers # Ensure that timer is listed
```
The programm will start every day at 00:05 AM. This can be changed in [systemd/inverter-charge-controller.timer](systemd/inverter-charge-controller.timer).

### Logs

#### Manually

The logs are printed to stdout.

#### Systemd

The service adds its logs to `/var/log/syslog`. Since this file can become pretty crowded with all kinds of logs you can filter for this service by using `journalctl -u inverter-charge-controller` for all logs and `journalctl -u inverter-charge-controller -b` for the current boot.
