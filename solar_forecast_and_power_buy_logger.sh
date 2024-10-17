#!/usr/bin/env bash

###### Setup ######

# Wait for all logs to be written to disk
sleep 2

# can't use source directly because of possible problems with quotes in the .env file in the semsportal password
env_temp=$(mktemp)
grep "DIRECTORY_OF_LOGS" .env >"${env_temp}"
# shellcheck disable=SC1090
source "${env_temp}"

log_directory=${DIRECTORY_OF_LOGS:-logs/}
logfile=${log_directory}/app.log

###### Find values of power buy ######
start_string="Initializing..."
temp_output_power_buy=$(mktemp)

tac "$logfile" | while read -r line; do
    echo "$line" >>"${temp_output_power_buy}"
    [[ "$line" == *"$start_string"* ]] && break
done

timestamp_start=$(grep "Starting to charge" "${temp_output_power_buy}" | awk '{print $1}' | tr -d '[]')
if [[ -n ${timestamp_start} ]]; then
    # happens if there was no need to charge and thus no charging occurred
    timestamp_end=$(grep "Charging finished" "${temp_output_power_buy}" | awk '{print $1}' | tr -d '[]')
    amount_of_energy_bought=$(grep "Bought" "${temp_output_power_buy}" | sed -n 's/.*Bought \([0-9]*\) Wh.*/\1/p')

    echo -e "${timestamp_start}\t${timestamp_end}\t${amount_of_energy_bought}" >>"${log_directory}"/power_buy.log
fi

###### Find values of solar forecast ######
start_string="The expected solar output for today"
temp_output_solar_forecast=$(mktemp)

tac "$logfile" | while read -r line; do
    echo "$line" >>"${temp_output_solar_forecast}"
    [[ "$line" == *"$start_string"* ]] && break
done

timestamp=$(head -n 1 "${temp_output_solar_forecast}" | awk '{print $1}' | tr -d '[]')
date=$(date -d "${timestamp}" +%Y-%m-%d)
solar_forecast_expected=$(grep "The expected solar output for today" "${temp_output_solar_forecast}" | sed -n 's/.*is \([0-9]*\) Wh.*/\1/p')
solar_forecast_real=$(grep "The actual solar output of today was" "${temp_output_solar_forecast}" | sed -n 's/.*was \([0-9]*\) Wh.*/\1/p')

echo -e "${date}\t${solar_forecast_expected}\t${solar_forecast_real}" >>"${log_directory}"/solar-forecast-difference.log

###### Cleanup ######

rm "${temp_output_power_buy}" "${temp_output_solar_forecast}" "${env_temp}"
