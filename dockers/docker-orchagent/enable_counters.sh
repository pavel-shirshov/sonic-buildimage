#!/usr/bin/env bash

# If the switch was just started (uptime less than 5 minutes),
# wait for 3 minutes and enable counters
# otherwise wait for 60 seconds and enable counters

uptime_str=$(</proc/uptime)
uptime_sec=${uptime_str%% *}
if [[ $uptime_sec -gt 300 ]]; # wait 5 minutes
then
  sleep 180
else 
  sleep 60
fi

# Enable counters
/usr/bin/counterpoll queue enable
/usr/bin/counterpoll port enable
/usr/bin/pfcwd counter_poll enable
