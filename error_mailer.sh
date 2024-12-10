#!/usr/bin/env bash

###### Setup ######

# can't use source directly because of possible problems with quotes in the .env file in the semsportal password
env_temp=$(mktemp)
grep "DIRECTORY_OF_LOGS" .env >"${env_temp}"
grep "ERROR_MAIL_ADDRESS" .env >>"${env_temp}"
# shellcheck disable=SC1090
source "${env_temp}"

if [[ -z ${ERROR_MAIL_ADDRESS} ]]; then
	echo "The \"ERROR_MAIL_ADDRESS\" is not set!"
	exit 1
fi

log_directory=${DIRECTORY_OF_LOGS:-logs/}
logfile=${log_directory}/app.log

current_date=$(date '+%Y-%m-%d')
search_pattern="ERROR|WARNING|CRITICAL"
temp_output=$(mktemp)

###### Search for errors ######
grep -A10 -n "${current_date}" "${logfile}" | grep -A10 -E "${search_pattern}" > "${temp_output}"
if [[ $(wc -l "${temp_output}") != 0 ]]; then
	 mail -r "InverterChargeController" -s "Fehler beim InverterChargeController" "${ERROR_MAIL_ADDRESS}" < "${temp_output}"
fi

###### Cleanup ######
rm "${temp_output}" "${env_temp}"
