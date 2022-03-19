"""Command-line interface module"""
from typing import List
import signal
import time
import sys

import click
from easysnmp import Session
import rrdtool
import toml

from sorrd import utils

REQ_EXIT = False


@click.command()
@click.option("--db", help="DB Name")
@click.option("--rate", help="How often to poll the device in seconds")
@click.option("--addr", help="Device address")
@click.option("--module", help="Use a preset configured module")
@click.option(
    "--config",
)
@click.option(
    "--oids",
    help="List of oids, format: OID:DSTYPE, ex. ifInOctets.12:COUNTER:TRANSFORM",
)
def sorrd_cli(db: str, rate: str, addr: str, config: str, module: str, oids: List[str]):
    """SORRD CLI"""

    if module and oids:
        print("Can only provide modules or oid list")
        sys.exit()
    if oids:
        config = {"cli-generated": {"oids": []}}
        for oid in oids:
            oid_parts = oid.strip().split(":")
            config["cli-generated"]["oids"].append(
                {"oid": oid_parts[0], "dstype": oid_parts[1]}
            )
    elif module:
        config = toml.load(config)

    # we handle sigint to avoid blowing up the db on exit
    signal.signal(signal.SIGINT, sigint_handler)

    # generate a data source per oid
    data_sources = []
    for oid in config[module]["oids"]:
        data_sources.append(f"DS:{oid['label']}:{oid['dstype']}:60:U:U")
    # load secrets
    # TODO provide this from the config/elsewhere
    secrets = toml.load("/opt/secrets.toml")

    # DB / SNMP setup
    db_path = f"{db}.rrd"
    session = Session(hostname=addr, community=secrets["SNMP_COMMUNITY"], version=2)
    rrdtool.create(
        db_path, "--start", "now", "--step", rate, "RRA:LAST:0.5:1:1000", *data_sources
    )
    dbstart = int(time.time())

    # main loop
    while not REQ_EXIT:
        rrd_update_str = "N"
        for oid in config[module]["oids"]:
            oid_value = utils.tryint(
                session.get(tuple(oid["oid"].split("."))).value, default=0
            )
            rrd_update_str += f":{int(oid_value)}"

        rrdtool.update(db_path, rrd_update_str)
        time.sleep(int(rate))
    dbstop = int(time.time())

    # create defs/labels per oid
    output_defs = []
    for idx, oid in enumerate(config[module]["oids"]):
        output_defs.append(f"DEF:def_{oid['label']}={db_path}:{oid['label']}:LAST")
        if oid.get("cdef"):
            # generate cdefs, feed into line defs
            output_defs.append(
                f"CDEF:cdef_{oid['label']}=def_{oid['label']},{oid['cdef']}"
            )
            line_def = f"cdef_{oid['label']}"
        else:
            line_def = f"def_{oid['label']}"
        output_defs.append(f"LINE{idx+1}:{line_def}#FF0000:{oid['label']}")

    # dump graph
    rrdtool.graph(
        f"{db}.graph.png",
        "--start",
        str(dbstart),
        "--end",
        str(dbstop),
        *output_defs,
        "--units-exponent",  # TODO optional
        "0",
    )


def sigint_handler(
    sig,
    frame,
):
    global REQ_EXIT
    print(
        "Cleaning up and printing the graph, you'll need to wait a maximum of the number of seconds you set for the rate..."
    )
    REQ_EXIT = True
