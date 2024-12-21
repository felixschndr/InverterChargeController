#!/usr/bin/env bash

###### Setup ######
source .env
log_directory=${DIRECTORY_OF_LOGS:-logs/}
logfile=${log_directory}/app.log

if [[ -z ${ERROR_MAIL_ADDRESS} ]]; then
	echo "The \"ERROR_MAIL_ADDRESS\" is not set!"
	exit 1
fi

###### Search for errors ######
current_date=$(date '+%Y-%m-%d')
search_pattern="ERROR|WARNING|CRITICAL"
temp_output=$(mktemp)

grep -A10 -n "${current_date}" "${logfile}" | grep -A10 -E "${search_pattern}" > "${temp_output}"
if [[ $(wc -l < "${temp_output}") != 0 ]]; then
	 mail -r "InverterChargeController" -s "Fehler beim InverterChargeController" "${ERROR_MAIL_ADDRESS}" < "${temp_output}"
fi

###### Cleanup ######
rm "${temp_output}"
