# InverterChargeController

This project aims to charge the battery pack of a photovoltaic system when the energy rates are as low as possible.

The program continuously runs and does the following:

It queries the Tibber API for the least expensive energy rates (= *price minimum*).
  - This is done in the [TibberAPIHandler](source/tibber_api_handler.py).
  - The program then runs from a minimum in prices to the next one and sleeps in between.

When the current time is a price minimum, the program wakes up and does the following:
1. Check for the expected power consumption until the next price minimum.
    - This is done in the [SemsPortalApiHandler](source/sems_portal_api_handler.py).
    - The inverter used while programming this is a model from Goodwe (`GW5KN-ET`) which sends its data (state of charge, power input, power output, ...) into the SEMS portal. These values are retrieved from there via the API.
    - The program calculates how much power will be used until the next price minimum. This is done based on the duration until then, how much power is used during the day vs. during the night and the power consumption in the last 7 days.
2. Check for the amount of expected power harvested by the sun until the next price minimum.
    - This is done in the [SunForecastHandler](source/sun_forecast_handler.py).
    - The data about the photovoltaic system is used to query https://forecast.solar/ via their API for an estimate of power production during the day.
    - The program calculates how much power will be harvested until the next price minimum. This is done based on the duration until then, the amount of sun until then and the overlapping of the timeframes (duration until next minimum vs. sun shining only during the day). 
3. Check the amount of power currently remaining in the battery.
   - This is done in the [SemsPortalApiHandler](source/sems_portal_api_handler.py).
4. Check the amount of power supposed to be remaining in the battery when reaching the next price minimum.
    - This is (as many other values) defined in `.env`. More explanation on this can be found below. 
5. Calculate the difference between these values.
6. Charge the battery (if necessary) such that reaching the next price minimum is possible.
   - This is (as well as the main loop) is done in the [InverterChargeController](source/inverter_charge_controller.py).
   - If charging is necessary, the code calculates the target state of charge, sets the inverter controller accordingly and checks the battery status every 5 minutes.
   - If no charging is needed, the program will do nothing.
   - Afterwards, the program will go back to sleep until the next price minimum.

<details>
  <summary>This is an example excerpt from the log and shows the inner workings</summary>

```txt
[2024-10-29T23:00:00+0100] [InverterChargeController] [INFO] Waiting is over, now is the a price minimum. Checking what has to be done to reach the next minimum...
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] Finding the price minimum...
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] Crawling the Tibber API for the electricity prices
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] The Upcoming energy rates are [0.3085 € at 2024-10-30 00:00:00+01:00, 0.3082 € at 2024-10-30 01:00:00+01:00, 0.3054 € at 2024-10-30 02:00:00+01:00, 0.3053 € at 2024-10-30 03:00:00+01:00, 0.3083 € at 2024-10-30 04:00:00+01:00, 0.3151 € at 2024-10-30 05:00:00+01:00, 0.3356 € at 2024-10-30 06:00:00+01:00, 0.3548 € at 2024-10-30 07:00:00+01:00, 0.3539 € at 2024-10-30 08:00:00+01:00, 0.3366 € at 2024-10-30 09:00:00+01:00, 0.3255 € at 2024-10-30 10:00:00+01:00, 0.3191 € at 2024-10-30 11:00:00+01:00, 0.3106 € at 2024-10-30 12:00:00+01:00, 0.3159 € at 2024-10-30 13:00:00+01:00, 0.3211 € at 2024-10-30 14:00:00+01:00, 0.3388 € at 2024-10-30 15:00:00+01:00, 0.379 € at 2024-10-30 16:00:00+01:00, 0.4193 € at 2024-10-30 17:00:00+01:00, 0.4182 € at 2024-10-30 18:00:00+01:00, 0.3784 € at 2024-10-30 19:00:00+01:00, 0.3476 € at 2024-10-30 20:00:00+01:00, 0.3346 € at 2024-10-30 21:00:00+01:00, 0.3259 € at 2024-10-30 22:00:00+01:00, 0.3223 € at 2024-10-30 23:00:00+01:00]
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] Found 0.3548 € at 2024-10-30 07:00:00+01:00 to be the first maximum of the upcoming energy rates
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] Found 0.4193 € at 2024-10-30 17:00:00+01:00 to be the second maximum of the upcoming energy rates
[2024-10-29T23:00:00+0100] [TibberAPIHandler] [DEBUG] Found 0.3106 € at 2024-10-30 12:00:00+01:00 to be the global minimum of the energy rates between the first and second maximum
[2024-10-29T23:00:00+0100] [InverterChargeController] [INFO] The next price minimum is at 2024-10-30 12:00:00+01:00
[2024-10-29T23:00:00+0100] [SunForecastHandler] [DEBUG] Getting estimated solar output between 2024-10-29 23:00:00.000215+01:00 and 2024-10-30 12:00:00+01:00
[2024-10-29T23:00:00+0100] [SunForecastHandler] [DEBUG] Sunrise is at 2024-10-29 07:10:00+01:00, sunset is at 2024-10-29 17:10:00+01:00, duration of sunlight is 10:00:00, offset is 1:00:00, sunrise with offset is at 2024-10-29 08:10:00+01:00, sunset with offset is at 2024-10-29 16:10:00+01:00
[2024-10-29T23:00:00+0100] [SunForecastHandler] [INFO] There is 0:00:00 of sunlight (with 10 % offsets) during the given timeframe
[2024-10-29T23:00:00+0100] [InverterChargeController] [INFO] The expected energy harvested by the sun till the next price minimum is 0 Wh
[2024-10-29T23:00:00+0100] [SemsPortalApiHandler] [DEBUG] Getting estimated energy usage between 2024-10-29 23:00:00.000215+01:00 and 2024-10-30 12:00:00+01:00
[2024-10-29T23:00:00+0100] [SemsPortalApiHandler] [DEBUG] The time between the given timeframe is split across 6:00:00 of daytime and 6:59:59.999785 of nighttime
[2024-10-29T23:00:00+0100] [SemsPortalApiHandler] [DEBUG] Determining average energy consumption per day
[2024-10-29T23:00:00+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:00:03+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:00:03+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for energy consumption data...
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [DEBUG] Extracted last weeks energy usage: [6280 Wh, 7260 Wh, 5980 Wh, 10110 Wh, 1690 Wh, 4420 Wh, 2920 Wh]
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [DEBUG] Expected energy usage of the day is 5522 Wh
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [DEBUG] Average power consumption today is 230 W
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [INFO] Energy usage during daytime is expected to be 1656 Wh, energy usage during nighttime is expected to be 1288 Wh
[2024-10-29T23:00:05+0100] [InverterChargeController] [INFO] The total expected energy usage till the next price minimum is 2945 Wh
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for current state of charge...
[2024-10-29T23:00:05+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:00:06+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:00:06+0100] [InverterChargeController] [INFO] The battery is currently at 53 %, thus it is holding 3763 Wh
[2024-10-29T23:00:06+0100] [InverterChargeController] [INFO] The battery shall contain 1420 Wh (20 %) when reaching the next minimum
[2024-10-29T23:00:06+0100] [InverterChargeController] [DEBUG] Summary of energy values: {'timestamp now': '2024-10-29 23:00:00.000215+01:00', 'next price minimum': '2024-10-30 12:00:00+01:00', 'expected power harvested till next minimum': 0 Wh, 'expected energy usage till next minimum': 2945 Wh, 'current state of charge': 53, 'current energy in battery': 3763 Wh, 'target min state of charge': 20, 'energy to be in battery when reaching next minimum': 1420 Wh}
[2024-10-29T23:00:06+0100] [InverterChargeController] [INFO] There is a need to charge 602 Wh
[2024-10-29T23:00:06+0100] [InverterChargeController] [INFO] Need to charge to 61 % in order to reach the next minimum with 20 % left
[2024-10-29T23:00:06+0100] [SemsPortalApiHandler] [INFO] Determining amount of energy bought today
[2024-10-29T23:00:06+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:00:06+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:00:06+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for energy consumption data...
[2024-10-29T23:00:07+0100] [InverterChargeController] [DEBUG] The amount of energy bought before charging is 2230 Wh
[2024-10-29T23:00:07+0100] [InverterChargeController] [INFO] Starting to charge
[2024-10-29T23:00:07+0100] [Inverter] [DEBUG] Setting new operation mode: ECO_CHARGE...
[2024-10-29T23:00:12+0100] [Inverter] [DEBUG] Getting current operation mode...
[2024-10-29T23:00:13+0100] [Inverter] [INFO] Current Operation mode is ECO_CHARGE
[2024-10-29T23:00:13+0100] [Inverter] [INFO] Successfully set new operation mode ECO_CHARGE
[2024-10-29T23:00:13+0100] [InverterChargeController] [INFO] Set the inverter to charge, the target state of charge is 61 %. Checking the charging progress every 0:10:00...
[2024-10-29T23:10:13+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for current state of charge...
[2024-10-29T23:10:13+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:10:13+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:10:14+0100] [InverterChargeController] [INFO] The current state of charge is 58%
[2024-10-29T23:10:14+0100] [InverterChargeController] [DEBUG] Charging is still ongoing (current: 58%, target: >= 61%) --> Waiting for another 0:10:00...
[2024-10-29T23:20:14+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for current state of charge...
[2024-10-29T23:20:14+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:20:14+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:20:15+0100] [InverterChargeController] [INFO] The current state of charge is 67%
[2024-10-29T23:20:15+0100] [InverterChargeController] [INFO] Charging finished (67%) --> Setting the inverter back to normal mode
[2024-10-29T23:20:15+0100] [Inverter] [DEBUG] Setting new operation mode: GENERAL...
[2024-10-29T23:20:16+0100] [Inverter] [DEBUG] Getting current operation mode...
[2024-10-29T23:20:16+0100] [Inverter] [INFO] Current Operation mode is GENERAL
[2024-10-29T23:20:16+0100] [Inverter] [INFO] Successfully set new operation mode GENERAL
[2024-10-29T23:20:16+0100] [SemsPortalApiHandler] [INFO] Determining amount of energy bought today
[2024-10-29T23:20:16+0100] [SemsPortalApiHandler] [DEBUG] Logging in into the SEMSPORTAL...
[2024-10-29T23:20:17+0100] [SemsPortalApiHandler] [DEBUG] Login successful
[2024-10-29T23:20:17+0100] [SemsPortalApiHandler] [DEBUG] Crawling the SEMSPORTAL API for energy consumption data...
[2024-10-29T23:20:18+0100] [InverterChargeController] [DEBUG] The amount of energy bought after charging is 3320 Wh
[2024-10-29T23:20:18+0100] [InverterChargeController] [INFO] Bought 1090 Wh to charge the battery
[2024-10-29T23:20:18+0100] [InverterChargeController] [INFO] The next price minimum is at 2024-10-30 12:00:00+01:00. Waiting until then...
```

</details>

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

   | Variable Name                                                                                   | Description                                                                                                                                                                                                                                                                         | Default Value                | Possible Values                                                                                                              |
   |-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|------------------------------------------------------------------------------------------------------------------------------|
   | `ERROR_MAIL_ADDRESS`                                                                            | The mail address to send error logs to in [error_mailer.sh](error_mailer.sh). Only necessary if script is used.                                                                                                                                                                     | -                            | A string containing an email address, example `username@domain.tld`                                                          |
   | `USE_DEBUG_SOLAR_OUTPUT`                                                                        | Use a debug value for the expected solar output (can be used while debugging since the solar forecast API offers a very limited amount of API calls per day). Should be set to `False` in normal production mode.                                                                   | `False`                      | [`True`, `False`]                                                                                                            |
   | `LOGLEVEL`                                                                                      | The level to log at.                                                                                                                                                                                                                                                                | `INFO`                       | [`TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`]                                                                   |
   | `DIRECTORY_OF_LOGS`                                                                             | The directory where the logs of the application shall be stored. Ensure the user running the application has permissions to write in this directory.                                                                                                                                | `<path to repository>/logs/` | A string containing an absolute path, example: `/var/log/inverterchargecontroller/`                                          |
   | `PRINT_TO_STDOUT`                                                                               | Whether to print to stdout in addition to the logfile.                                                                                                                                                                                                                              | `True`                       | [`True`, `False`]                                                                                                            |
   | `POWER_USAGE_FACTOR`                                                                            | The amount of power used during the day vs during the night as a percentage value. E.g. if the value is set to `0.6` the program assumes you use 60 % of the daily power usage between 6 AM and 6 PM and 40 % between 6 PM and 6 AM.                                                | `0.6`                        | A decimal number between `0` and `1`, typically between `0.5` and `0.8`                                                      |
   | `TIBBER_API_TOKEN`                                                                              | The token to crawl the Tibber API. See https://developer.tibber.com/docs/guides/calling-api for more information.                                                                                                                                                                   | -                            | A string, example: `my-secret-token`                                                                                         |
   | `INVERTER_HOSTNAME`                                                                             | The hostname or IP of the inverter.                                                                                                                                                                                                                                                 | -                            | [`inverter.mydomain.com`, `192.168.5.10`, ...]                                                                               |
   | `INVERTER_TARGET_MIN_STATE_OF_CHARGE`                                                           | The state of charge the battery shall have when reaching the next minimum as a buffer.                                                                                                                                                                                              | `20`                         | A number between `0` and `100`, typically between `0` and `40`                                                               |
   | `SEMSPORTAL_USERNAME`                                                                           | The username to login into the SEMSPortal.                                                                                                                                                                                                                                          | -                            | A string, example: `mail@mydomain.com`                                                                                       |
   | `SEMSPORTAL_PASSWORD`                                                                           | The password to login into the SEMSPortal.                                                                                                                                                                                                                                          | -                            | A string, example: `my-secret-password`                                                                                      |
   | `SEMSPORTAL_POWERSTATION_ID`                                                                    | The ID of the inverter in the SEMSPortal. This can be found at the end of the URL in the browser after logging in.                                                                                                                                                                  | -                            | A string, example: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`                                                                    |
   | `SOLCAST_API_KEY`                                                                               | The API-Key of https://www.solcast.com/                                                                                                                                                                                                                                             | -                            | A string, example: `my-secret-token`                                                                                         |
   | `ROOFTOP_ID_1`                                                                                  | The ID of the rooftop in solcast.                                                                                                                                                                                                                                                   | -                            | A string, example: `aaaa-bbbb-cccc-dddd`                                                                                     |
   | `ROOFTOP_ID_2`                                                                                  | The ID of the second rooftop in solcast. This can be used if you have solar panels on both sides of your roof or a small balcony power plant, can be omitted if unused.                                                                                                             | -                            | A string, example: `aaaa-bbbb-cccc-dddd`                                                                                     |
   | `ABSENCE_TIMEFRAME`                                                                             | This variable CAN be set in order to set a timeframe for an absence. During the absence the value of `ABSENCE_POWER_CONSUMPTION` is used to determine the power consumption (not the average of the last week). The timestamps have to be in ISO8601 format and contain a timezone. | -                            | A string in the format `<START_OF_ABSENCE>;<START_OF_ABSENCE>`. Example: `2024-11-03T00:00:00+0100;2024-11-10T11:00:00+0100` |
   | `ABSENCE_POWER_CONSUMPTION`                                                                     | The power consumption to use during the absence (instead of lass week's average)                                                                                                                                                                                                    | `150`                        | A number, typically between `0` and `250`.                                                                                   |

   All the environment variables are read in every time they are used.
   As a consequence, the program does **not** have to be restarted when they are altered.

### Running
#### Manually
You can run the program manually
```bash
python3 source/main.py
```

#### Systemd
or you can install the program as a systemd service.

Before installing the systemd service, you can optionally choose to create a user whose sole purpose is to run this application. This is not necessary at all but considered best practice. If you choose to run the application as your own user, skip this step.

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
vi systemd/inverter-charge-controller.service
sudo ln -s <path to repository>/systemd/inverter-charge-controller.service /etc/systemd/system
sudo systemctl daemon-reload
```

Once done, you can control the program like any other systemd service:
- Status: `sudo systemctl status inverter-charge-controller.service`
- Starting: `sudo systemctl start inverter-charge-controller.service`
- Stopping: `sudo systemctl stop inverter-charge-controller.service`
- Restarting: `sudo systemctl restart inverter-charge-controller.service`
- Enabling to run at boot: `sudo systemctl enable inverter-charge-controller.service`


## Extra script

You can use the [inverter script](./inverter) to control the inverter manually over the command line. It supports getting the current state of charge and operation mode and setting the operation mode.

### Logs

The logs of the application are stored in `<path to repository>/logs/`. They are rolled over once a logfile reaches `1 MB` in size. The current log and a maximum of `7` rolled over logfiles are saved.
See also the environment variables `DIRECTORY_OF_LOGS` and `LOGLEVEL`.

#### Only log the solar forecast

If you pass in `--solar-forecast` as an argument to `main.py` the programm just logs the expected solar forecast of the day.

This can also be used to log the solar prediction after the sun has set to see how far off the solar prediction was and get a sense of how good the predication was (→ not as a *forecast* but as a *review*). To correctly display the log message use `--solar-review` in this case.

#### Monitor solar forecast prediction and power buy

You can monitor how far the prediction of the solar forecast was off and how much power was bought with the script [solar_forecast_logger.sh](solar_forecast_logger.sh).

It saves the following data:
- `<directory> of logs>/power_buy.log`: `<timestamp of start of charging>\t<timestamp of end of charging>\t<power bought in Wh>`
- `<directory> of logs>/solar_forecast_difference.log`: `<date>\t<prediction at start of day in Wh>\t<prediction at end of day in Wh>`

## InfluxDB commands

- Create bucket: `influx bucket create -org default -token ${INFLUXDB_TOKEN} --name default`
- Delete bucket: `influx bucket delete -org default -token ${INFLUXDB_TOKEN} --name default`
- Retrieve all solar forecast values:
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   import "experimental"
   from(bucket: "default")
     |> range(start: 0, stop: experimental.addDuration(d: 2d, to: now()))
     |> filter(fn: (r) => r._measurement == "solar_forecast")
     |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
   '
   ```
- Retrieve all energy prices:
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   import "experimental"
   from(bucket: "default")
     |> range(start: 0, stop: experimental.addDuration(d: 2d, to: now()))
     |> filter(fn: (r) => r._measurement == "energy_prices")
     |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
   '
   ```
- Retrieve all power data (semsportal): 
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   from(bucket: "default")
     |> range(start: 0, stop: now())
     |> filter(fn: (r) => r._measurement == "power")
     |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
   '
   ```
- Retrieve all power buy data: 
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   from(bucket: "default")
     |> range(start: 0, stop: now())
     |> filter(fn: (r) => r._measurement == "power_buy")
     |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
   '
   ```
- Rename a field within the same measurement: 
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   import "experimental"
   from(bucket: "default")
     |> range(start: 0, stop: experimental.addDuration(d: 2d, to: now()))
     |> filter(fn: (r) => r._measurement == "power")
     |> map(fn: (r) => ({
       _time: r._time,
       _value: if exists r.<old_field_name> then r.<old_field_name> else r._value,
       <new_field_name>: r.<old_field_name>,
       _field: "<new_field_name>"
     }))
     |> drop(columns: ["<old_field_name>"])
     |> to(bucket: "default", org: "default")
   '
   ```
- Copy values of `_time` into a new field within the same measurement:
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   import "experimental"
   from(bucket: "default")
     |> range(start: 0, stop: experimental.addDuration(d: 2d, to: now()))
     |> filter(fn: (r) => r._measurement == "<measurement_to_copy>")
     |> map(fn: (r) => ({ _time: r._time, _value: r._value, <new_field_name>: r._time }))
     |> to(bucket: "default", org: "default")
   '
   ```
- Copy data from one measurement to another:
   ```
   influx query -org default -token ${INFLUXDB_TOKEN} \
   '
   import "experimental"
   from(bucket: "default")
     |> range(start: 0, stop: experimental.addDuration(d: 2d, to: now()))
     |> filter(fn: (r) => r._measurement == "<old_measurement>")
     |> set(key: "_measurement", value: "<new_measurement>")
     |> to(bucket: "default")
   '
   ```
- Delete data from one measurement: 
   ```
   influx delete --bucket default -org default -token ${INFLUXDB_TOKEN} \
   --start='1970-01-01T00:00:00Z' --stop=$(date +"%Y-%m-%dT%H:%M:%SZ" -d "+2 days") \
   --predicate '_measurement=<old_measurement>'
   ```
