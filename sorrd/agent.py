from dataclasses import dataclass
from multiprocessing import Pool
from typing import List
from typing import Dict

from easysnmp import Session

from sorrd import utils


@dataclass
class SORRDAgent:
    """Agent for managing SNMP sessions"""

    workers: int = 1

    def __post_init__(self):
        return

    def collect(self, oid_configs: List[Dict]) -> List[int]:
        """Collect one value from each oid config
        :param oid_configs: List of oid configs
        """
        results = []
        with Pool(processes=self.workers) as pool:
            results = pool.map(self._spawn_proc, oid_configs)
        if len(results) != len(oid_configs):
            # TODO custom exception
            raise Exception("Some OIDs failed to collect")
        return results

    @staticmethod
    def _spawn_proc(oid_config: Dict) -> int:
        """Collect a value from a single oid
        :param oid_config: Config dict for an oid, expects host/community/oid keys
        """
        session = Session(
            hostname=oid_config["host"], community=oid_config["community"], version=2
        )
        # splitting these variables to ignore membership issues without multiline formatting
        oid_tuple = tuple(oid_config["oid"].split("."))
        oid_value = session.get(oid_tuple).value  # pylint: disable=no-member
        return utils.tryint(oid_value, default=0)
