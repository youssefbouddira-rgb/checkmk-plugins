#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# Developed by Youssef BOUDDIRA <youssefbouddira@gmail.com>
# Checkmk Plugin – Nutanix Host Maintenance Mode

from collections.abc import Mapping
from typing import Any

from .agent_based_api.v1 import register, Result, Service, State
from .agent_based_api.v1.type_defs import CheckResult, DiscoveryResult

Section = Mapping[str, Any]

def discovery_prism_host_maintenance(section: Section) -> DiscoveryResult:
    if section:
        yield Service()

def check_prism_host_maintenance(params: Mapping[str, Any], section: Section) -> CheckResult:
    if not section:
        return

    maintenance_mode = section.get("host_in_maintenance_mode", False)
    maintenance_reason = section.get("host_maintenance_mode_reason", "No reason provided")

    if maintenance_mode:
        yield Result(state=State.CRIT, summary=f"Host is in maintenance mode: {maintenance_reason}")
    else:
        yield Result(state=State.OK, summary=f"Host is not in maintenance mode")

register.check_plugin(
    name="prism_host_maintenance",
    service_name="SYS_NTNX_PRISM_Host_MAINTENANCE-Mode_Status",
    sections=["prism_host"],
    check_default_parameters={},
    discovery_function=discovery_prism_host_maintenance,
    check_function=check_prism_host_maintenance,
    check_ruleset_name="prism_host_maintenance",
)