#!/usr/bin/env python3
"""
A function to extract power metrics using iLO.

Usage: python3 measure_power_server.py <IPaddressofILO> <username> <pwd>

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import sys
import redfish
import os

# When running remotely connect using the iLO address, iLO account name,
# and password to send https requests
ilo_url = os.popen('hostname -s').read().rstrip()+"-ilo.labs.hpecorp.net"
print(ilo_url)
SYSTEM_URL = ilo_url
ACCOUNT = sys.argv[1]
PASSWORD = sys.argv[2]

# Create a REDFISH object
REDFISH_OBJ = redfish.redfish_client(base_url=SYSTEM_URL, username=ACCOUNT,
                                     password=PASSWORD)

# Login into the server and create a session
REDFISH_OBJ.login()

# Do a GET on a given path
RESPONSE = REDFISH_OBJ.get("/redfish/v1/Chassis/1/Power/PowerMeter")
RESPONSE = REDFISH_OBJ.get("/redfish/v1/Chassis/1/Power/FastPowerMeter")
# RESPONSE = REDFISH_OBJ.get("/redfish/v1/systems/1/")
# Print out the response
sys.stdout.write("%s\n" % RESPONSE)

# Logout of the current session
REDFISH_OBJ.logout()
