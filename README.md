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
   vi .env
   ```

   | Variable Name                         | Description                                                                                                                                                                                                                                                                         | Default Value                | Possible Values                                                                                                              |
   |---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|------------------------------------------------------------------------------------------------------------------------------|
   | `ERROR_MAIL_ADDRESS`                  | The mail address to send error logs to in [error_mailer.sh](error_mailer.sh). Only necessary if script is used.                                                                                                                                                                     | -                            | A string containing an email address, example `username@domain.tld`                                                          |
   | `USE_DEBUG_SOLAR_OUTPUT`              | Use a debug value for the expected solar output (can be used while debugging since the solar forecast API offers a very limited amount of API calls per day). Should be set to `False` in normal production mode.                                                                   | `False`                      | [`True`, `False`]                                                                                                            |
   | `LOGLEVEL`                            | The level to log at.                                                                                                                                                                                                                                                                | `INFO`                       | [`TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`]                                                                   |
   | `DIRECTORY_OF_LOGS`                   | The directory where the logs of the application shall be stored. Ensure the user running the application has permissions to write in this directory.                                                                                                                                | `<path to repository>/logs/` | A string containing an absolute path, example: `/var/log/inverterchargecontroller/`                                          |
   | `PRINT_TO_STDOUT`                     | Whether to print to stdout in addition to the logfile.                                                                                                                                                                                                                              | `True`                       | [`True`, `False`]                                                                                                            |
   | `POWER_USAGE_FACTOR`                  | The amount of power used during the day vs during the night as a percentage value. E.g. if the value is set to `0.6` the program assumes you use 60 % of the daily power usage between 6 AM and 6 PM and 40 % between 6 PM and 6 AM.                                                | `0.6`                        | A decimal number between `0` and `1`, typically between `0.5` and `0.8`                                                      |
   | `TIBBER_API_TOKEN`                    | The token to crawl the Tibber API. See https://developer.tibber.com/docs/guides/calling-api for more information.                                                                                                                                                                   | -                            | A string, example: `my-secret-token`                                                                                         |
   | `INVERTER_HOSTNAME`                   | The hostname or IP of the inverter.                                                                                                                                                                                                                                                 | -                            | [`inverter.mydomain.com`, `192.168.5.10`, ...]                                                                               |
   | `INVERTER_BATTERY_CAPACITY`           | The capacity of the battery in watt hours without any separators.                                                                                                                                                                                                                   | -                            | A number, typically between `3000` and `15000`                                                                               |
   | `INVERTER_TARGET_MIN_STATE_OF_CHARGE` | The state of charge the battery shall have when reaching the next minimum as a buffer.                                                                                                                                                                                              | `15`                         | A number between `0` and `100`, typically between `0` and `40`                                                               |
   | `INVERTER_TARGET_MAX_STATE_OF_CHARGE` | The maximum state of charge the inverter will charge to since the last few percent take a long time to charge.                                                                                                                                                                      | `95`                         | A number between `0` and `100`, typically between `80` and `100`                                                             |
   | `SEMSPORTAL_USERNAME`                 | The username to login into the SEMSPortal.                                                                                                                                                                                                                                          | -                            | A string, example: `mail@mydomain.com`                                                                                       |
   | `SEMSPORTAL_PASSWORD`                 | The password to login into the SEMSPortal.                                                                                                                                                                                                                                          | -                            | A string, example: `my-secret-password`                                                                                      |
   | `SEMSPORTAL_POWERSTATION_ID`          | The ID of the inverter in the SEMSPortal. This can be found at the end of the URL in the browser after logging in.                                                                                                                                                                  | -                            | A string, example: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`                                                                    |
   | `SOLCAST_API_KEY`                     | The API-Key of https://www.solcast.com/                                                                                                                                                                                                                                             | -                            | A string, example: `my-secret-token`                                                                                         |
   | `ROOFTOP_ID_1`                        | The ID of the rooftop in solcast.                                                                                                                                                                                                                                                   | -                            | A string, example: `aaaa-bbbb-cccc-dddd`                                                                                     |
   | `ROOFTOP_ID_2`                        | The ID of the second rooftop in solcast. This can be used if you have solar panels on both sides of your roof or a small balcony power plant, can be omitted if unused.                                                                                                             | -                            | A string, example: `aaaa-bbbb-cccc-dddd`                                                                                     |
   | `ABSENCE_TIMEFRAME`                   | This variable CAN be set in order to set a timeframe for an absence. During the absence the value of `ABSENCE_POWER_CONSUMPTION` is used to determine the power consumption (not the average of the last week). The timestamps have to be in ISO8601 format and contain a timezone. | -                            | A string in the format `<START_OF_ABSENCE>;<START_OF_ABSENCE>`. Example: `2024-11-03T00:00:00+0100;2024-11-10T11:00:00+0100` |
   | `ABSENCE_POWER_CONSUMPTION`           | The power consumption to use during the absence (instead of lass week's average)                                                                                                                                                                                                    | `150`                        | A number, typically between `0` and `250`.                                                                                   |

   All the environment variables are read in every time they are used.
   As a consequence, the program does **not** have to be restarted when they are altered.
   If a `.env.override` exists values of the `.env` are overwritten.

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

## Charging algorithm
The following describes the algorithm the program executes to determine when to charge.
- Start: Now is a price minimum, check what has to be done to reach the next one.
- Calculate the estimated min and max state of charge from now until the next price minimum. Is the estimated min state of charge until the next price minimum lower than the `INVERTER_TARGET_MIN_STATE_OF_CHARGE`?
  - `Yes`: Is it possible to reach the next price minimum by not charging or charging (= is it necessary to charge multiple times to reach the next price minimum?).
    - `Yes`: Continue with `No` branch of parent decision.
    - `No`: It is necessary to charge multiple times
      1. Determine the energy rates before and after the upcoming price spike. A price spike is a series of energy rates that are more expensive than the average of all upcoming energy rates.
      2. Charge until `INVERTER_TARGET_MAX_STATE_OF_CHARGE`
      3. Wait until the energy rate before the price spike.
      4. Is the energy rate after the price spike higher than the one after?
         - `Yes`: Calculate the estimated min state of charge from now until the energy rate after the price spike. Is the estimated min state of charge until the energy rate after the price spike higher than the `INVERTER_TARGET_MIN_STATE_OF_CHARGE`?
           - `Yes`: It is possible to reach the energy rate after the price spike without charging. Wait until the energy rate after the price spike.
           - `No`: It is necessary to charge to reach the energy rate after the price spike. 
             1. Calculate the amount of energy necessary to charge to reach the energy rate after the price spike. # TODO
             2. Charge until `target state of charge`.
             3. Wait until the energy rate after the price spike.
             4. Calculate the estimated min state of charge from now until the next price minimum. Is the estimated min state of charge until the next price minimum higher than the `INVERTER_TARGET_MIN_STATE_OF_CHARGE`?
                - `Yes`: There is no need to charge, skip to end.
                - `No`:
                  1. Calculate the amount of energy necessary to charge to reach the next price minimum. 
                  2. Charge until `target state of charge`.
                  3. Skip to end.
         - `No`: Calculate the estimated min state of charge from now until the next price minimum. Is the estimated min state of charge until the next price minimum higher than the `INVERTER_TARGET_MIN_STATE_OF_CHARGE`? This should not be the case as we calculated this earlier. However, since some hours have passed, it is a good idea to recheck.
           - `Yes`: There is no need to charge, skip to end.
           - `No`: # TODO
  - `No`: Is the current energy rate higher than the one of the next price minimum?
    - `Yes`: Only charge as much as necessary to reach the next price minimum. Is the estimated min state of charge until the next price minimum higher than the `INVERTER_TARGET_MIN_STATE_OF_CHARGE`?
      - `Yes`: There is no need to charge, skip to end. 
      - `No`: There is a need to charge.
        1. `target state of charge` = `current state of charge` + `INVERTER_TARGET_MIN_STATE_OF_CHARGE` - `estimated min state of charge until the next price minimum`.
        2. Charge until `target state of charge`.
        3. Skip to end.
    - `No`: Charge as much as possible without waisting energy from the sun. 
      1. `target state of charge` = `current state of charge` + `INVERTER_TARGET_MAX_STATE_OF_CHARGE` - `estimated max state of charge until the next price minimum`.
      2. Charge until `target state of charge`.
      3. Skip to end.
- Wait until next price minimum.

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
