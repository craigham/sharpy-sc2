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

class MilitaryActionType(Enum):
    ATTACK_ENEMY_BASE = auto()
    SIEGE_LOCATION = auto()
    ATTACK_ENEMY_PROXY_LOCATION = auto()
    JOIN_ARMY = auto()
    ATTACK_ENEMY_UNITS = auto()

class ArmyEncounterType(Enum):
    GROUND_VS_GROUND = auto()
    GROUND_VS_AIR = auto()
    AIR_VS_AIR = auto()
    AIR_VS_GROUND = auto()


@dataclass(unsafe_hash=True)
class MilitaryTarget:
    target:Point2|CombatUnits|Zone
    action_type: MilitaryActionType
    context:dict[str, object] = field(default_factory=dict, init=False, compare=False)
    
    @cached_property
    def target_position(self)->Point2:
        if isinstance(self.target, Point2):
            return self.target
        elif isinstance(self.target, CombatUnits):
            return self.target.units.first.position
        else:
            return self.target.center_location

    def categorize_squad_target(self, army:CombatUnits)->ArmyEncounterType:
        logger.debug(utils.log_format(f'Categorizing squad target: {self.target} {army}'))
        us_air_only = army.ground_units.amount == 0
        logger.debug(f'{us_air_only=} - {isinstance(self.target, CombatUnits)=}')
        if isinstance(self.target, CombatUnits):
            enemy_air_only = self.target.ground_units.amount == 0
            logger.debug(f'{enemy_air_only=}')
            if us_air_only:
                return ArmyEncounterType.AIR_VS_AIR if enemy_air_only else ArmyEncounterType.AIR_VS_GROUND            
            else:
                return ArmyEncounterType.GROUND_VS_AIR if enemy_air_only else ArmyEncounterType.GROUND_VS_GROUND 
        else:
            if us_air_only:
                return ArmyEncounterType.AIR_VS_GROUND
            else:
                return ArmyEncounterType.GROUND_VS_GROUND

@dataclass
class MilitaryAction:
    action_info: MilitaryTarget    
    move_type: MoveType
    expected_path: Iterable[tuple[int,int]]|None = field(init=False, default=None, repr=False)
    army_center_unit:Unit|None = field(init=False, default=None)
    walk_distance_to_target:float|None = field(init=False, default=None)
    distance_closest_significant_army:float|None = field(init=False, default=float('inf'))
    youngest_age_enemy_army:int|None = field(init=False, default=None)
    next_up_ramp:PathRamp|None = field(init=False, default=None)
    next_down_ramp:PathRamp|None = field(init=False, default=None)
    previous_down_ramp:PathRamp|None = field(init=False, default=None)
    next_choke:PathChoke|None = field(init=False, default=None)
    bio_positions:dict[int, Point2]|None = field(init=False, default=None)
    expected_engagement_result:"EngagementResult|None" = field(init=False, default=None)

