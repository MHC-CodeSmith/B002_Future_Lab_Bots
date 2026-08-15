"""Funções puras para validar evidências dos sinais de missão em logs ROS."""

import re
from typing import Iterable, Optional


ROS_LOG_TIMESTAMP = re.compile(r"^\[[A-Z]+\] \[([0-9]+(?:\.[0-9]+)?)\]")


def latest_matching_timestamp(lines: Iterable[str], marker: str) -> Optional[float]:
    latest = None
    for line in lines:
        if marker not in line:
            continue
        match = ROS_LOG_TIMESTAMP.match(line)
        if match:
            measured = float(match.group(1))
            latest = measured if latest is None else max(latest, measured)
    return latest


def is_new_evidence(
    observed: Optional[float], previous: Optional[float]
) -> bool:
    return observed is not None and (previous is None or observed > previous)
