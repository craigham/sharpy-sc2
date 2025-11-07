from typing import TYPE_CHECKING
from enum import Enum, auto
from dataclasses import dataclass, field
from functools import cached_property
from collections.abc import Iterable
from loguru import logger
from sc2.position import Point2
from sc2.unit import Unit

from sharpy.combat import CombatUnits, MoveType
from sharpy.general.zone import Zone

from terranbot import utils

from terranbot.pathing import PathChoke, PathRamp

if TYPE_CHECKING:
    from terranbot.combat.combat_types import EngagementResult



