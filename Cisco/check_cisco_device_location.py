#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Developed by Youssef BOUDDIRA <youssefbouddira@gmail.com>
# Checkmk Plugin – Cisco Device Location

from cmk.base.check_api import register
from cmk.agent_based.v2 import SNMPTree

def check_device_location(item, _params, info):
    location = info[0][0] if info and info[0] else "Unknown"
    return 0, f"Emplacement de ce Noeud est: {location}"

register.check_plugin(
    name="cisco_device_location",
    service_name="HWR_CSC_DEVICE_LOCATION_Info",
    discovery_function=lambda info: [("device_location", {})] if info else [],
    check_function=check_device_location,
    fetch=SNMPTree(base=".1.3.6.1.2.1.1", oids=["6.0"]),
    detect=lambda oid: oid(".1.3.6.1.2.1.1.6.0") in [".1.3.6.1.2.1.1.6"]
)