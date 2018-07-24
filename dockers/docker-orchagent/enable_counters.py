#!/usr/bin/env python

import swsssdk
import time

def enable_counter(db, name):
    info = {}
    info['FLEX_COUNTER_STATUS'] = 'enable'
    db.mod_entry("FLEX_COUNTER_TABLE", name, info)

def enable_counters():
    configdb = swsssdk.ConfigDBConnector()
    configdb.connect()
    enable_counter(configdb, 'PORT')
    enable_counter(configdb, 'QUEUE')
    enable_counter(configdb, 'PFCWD')

def get_uptime():
    with open('/proc/uptime') as fp:
        return int(fp.read().split(' ')[0])

def main():
    # If the switch was just started (uptime less than 5 minutes),
    # wait for 3 minutes and enable counters
    # otherwise wait for 60 seconds and enable counters
    uptime = get_uptime()
    if uptime < 300:
        time.sleep(180)
    else:
        time.sleep(60)
    enable_counters()

if __name__ == '__main__':
    main()
