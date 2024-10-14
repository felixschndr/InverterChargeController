# InverterChargeController

This project aims to charge the battery pack of a photovoltaic system when the energy rates are as low as possible.

There is a solar panel on the roof of the house that produces a certain amount of electricity. This power is fed into
the system's battery, where it is stored for use in the house. Every day this script is started (using a systemd timer)
and does the following:
  1. Check the power consumption of the last week and calculate an average. This value is then used as the expected power consumption of the upcoming day.
     - This is done in the [SemsPortalApiHandler](source/sems_portal_api_handler.py).
     - The inverter used while programming this is a model from Goodwe (`GW5KN-ET`) which sends its data (state of charge, power input, power output, ...) into the SEMS portal. The values are retrieved from there via the API.
  2. An estimate of the expected solar output from the panels is made.
     - This is done in the [SunForecastAPIHandler](source/sun_forecast_api_handler.py).
     - In the .env file the user has to specify some parameters about his solar panels. See the [.env.example](.env.example) for more details about the configuration.
     - The data about the photovoltaic system is used to query https://forecast.solar/ via their API for an estimate of power production during the day.
  3. If the expected power consumption of the house is less than the expected solar output, the script will exit as
     there is nothing to do.
  4. If the expected power consumption of the house is greater than the expected solar output, the programm will use
     energy prices to work out when it is cheapest to charge the battery pack.
     1. The programm calculates the necessary duration to charge the battery.
         - This is done in the [Inverter](source/inverter.py).
     2. The programm pulls energy price data for the coming day and works out which time of day will be the cheapest over
        the estimated charging time
        - This is done in the [TibberAPIHandler](source/tibber_api_handler.py).
  5. It then waits until that time, sets the inverter to charge, waits for the charging process to be completed and then
     sets the inverter back to normal operation.
      - This is done in the [InverterChargeController](source/inverterchargecontroller.py).
      - By default, the code will not actually change the operation mode of the inverter. To do this you have to set `DRY_RUN` to `False` in the environment (see table below).

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
   
   | Variable Name                                 | Description                                                                                                                                                                                | Default Value                | Possible Values                                                                                       |
   |-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|-------------------------------------------------------------------------------------------------------|
   | `DRY_RUN`                                     | Per default system work normally but not actually change the operation mode on the inverter for testing purposes.                                                                          | `True`                       | [`True`, `False`]                                                                                     |
   | `USE_DEBUG_SOLAR_OUTPUT`                      | Use a debug value for the expected solar output. This can be used when running the programm multiple times since the solar forecast API offers a very limited amount of API calls per day. | `FALSE`                      | [`True`, `False`]                                                                                     |
   | `LOGLEVEL`                                    | The level to log at.                                                                                                                                                                       | `INFO`                       | [`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`]                                                     |
   | `DIRECTORY_OF_LOGS`                           | The directory where the logs of the application shall be stored. Ensure the user running the application has permissions to write in this directory.                                       | `<path to repository>/logs/` | A string containing an absolute path, example: `/var/log/inverterchargecontroller/`                   |
   | `TIBBER_API_TOKEN`                            | The token to crawl the Tibber API. See https://developer.tibber.com/docs/guides/calling-api for more information.                                                                          | -                            | A string, example: `my-secret-token`                                                                  |
   | `INVERTER_HOSTNAME`                           | The hostname or IP of the inverter.                                                                                                                                                        | -                            | [`inverter.mydomain.com`, `192.168.5.10`, ...]                                                        |
   | `INVERTER_BATTERY_CAPACITY`                   | The capacity of the battery in watt hours.                                                                                                                                                 | -                            | A number, typically between `5,000` and `15,000`                                                      |
   | `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE` | See below.                                                                                                                                                                                 | -                            | A number, typically between `5` and `30`.                                                             |
   | `INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE` | See below.                                                                                                                                                                                 | -                            | A number, typically between `5` and `30` and smaller as `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE` |
   | `INVERTER_BATTERY_CHARGING_CC_PHASE_LIMIT`    | State of charge to use the `INVERTER_BATTERY_CHARGING_AMPERAGE_CC_PHASE`. After that use the `INVERTER_BATTERY_CHARGING_AMPERAGE_CV_PHASE`                                                 | `80`                         | A number between `0` and `100`, typically between `70` and `90`                                       |
   | `INVERTER_BATTERY_CHARGING_VOLTAGE`           | The voltage to battery charges at. Typically the same voltage as all the outlets in your house.                                                                                            | -                            | A number, typically between `120` and `240`.                                                          |
   | `INVERTER_BATTERY_CHARGING_EFFICIENCY`        | The efficiency your battery charges at. This can be found on the datasheet of the battery of the inverter.                                                                                 | `0.95`                       | A number between `0` and `1`, typically between `0.8` and `0.95`                                      |
   | `INVERTER_TARGET_STATE_OF_CHARGE`             | The state of charge at which the battery is considered full.                                                                                                                               | `98`                         | A number between `0` and `100`, typically between `70` and `100`                                      |
   | `SEMSPORTAL_USERNAME`                         | The username to login into the SEMSPortal.                                                                                                                                                 | -                            | A string, example: `mail@mydomain.com`                                                                |
   | `SEMSPORTAL_PASSWORD`                         | The password to login into the SEMSPortal.                                                                                                                                                 | -                            | A string, example: `my-secret-password`                                                               |
   | `SEMSPORTAL_POWERSTATION_ID`                  | The ID of the inverter in the SEMSPortal. This can be found at the end of the URL in the browser after logging in.                                                                         | -                            | A string, example: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`                                             |
   | `LOCATION_LATITUDE`                           | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                | -                            | A string, example: `48.8778244909298`                                                                 |
   | `LOCATION_LONGITUDE`                          | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                | -                            | A string, example: `2.3321814528287352`                                                               |
   | `LOCATION_PLANE_DECLINATION`                  | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                | -                            | A number between `0` and `90`                                                                         |
   | `LOCATION_PLANE_AZIMUTH`                      | See https://doc.forecast.solar/api:estimate#url_parameters and https://www.home-assistant.io/integrations/forecast_solar/#prerequisites for an explanation.                                | -                            | A number between `-180` and `180`                                                                     |
   | `LOCATION_NUMBER_OF_PANELS`                   | The number of installed solar panels.                                                                                                                                                      | -                            | A string, example: `48.8778244909298`                                                                 |
   | `LOCATION_MAXIMUM_POWER_OUTPUT_PER_PANEL`     | The maximum power output per solar panel in watts.                                                                                                                                         | -                            | A number, typically between `100` and `600`.                                                          |
   
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
or you can install the programm as a systemd service. 

Before installing the systemd service you can optionally choose to create a user whose sole purpose is to run this application. This is not necessary at all but best practice. If you choose to run the application as your own user just skip this step.

```bash
sudo su
useradd -r -s /usr/sbin/nologin -m <username>
cd /home/<username>
git clone https://github.com/felixschndr/InverterChargeController.git app/
cd app/
python -m venv .venv
source .venv/bin/activate
poetry install
cp .env.example .env
vi .env
chown -R <username>: app/
```

After that, you can create the systemd configuration:
```bash
cp systemd/inverter-charge-controller.service.example systemd/inverter-charge-controller.service
vi systemd/inverter-charge-controller.service
sudo ln -s <path to repository>/systemd/inverter-charge-controller.service /etc/systemd/system
sudo ln -s <path to repository>/systemd/inverter-charge-controller.timer /etc/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable --now inverter-charge-controller.timer
systemctl list-timers # Ensure that timer is listed
```
The programm will start every day at 00:05 AM. This can be changed in [systemd/inverter-charge-controller.timer](systemd/inverter-charge-controller.timer).

### Note: Just get the solar forecast

If you pass in `--solar-forecast` as an argument to `main.py` the programm just logs the expected solar forecast of the day.

This can also be used to log the solar prediction after the sun has set to see how far off the solar prediction
from before the sun has risen was (--> not as a *forecast* but as a *review*) to get a sense about how good the prediction was. In order to correctly display the log message use `--solar-review` in this case.

There is also a systemd configuration with a service and a timer that does the latter: daily at 11:00 PM log the solar *forecast* from the API. 

### Logs

The logs of the application are stored in `<path to repository>/logs/`. They are rolled over once a logfile reaches `1 MB` in size. The current log and a maximum of `7` rolled over logfiles are saved. 
