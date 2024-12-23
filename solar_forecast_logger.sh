#!/usr/bin/env bash

###### Setup ######
source .env
log_directory=${DIRECTORY_OF_LOGS:-logs/}
logfile=${log_directory}/app.log

###### Find values of solar forecast ######
start_string="The expected solar output of today is"
temp_output_solar_forecast=$(mktemp)

tac "$logfile" | while read -r line; do
    echo "$line" >>"${temp_output_solar_forecast}"
    [[ "$line" == *"$start_string"* ]] && break
done

timestamp=$(head -n 1 "${temp_output_solar_forecast}" | awk '{print $1}' | tr -d '[]')
date=$(date -d "${timestamp}" +%Y-%m-%d)
solar_forecast_expected=$(grep "${start_string}" "${temp_output_solar_forecast}" | sed 's/^.* is //' | sed 's/ Wh//')
solar_forecast_real=$(grep "The actual solar output of today was" "${temp_output_solar_forecast}" | sed 's/^.* was //' | sed 's/ Wh//')

echo -e "${date}\t${solar_forecast_expected}\t${solar_forecast_real}" >>"${log_directory}/solar_forecast_difference.log"

###### Cleanup ######
rm "${temp_output_solar_forecast}"
