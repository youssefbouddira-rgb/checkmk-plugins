#!/usr/bin/env python3
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#
# Special agent to collect the Hitachi VSP data via REST API.
# Use Hitachi VSP rule to set data source (username, password and SSL check)
#
# Based on the following code:
#    https://code.spearhead.cloud/Spearhead/checkmk-plugins/src/branch/master/hitachi-vsp
# 
# (c) Janez Bostic (janez.bostic@kontron.si)
#
# Created: 01.04.2025
#
# License: GNU General Public License v2
#
# Modified by: Youssef (equipe Outillage / Econocom)
# Modified: 14.09.2026
#
# Ajustements apportes pour compatibilite avec Hitachi VSP One Block (B26) :
#   - Sur VSP One Block, les tables materielles remontees par l'endpoint
#     /ConfigurationManager/v1/objects/components/instance (ctls,
#     cacheMemories, chbs, cacheFlashMemories, dkbs, sfps, bkmfs) sont
#     nichees sous la cle "dkcs" (liste de controleurs DKC), et non plus
#     exposees a la racine du JSON comme sur les gammes E/G d'origine
#     (VSP E590) sur lesquelles ce plugin avait ete developpe et teste.
#     process_storage_hardware_status() a ete modifiee pour boucler sur
#     full_data.get("dkcs", []) avant de lire chaque table.
#   - Tous les acces directs dict["cle"] sur ces tables (ctls, cacheMemories,
#     chbs, cacheFlashMemories, dkbs, sfps, bkmfs, driveBoxes, drives, encs,
#     dbps) ont ete remplaces par dict.get("cle", []) pour eviter un
#     KeyError bloquant si une table est absente ou vide sur ce modele.
#   - Le champ drive["recomendReplacement"], absent sur les disques VSP One
#     Block, est desormais lu via drive.get("recomendReplacement", "0")
#     pour garantir 4 colonnes non vides en sortie (une valeur par defaut
#     vide "" faisait perdre la tabulation finale et cassait le parsing
#     CheckMK de la section hitachivsp_drive_boxes_drives).
#
# Teste et valide sur : Hitachi VSP One B26 (dkcMicroVersion A3-05-42/00),
# CheckMK 2.4, site usc01.
#
#
import sys
import pprint
import json
import pathlib
import urllib3
import requests
import argparse
from typing import List, Dict, Any, Optional, Union
from cmk.utils import password_store

from cmk.special_agents.v0_unstable.agent_common import SectionWriter, special_agent_main
from cmk.special_agents.v0_unstable.argument_parsing import Args, create_default_argument_parser


# Define type aliases for better readability
JSONObject = Dict[str, Any]
JSONArray = List[JSONObject]
JSONType = Union[JSONObject, JSONArray, str, int, float, bool, None]


# Argument parser setup
parser = argparse.ArgumentParser(description="Checkmk agent for Hitachi VSP storage systems.")
parser.add_argument(
    "--address",
    help="Specify the name or IP address of the device.",
    type=str,
    required=True #Mark address as required, because if not defined it can not run.
    )
parser.add_argument(
    "--username",
    help="Specify the username for the API access.",
    type=str,
    required=True #Mark username as required, because if not defined it can not run.
    )
#parser.add_argument(
#    "--password",
#    help="Specify the password for the API access.",
#    type=str,
#    required=True #Mark password as required, because if not defined it can not run.
#    )
group_password = parser.add_mutually_exclusive_group(required=True)
group_password.add_argument(
        "--password-ref",
        help="Password store reference to the secret pasword of the API access.",
    )
group_password.add_argument("--password", help="Specify the username for the API access.")
parser.add_argument(
    "--demo",
    help="Specify the mode of the access.",
    type=bool,
    default=False,
    action=argparse.BooleanOptionalAction
)
parser.add_argument(
    "--no-cert-check",
    help="Specify if certificate check is suppressed (True|False).",
    type=str,
    default="False", #Added a default
    choices=["True", "False"] # Added values validation
)
args = parser.parse_args()


def usage() -> None:
    """Prints usage information to stderr and exits."""
    sys.stderr.write(
        """Check_MK Hitachi VSP

USAGE: agent_hitachivsp [OPTIONS] HOST

OPTIONS:
  -h, --help                    Show this help message and exit
  --address                     Host address
  --user                        Username
  --password                    Password
  --no-cert-check               Disable certificate check
"""
    )
    sys.exit(1)


def get_password_from_args(args: Args) -> str:
    if args.password:
        return args.password

    pw_id, pw_file = args.password_ref.split(":", maxsplit=1)

    return password_store.lookup(pathlib.Path(pw_file), pw_id)


def query(url: str) -> str:
    """Queries the specified URL and returns the raw JSON response.

    Args:
        url: The URL to query.

    Returns:
        The raw JSON response as a string.
    """
    if args.no_cert_check == "False":
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        response = requests.get(
            url,
            #auth=(args.username, args.password),
            auth=(args.username, get_password_from_args(args)),
            verify=args.no_cert_check == 'True',
            timeout=10, #Add timeout to prevent the code from hanging.
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        raw_json = response.text
        return raw_json
    except requests.exceptions.RequestException as e:
        sys.stderr.write(f"Connection error: {e}\n")
        sys.exit(1)

output_lines: List[str] = []


def output(line: str) -> None:
    """Appends a line to the output_lines list.

    Args:
        line: The line to append.
    """
    output_lines.append(line)


def get_storage_info() -> str:
    """Retrieves storage information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_info #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/storages/instance" % args.address
    return query(url)


def get_storage_pools() -> str:
    """Retrieves storage pools information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_pools #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/pools" % args.address
    return query(url)


def get_storage_clprs() -> str:
    """Retrieves CLPRs information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_clprs #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/clprs" % args.address
    return query(url)


def get_storage_ldevs() -> str:
    """Retrieves LDEVs information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_ldevs #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/ldevs" % args.address
    return query(url)


def get_storage_parity_groups() -> str:
    """Retrieves parity groups information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_parity_groups #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/parity-groups" % args.address
    return query(url)


def get_storage_hardware_status() -> str:
    """Retrieves hardware status information from the Hitachi VSP API."""
    if args.demo:
        raw_json = storage_hardware_status #This needs to be defined with test values.
        return raw_json
    url = "https://%s/ConfigurationManager/v1/objects/components/instance" % args.address
    return query(url)


def process_storage_hardware_status() -> None:
    """Processes storage hardware status data and formats it for Checkmk."""
    raw_json = get_storage_hardware_status()
    try:
        full_data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return

    system: JSONObject = full_data["system"]
    output("<<<hitachivsp_powerConsumption:sep(9)>>>")
    output("powerConsumption\t%s" % (system["powerConsumption"]))

    # Sur VSP One Block (contrairement aux series E/G d'origine), les tables
    # materielles (ctls, cacheMemories, chbs, cacheFlashMemories, dkbs, sfps,
    # bkmfs) sont nichees sous "dkcs" (liste des controleurs DKC) et non plus
    # exposees a la racine du JSON. driveBoxes reste en revanche a la racine.
    dkcs: JSONArray = full_data.get("dkcs", [])

    output("<<<hitachivsp_ctls:sep(9)>>>")
    output("location\tstatus\ttemperature\ttemperatureStatus\tcharge")
    for dkc in dkcs:
        for ctl in dkc.get("ctls", []):
            output(
                "%s\t%s\t%s\t%s\t%s"
                % (ctl["location"], ctl["status"], ctl["temperature"], ctl["temperatureStatus"], ctl["charge"])
            )

    output("<<<hitachivsp_cache_memories:sep(9)>>>")
    output("location\tstatus\tcacheSize")
    for dkc in dkcs:
        for cachemem in dkc.get("cacheMemories", []):
            output("%s\t%s\t%s" % (cachemem["location"], cachemem["status"], cachemem["cacheSize"]))

    output("<<<hitachivsp_channel_board:sep(9)>>>")
    output("location\tstatus\ttype")
    for dkc in dkcs:
        for channelboard in dkc.get("chbs", []):
            output("%s\t%s\t%s" % (channelboard["location"], channelboard["status"], channelboard["type"]))

    output("<<<hitachivsp_cache_flash_memories:sep(9)>>>")
    output("location\tstatus\ttype")
    for dkc in dkcs:
        for cacheflashmemory in dkc.get("cacheFlashMemories", []):
            output(
                "%s\t%s\t%s" % (cacheflashmemory["location"], cacheflashmemory["status"], cacheflashmemory["type"])
            )

    output("<<<hitachivsp_disk_boards:sep(9)>>>")
    output("location\tstatus\ttype")
    for dkc in dkcs:
        for dkb in dkc.get("dkbs", []):
            output("%s\t%s\t%s" % (dkb["location"], dkb["status"], dkb["type"]))

    output("<<<hitachivsp_sfps:sep(9)>>>")
    output("portId\tstatus\ttype\tspeed\tportCondition")
    for dkc in dkcs:
        for sfp in dkc.get("sfps", []):
            output(
                "%s\t%s\t%s\t%s\t%s" % (sfp["portId"], sfp["status"], sfp["type"], sfp["speed"], sfp["portCondition"])
            )

    output("<<<hitachivsp_backup_modules:sep(9)>>>")
    output("location\tstatus\tbat_location\tbat_status\tbat_life")
    for dkc in dkcs:
        for backup_module in dkc.get("bkmfs", []):
            batteries: List[JSONObject] = backup_module.get("batteries", [])
            if batteries:
                battery: JSONObject = batteries[0]  # Safe index access
                output(
                    "%s\t%s\t%s\t%s\t%s"
                    % (
                        backup_module["location"],
                        backup_module["status"],
                        battery["location"],
                        battery["status"],
                        battery["life"],
                    )
                )
            else:
                output("%s\t%s\t\t\t" % (backup_module["location"], backup_module["status"]))

    driveboxes: JSONArray = full_data.get("driveBoxes", [])
    output("<<<hitachivsp_drive_boxes_drives:sep(9)>>>")
    output("drivebox_location\tdrive_location\tdrive_status\tdrive_recomend_Replacement")
    for drivebox in driveboxes:
        drives: JSONArray = drivebox.get("drives", [])
        for drive in drives:
            output(
                "%s\t%s\t%s\t%s"
                % (drivebox["location"], drive["location"], drive["status"], drive.get("recomendReplacement", "0"))
            )

    output("<<<hitachivsp_drive_boxes_encs:sep(9)>>>")
    output("drivebox_location\tenc_location\tenc_status")
    for drivebox in driveboxes:
        encs: JSONArray = drivebox.get("encs", [])
        for enc in encs:
            output("%s\t%s\t%s" % (drivebox["location"], enc["location"], enc["status"]))

    output("<<<hitachivsp_drive_boxes_dbps:sep(9)>>>")
    output("drivebox_location\tdbps_location\tdbps_status")
    for drivebox in driveboxes:
        dbps: JSONArray = drivebox.get("dbps", [])
        for power_supply in dbps:
            output("%s\t%s\t%s" % (drivebox["location"], power_supply["location"], power_supply["status"]))


def process_storage_parity_groups() -> None:
    """Processes storage parity groups data and formats it for Checkmk."""
    output("<<<hitachivsp_parity_groups:sep(9)>>>")
    raw_json = get_storage_parity_groups()
    try:
        full_data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return
    data: JSONArray = full_data["data"]
    output(
        "parityGroupId\tnumOfLdevs\tusedCapacityRate\tclprId\tavailableVolumeCapacity\t"
        "totalCapacity\tphysicalCapacity"
    )
    for parity_group in data:
        output(
            "%s\t%s\t%s\t%s\t%s\t%s\t%s"
            % (
                parity_group["parityGroupId"],
                parity_group["numOfLdevs"],
                parity_group["usedCapacityRate"],
                parity_group["clprId"],
                parity_group["availableVolumeCapacity"],
                parity_group["totalCapacity"],
                parity_group["physicalCapacity"],
            )
        )


def process_storage_ldevs() -> None:
    """Processes storage LDEVs data and formats it for Checkmk."""
    output("<<<hitachivsp_ldevs:sep(9)>>>")
    raw_json = get_storage_ldevs()
    try:
        full_data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return
    data: JSONArray = full_data["data"]
    output(
        "ldevId\tclprId\tbyteFormatCapacity\tblockCapacity\t" "label\tstatus"
    )  # Corrected typo in output string
    for ldev in data:
        if "clprId" in ldev:
            label = "_".join(ldev["attributes"])
            output(
                "%s\t%s\t%s\t%s\t%s\t%s"
                % (
                    ldev["ldevId"],
                    ldev["clprId"],
                    ldev["byteFormatCapacity"],
                    ldev["blockCapacity"],
                    label,
                    ldev["status"],
                )
            )


def process_storage_clprs() -> None:
    """Processes storage CLPRs data and formats it for Checkmk."""
    output("<<<hitachivsp_clprs:sep(9)>>>")
    raw_json = get_storage_clprs()
    try:
        full_data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return
    data: JSONArray = full_data["data"]
    output(
        "clprId\tcacheMemoryCapacity\tcacheMemoryUsedCapacity\twritePendingDataCapacity\t"
        "writePendingDataCapacity\tcacheUsageRate"
    )
    for clpr in data:
        output(
            "%s\t%s\t%s\t%s\t%s"
            % (
                clpr["clprId"],
                clpr["cacheMemoryCapacity"],
                clpr["cacheMemoryUsedCapacity"],
                clpr["writePendingDataCapacity"],
                clpr["cacheUsageRate"],
            )
        )


def process_storage_pools() -> None:
    """Processes storage pools data and formats it for Checkmk."""
    output("<<<hitachivsp_pools:sep(9)>>>")
    raw_json = get_storage_pools()
    try:
        full_data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return
    data: JSONArray = full_data["data"]
    output(
        "poolID\tpoolType\tpoolName\ttotalPhysicalCapacity\ttotalPoolCapacity\tavailableVolumeCapacity\tusedCapacityRate\tpoolStatus"
    )
    for pool in data:
        output(
            "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s"
            % (
                pool["poolId"],
                pool["poolType"],
                pool["poolName"],
                pool["totalPhysicalCapacity"],
                pool["totalPoolCapacity"],
                pool["availableVolumeCapacity"],
                pool["usedCapacityRate"],
                pool["poolStatus"],
            )
        )


def process_storage_info() -> None:
    """Processes storage system information and formats it for Checkmk."""
    output("<<<hitachivsp_info:sep(9)>>>")
    raw_json = get_storage_info()
    try:
        data: JSONObject = json.loads(raw_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error decoding JSON: {e}\nRaw JSON:{raw_json}\n")
        return
    output("%s\t%s\t%s\t%s" % (data["serialNumber"], data["storageDeviceId"], data["dkcMicroVersion"], data["model"]))


def main() -> None:
    """Main function to orchestrate data retrieval and processing."""
    try:
        process_storage_info()
        process_storage_pools()
        process_storage_clprs()
        process_storage_ldevs()
        process_storage_parity_groups()
        process_storage_hardware_status()
        sys.stdout.write("\n".join(output_lines) + "\n")
    except Exception as e:
        sys.stderr.write(f"General error: {e}\n")  # Added general exception catch-all
        sys.exit(1)


storage_info = """{
 "storageDeviceId": "666666666666",
 "model": "VSP G700",
 "serialNumber": 666666,
 "ctl1Ip": "192.168.223.69",
 "ctl2Ip": "192.168.223.70",
 "dkcMicroVersion": "88-04-03/00",
 "communicationModes": [
   {
     "communicationMode": "lanConnectionMode"
   }
 ],
 "isSecure": true
}"""

storage_clprs="""{
  "data": [
    {
      "clprId": 0,
      "clprName": "CLPR0",
      "cacheMemoryCapacity": 924672,
      "cacheMemoryUsedCapacity": 901454,
      "writePendingDataCapacity": 44959,
      "sideFilesCapacity": 0,
      "cacheUsageRate": 99,
      "writePendingDataRate": 5,
      "sideFilesUsageRate": 0
    }
  ]
}"""


storage_hardware_status = """{
  "system": {
    "powerConsumption": 1357
  },
  "ctls": [
    {
      "location": "CTL1",
      "status": "Normal",
      "temperature": 23,
      "temperatureStatus": "Normal",
      "charge": 100,
      "type": "-"
    },
    {
      "location": "CTL2",
      "status": "Normal",
      "temperature": 23,
      "temperatureStatus": "Normal",
      "charge": 100,
      "type": "-"
    }
  ],
  "cacheMemories": [
    {
      "location": "CTL1 CMG0",
      "status": "Normal",
      "cacheSize": 256
    },
    {
      "location": "CTL1 CMG1",
      "status": "Normal",
      "cacheSize": 256
    },
    {
      "location": "CTL2 CMG0",
      "status": "Normal",
      "cacheSize": 256
    },
    {
      "location": "CTL2 CMG1",
      "status": "Normal",
      "cacheSize": 256
    }
  ],
  "chbs": [
    {
      "location": "CHB-1A",
      "status": "Normal",
      "type": "32G Ready 4Port FC"
    },
    {
      "location": "CHB-1B",
      "status": "Normal",
      "type": "32G Ready 4Port FC"
    },
    {
      "location": "CHB-2A",
      "status": "Normal",
      "type": "32G Ready 4Port FC"
    },
    {
      "location": "CHB-2B",
      "status": "Normal",
      "type": "32G Ready 4Port FC"
    }
  ],
  "cacheFlashMemories": [
    {
      "location": "CFM-10",
      "status": "Normal",
      "type": "BM45"
    },
    {
      "location": "CFM-11",
      "status": "Normal",
      "type": "BM45"
    },
    {
      "location": "CFM-20",
      "status": "Normal",
      "type": "BM45"
    },
    {
      "location": "CFM-21",
      "status": "Normal",
      "type": "BM45"
    }
  ],
  "dkbs": [
    {
      "location": "DKB-1G",
      "status": "Normal",
      "type": "Disk Board"
    },
    {
      "location": "DKB-1H",
      "status": "Normal",
      "type": "Disk Board"
    },
    {
      "location": "DKB-2G",
      "status": "Normal",
      "type": "Disk Board"
    },
    {
      "location": "DKB-2H",
      "status": "Normal",
      "type": "Disk Board"
    }
  ],
  "lanbs": [
    {
      "location": "LAN1",
      "status": "Normal"
    },
    {
      "location": "LAN2",
      "status": "Normal"
    }
  ],
  "sfps": [
    {
      "portId": "1A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "3A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "5A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "7A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "1B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "3B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "5B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "7B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "2A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "4A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "6A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "8A",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "2B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "4B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "6B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    },
    {
      "portId": "8B",
      "status": "Normal",
      "type": "Short Wave",
      "speed": "16 Gbps",
      "portCondition": "Available (Connected)"
    }
  ],
  "bkmfs": [
    {
      "location": "BKMF-10",
      "status": "Normal",
      "batteries": []
    },
    {
      "location": "BKMF-11",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B11",
          "status": "Normal",
          "life": 90
        }
      ]
    },
    {
      "location": "BKMF-12",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B12",
          "status": "Normal",
          "life": 90
        }
      ]
    },
    {
      "location": "BKMF-13",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B13",
          "status": "Normal",
          "life": 90
        }
      ]
    },
    {
      "location": "BKMF-20",
      "status": "Normal",
      "batteries": []
    },
    {
      "location": "BKMF-21",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B21",
          "status": "Normal",
          "life": 90
        }
      ]
    },
    {
      "location": "BKMF-22",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B22",
          "status": "Normal",
          "life": 90
        }
      ]
    },
    {
      "location": "BKMF-23",
      "status": "Normal",
      "batteries": [
        {
          "location": "BAT-B23",
          "status": "Normal",
          "life": 90
        }
      ]
    }
  ],
  "dkcpss": [
    {
      "location": "DKCPS1",
      "status": "Normal"
    },
    {
      "location": "DKCPS2",
      "status": "Normal"
    }
  ],
  "driveBoxes": [
    {
      "location": "DB-00",
      "type": "DBF",
      "led": "OFF",
      "drives": [
        {
          "location": "HDD00-00",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-01",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-02",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-03",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-04",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-05",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD00-11",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "Spare",
          "recomendReplacement": 0
        }
      ],
      "encs": [
        {
          "location": "ENC00-1",
          "status": "Normal"
        },
        {
          "location": "ENC00-2",
          "status": "Normal"
        }
      ],
      "dbps": [
        {
          "location": "DBPS00-1",
          "status": "Normal"
        },
        {
          "location": "DBPS00-2",
          "status": "Normal"
        }
      ]
    },
    {
      "location": "DB-01",
      "type": "DBF",
      "led": "OFF",
      "drives": [
        {
          "location": "HDD01-00",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD01-01",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD01-02",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD01-03",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD01-04",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD01-05",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        }
      ],
      "encs": [
        {
          "location": "ENC01-1",
          "status": "Normal"
        },
        {
          "location": "ENC01-2",
          "status": "Normal"
        }
      ],
      "dbps": [
        {
          "location": "DBPS01-1",
          "status": "Normal"
        },
        {
          "location": "DBPS01-2",
          "status": "Normal"
        }
      ]
    },
    {
      "location": "DB-02",
      "type": "DBF",
      "led": "OFF",
      "drives": [
        {
          "location": "HDD02-00",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD02-01",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD02-02",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD02-03",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD02-04",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD02-05",
          "modelCode": "NFHAJ-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        }
      ],
      "encs": [
        {
          "location": "ENC02-1",
          "status": "Normal"
        },
        {
          "location": "ENC02-2",
          "status": "Normal"
        }
      ],
      "dbps": [
        {
          "location": "DBPS02-1",
          "status": "Normal"
        },
        {
          "location": "DBPS02-2",
          "status": "Normal"
        }
      ]
    },
    {
      "location": "DB-03",
      "type": "DBF",
      "led": "OFF",
      "drives": [
        {
          "location": "HDD03-00",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD03-01",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD03-02",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD03-03",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD03-04",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        },
        {
          "location": "HDD03-05",
          "modelCode": "NFHAK-Q13RSS",
          "status": "Normal",
          "usage": "DATA",
          "recomendReplacement": 0
        }
      ],
      "encs": [
        {
          "location": "ENC03-1",
          "status": "Normal"
        },
        {
          "location": "ENC03-2",
          "status": "Normal"
        }
      ],
      "dbps": [
        {
          "location": "DBPS03-1",
          "status": "Normal"
        },
        {
          "location": "DBPS03-2",
          "status": "Normal"
        }
      ]
    }
  ],
  "fans": [],
  "upsMode": "Standard Mode",
  "pecbs": [],
  "chbb": {},
  "pcps": [],
  "swpks": [],
  "chbbfans": [],
  "chbbpss": []
}"""


storage_pools = """
{
  "data" : [ {
    "poolId" : 0,
    "poolStatus" : "POLN",
    "usedCapacityRate" : 47,
    "usedPhysicalCapacityRate" : 47,
    "poolName" : "RAID6_HDT_01",
    "availableVolumeCapacity" : 208964826,
    "availablePhysicalVolumeCapacity" : 208964826,
    "totalPoolCapacity" : 397630296,
    "totalPhysicalCapacity" : 397630296,
    "numOfLdevs" : 136,
    "firstLdevId" : 3,
    "warningThreshold" : 80,
    "depletionThreshold" : 90,
    "virtualVolumeCapacityRate" : -1,
    "isMainframe" : false,
    "isShrinking" : true,
    "locatedVolumeCount" : 242,
    "totalLocatedCapacity" : 234976098,
    "blockingMode" : "NB",
    "totalReservedCapacity" : 0,
    "reservedVolumeCount" : 0,
    "poolActionMode" : "AUT",
    "tierOperationStatus" : "MON",
    "dat" : "VAL",
    "poolType" : "RT",
    "monitoringMode" : "CM",
    "tiers" : [ {
      "tierNumber" : 1,
      "tierLevelRange" : "00000001",
      "tierDeltaRange" : "00000005",
      "tierUsedCapacity" : 31524696,
      "tierTotalCapacity" : 37087848,
      "tablespaceRate" : 10,
      "performanceRate" : 4,
      "progressOfReplacing" : 100,
      "bufferRate" : 5
    }, {
      "tierNumber" : 2,
      "tierLevelRange" : "00000000",
      "tierDeltaRange" : "00000005",
      "tierUsedCapacity" : 98679336,
      "tierTotalCapacity" : 116093208,
      "tablespaceRate" : 10,
      "performanceRate" : 12,
      "progressOfReplacing" : 100,
      "bufferRate" : 5
    }, {
      "tierNumber" : 3,
      "tierLevelRange" : "00000000",
      "tierDeltaRange" : "00000000",
      "tierUsedCapacity" : 58461480,
      "tierTotalCapacity" : 244449240,
      "tablespaceRate" : 10,
      "performanceRate" : 62,
      "progressOfReplacing" : 100,
      "bufferRate" : 5
    } ],
    "dataReductionAccelerateCompCapacity" : 0,
    "dataReductionAccelerateCompRate" : 0,
    "compressionRate" : 0,
    "dataReductionAccelerateCompIncludingSystemData" : {
      "isReductionCapacityAvailable" : true,
      "reductionCapacity" : 0,
      "isReductionRateAvailable" : true,
      "reductionRate" : 0
    },
    "capacitiesExcludingSystemData" : {
      "usedVirtualVolumeCapacity" : 386386968576
    }
  }, {
    "poolId" : 1,
    "poolStatus" : "POLN",
    "usedCapacityRate" : 0,
    "usedPhysicalCapacityRate" : 0,
    "snapshotCount" : 0,
    "poolName" : "THIN_IMAGE_POOL",
    "availableVolumeCapacity" : 46453344,
    "availablePhysicalVolumeCapacity" : 46453344,
    "totalPoolCapacity" : 46453344,
    "totalPhysicalCapacity" : 46453344,
    "numOfLdevs" : 16,
    "firstLdevId" : 22,
    "warningThreshold" : 80,
    "virtualVolumeCapacityRate" : -1,
    "isMainframe" : false,
    "isShrinking" : false,
    "poolType" : "HTI",
    "dataReductionAccelerateCompCapacity" : 0,
    "dataReductionAccelerateCompRate" : 0,
    "compressionRate" : 0,
    "dataReductionAccelerateCompIncludingSystemData" : {
      "isReductionCapacityAvailable" : true,
      "reductionCapacity" : 0,
      "isReductionRateAvailable" : false
    },
    "capacitiesExcludingSystemData" : {
      "usedVirtualVolumeCapacity" : 0
    }
  } ]
}"""

storage_ldevs = """ {
  "data" : [ {
    "ldevId" : 0,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "500.00 G",
    "blockCapacity" : 1048576000,
    "numOfPorts" : 4,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 1
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 1
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 1
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 1
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vg_test0",
    "status" : "NML",
    "mpBladeId" : 0,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 0,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  }, {
    "ldevId" : 1,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "400.00 G",
    "blockCapacity" : 838860800,
    "numOfPorts" : 4,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 2
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 2
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 2
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 1,
      "hostGroupName" : "demosrv.example.com",
      "lun" : 2
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vg_test1",
    "status" : "NML",
    "mpBladeId" : 1,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 0,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  }, {
    "ldevId" : 2,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "10.00 T",
    "blockCapacity" : 21474836480,
    "numOfPorts" : 52,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 6
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 6
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 6
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 6
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vmware_legacy_ssd0",
    "status" : "NML",
    "mpBladeId" : 0,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 9604460544,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  }, {
    "ldevId" : 3,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "10.00 T",
    "blockCapacity" : 21474836480,
    "numOfPorts" : 52,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 5
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 5
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 5
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 5
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vmware_legacy_ssd1",
    "status" : "NML",
    "mpBladeId" : 1,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 7754084352,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  }, {
    "ldevId" : 4,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "5.00 T",
    "blockCapacity" : 10737418240,
    "numOfPorts" : 52,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 4
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 4
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 4
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 4
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vmware_legacy_ssd2",
    "status" : "NML",
    "mpBladeId" : 0,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 5074944,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  }, {
    "ldevId" : 5,
    "clprId" : 0,
    "emulationType" : "OPEN-V-CVS",
    "byteFormatCapacity" : "5.00 T",
    "blockCapacity" : 10737418240,
    "numOfPorts" : 52,
    "ports" : [ {
      "portId" : "CL2-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 3
    }, {
      "portId" : "CL1-B",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 3
    }, {
      "portId" : "CL2-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 3
    }, {
      "portId" : "CL1-A",
      "hostGroupNumber" : 2,
      "hostGroupName" : "demosrv0803",
      "lun" : 3
    } ],
    "attributes" : [ "CVS", "HDP" ],
    "label" : "vmware_legacy_ssd3",
    "status" : "NML",
    "mpBladeId" : 1,
    "ssid" : "0004",
    "poolId" : 0,
    "numOfUsedBlock" : 1014042624,
    "isFullAllocationEnabled" : false,
    "resourceGroupId" : 0,
    "dataReductionStatus" : "DISABLED",
    "dataReductionMode" : "disabled",
    "isAluaEnabled" : false
  } ]
}"""

storage_parity_groups = """ {
  "data": [
    {
      "parityGroupId": "1-1",
      "numOfLdevs": 26,
      "usedCapacityRate": 44,
      "availableVolumeCapacity": 87245,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 91483790592
    },
    {
      "parityGroupId": "1-2",
      "numOfLdevs": 51,
      "usedCapacityRate": 93,
      "availableVolumeCapacity": 10448,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 10955611392
    },
    {
      "parityGroupId": "1-3",
      "numOfLdevs": 25,
      "usedCapacityRate": 42,
      "availableVolumeCapacity": 90317,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 94704917760
    },
    {
      "parityGroupId": "1-4",
      "numOfLdevs": 52,
      "usedCapacityRate": 95,
      "availableVolumeCapacity": 7376,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 7734484224
    },
    {
      "parityGroupId": "1-5",
      "numOfLdevs": 54,
      "usedCapacityRate": 99,
      "availableVolumeCapacity": 1232,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 1292229888
    },
    {
      "parityGroupId": "1-6",
      "numOfLdevs": 25,
      "usedCapacityRate": 42,
      "availableVolumeCapacity": 90317,
      "raidLevel": "RAID5",
      "raidType": "3D+1P",
      "clprId": 0,
      "driveType": "NFHAF-Q13RSS",
      "driveTypeName": "SSD(FMC)",
      "totalCapacity": 157286,
      "physicalCapacity": 39321,
      "isAcceleratedCompressionEnabled": true,
      "availableVolumeCapacityInKB": 94704917760
    }
  ]
}"""
if __name__ == "__main__":
    main()

