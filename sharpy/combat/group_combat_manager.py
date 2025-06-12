from typing import List, Dict, Optional, Union
from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger
from sharpy.combat import *
from sharpy.general.extended_power import ExtendedPower
from sharpy.interfaces import ICombatManager
from sharpy.managers.core import UnitCacheManager, PathingManager, ManagerBase
from sharpy.combat import Action
from sc2.units import Units
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2, Point3
from sc2.unit import Unit
import numpy as np
from sklearn.cluster import DBSCAN

from terranbot.combat.simulator import EngagementResult
from terranbot.pathing import PathChoke, PathRamp

ignored = {UnitTypeId.MULE, UnitTypeId.LARVA, UnitTypeId.EGG}


class MilitaryActionType(Enum):
    ATTACK_ENEMY_BASE = auto()
    SIEGE_LOCATION = auto()
    ATTACK_ENEMY_PROXY_LOCATION = auto()
    JOIN_ARMY = auto()

@dataclass(unsafe_hash=True)
class MilitaryTarget:
    target:Point2
    action_type: MilitaryActionType
    context:dict[str, object] = field(default_factory=dict, init=False, compare=False)

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
    expected_engagement_result:EngagementResult|None = field(init=False, default=None)


class GroupCombatManager(ManagerBase, ICombatManager):
    rules: MicroRules

    def __init__(self):
        super().__init__()
        self.default_rules = MicroRules()
        self.default_rules.load_default_methods()
        self.default_rules.load_default_micro()
        self.enemy_group_distance = 7
        self.military_action = None

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.cache: UnitCacheManager = self.knowledge.unit_cache
        self.pather: PathingManager = self.knowledge.pathing_manager
        self._tags: List[int] = []
        self.all_enemy_power = ExtendedPower(self.unit_values)

        await self.default_rules.start(knowledge)

    @property
    def tags(self) -> List[int]:
        return self._tags

    @property
    def regroup_threshold(self) -> float:
        """ Percentage 0 - 1 on how many of the attacking units should actually be together when attacking"""
        return self.rules.regroup_percentage

    @property
    def own_group_threshold(self) -> float:
        """
        How much distance must be between units to consider them to be in different groups
        """
        return self.rules.own_group_distance

    @property
    def unit_micros(self) -> Dict[UnitTypeId, MicroStep]:
        return self.rules.unit_micros

    @property
    def generic_micro(self) -> MicroStep:
        return self.rules.generic_micro

    async def update(self):
        self.enemy_groups: List[CombatUnits] = self.group_enemy_units()
        self.all_enemy_power.clear()

        for group in self.enemy_groups:  # type: CombatUnits
            self.all_enemy_power.add_units(group.units)

    async def post_update(self):
        pass

    @property
    def debug(self):
        return self._debug and self.knowledge.debug

    def add_unit(self, unit: Unit):
        if unit.type_id in ignored or unit.tag in self._tags:  # Just no
            return

        self._tags.append(unit.tag)

    def add_units(self, units: Units):
        for unit in units:
            self.add_unit(unit)

    def get_all_units(self) -> Units:        
        return self.cache.by_tags(self._tags)

    def execute_military_action(self, action: MilitaryAction, rules: MicroRules|None = None):
        self.military_action = action
        self.execute(action.action_info.target, action.move_type, rules)
        self.military_action = None

    def execute(self, target: Point2, move_type=MoveType.Assault, rules: Optional[MicroRules] = None):
        our_units = self.get_all_units()
        if len(our_units) < 1:
            return

        self.rules = rules if rules else self.default_rules

        self.own_groups: List[CombatUnits] = self.group_own_units(our_units)

        if self.debug:
            fn = lambda group: group.center.distance_to(self.ai.start_location)
            sorted_list = sorted(self.own_groups, key=fn)
            for i in range(0, len(sorted_list)):
                sorted_list[i].debug_index = i

        self.rules.handle_groups_func(combat=self, target=target, move_type=move_type)

        self._tags.clear()

    def faster_group_should_regroup(self, group1: CombatUnits, group2: Optional[CombatUnits]) -> bool:
        if not group2:
            return False
        if group1.average_speed < group2.average_speed + 0.1:
            return False
        # Our group is faster, it's a good idea to regroup
        return True

    def regroup(self, group: CombatUnits, target: Union[Unit, Point2]):
        if isinstance(target, Unit):
            target = self.pather.find_path(group.center, target.position, 1)
        else:
            target = self.pather.find_path(group.center, target, 3)
        self.move_to(group, target, MoveType.Push)

    def move_to(self, group: CombatUnits, target, move_type: MoveType):
        logger.debug(f'move_to: {target=} {move_type=}')
        self.action_to(group, target, move_type, False)

    def attack_to(self, group: CombatUnits, target, move_type: MoveType):
        logger.debug(f'attack_to: {target=} {move_type=}')
        self.action_to(group, target, move_type, True)

    def action_to(self, group: CombatUnits, target, move_type: MoveType, is_attack: bool):
        original_target = target
        if isinstance(target, Point2) and group.ground_units:
            if move_type in {MoveType.DefensiveRetreat, MoveType.PanicRetreat}:
                target = self.pather.find_influence_ground_path(group.center, target, 14)
            else:
                target = self.pather.find_path(group.center, target, 14)

        own_unit_cache: Dict[UnitTypeId, Units] = {}

        for unit in group.units:
            real_type = self.unit_values.real_type(unit.type_id)
            units = own_unit_cache.get(real_type, Units([], self.ai))
            if units.amount == 0:
                own_unit_cache[real_type] = units

            units.append(unit)

        for type_id, type_units in own_unit_cache.items():
            micro: MicroStep = self.unit_micros.get(type_id, self.generic_micro)
            micro.init_group(self.rules, group, type_units, self.enemy_groups, move_type, original_target)
            group_action = micro.group_solve_combat(type_units, Action(target, is_attack))

            for unit in type_units:
                final_action = micro.unit_solve_combat(unit, group_action)
                final_action.to_commmand(unit)

                if self.debug:
                    if final_action.debug_comment:
                        status = final_action.debug_comment
                    elif final_action.ability:
                        status = final_action.ability.name
                    elif final_action.is_attack:
                        status = "Attack"
                    else:
                        status = "Move"
                    if final_action.target is not None:
                        if isinstance(final_action.target, Unit):
                            status += f": {final_action.target.type_id.name}"
                        else:
                            status += f": {final_action.target}"

                    status += f" G: {group.debug_index}"
                    status += f"\n{move_type.name}"

                    pos3d: Point3 = unit.position3d
                    pos3d = Point3((pos3d.x, pos3d.y, pos3d.z + 2))
                    self.ai._client.debug_text_world(status, pos3d, size=10)

    def closest_group(
        self,
        start: Point2,
        combat_groups: List[CombatUnits],
        group_center: Optional[Point2] = None,
        distance: float = 50,
    ) -> Optional[CombatUnits]:
        group = None
        best_distance = distance  # doesn't find enemy groups closer than this

        if group_center is None:
            group_center = start

        for combat_group in combat_groups:
            center = combat_group.center

            if center == group_center:
                continue  # it's the same group!

            distance = start.distance_to(center)
            if distance < best_distance:
                best_distance = distance
                group = combat_group

        return group
    
    def group_own_units(self, units: Units, eps=None) -> List[CombatUnits]:
        groups: List[Units] = []

        eps = eps or self.enemy_group_distance
        numpy_vectors: List[np.ndarray] = []
        for unit in units:
            numpy_vectors.append(np.array([unit.position.x, unit.position.y]))

        if numpy_vectors:
            clustering = DBSCAN(eps=eps, min_samples=1, algorithm="kd_tree").fit(numpy_vectors)
            # print(clustering.labels_)

            for index in range(0, len(clustering.labels_)):
                unit = units[index]
                if unit.type_id in self.unit_values.combat_ignore:
                    continue

                label = clustering.labels_[index]

                if label >= len(groups):
                    groups.append(Units([unit], self.ai))
                else:
                    groups[label].append(unit)
            # for label in clustering.labels_:

        # ns_pf = time.perf_counter_ns() - ns_pf
        # print(f"Own unit grouping (v2) took {ns_pf / 1000 / 1000} ms. groups: {len(groups)} units: {len(units)}")

        return [CombatUnits(u, self.knowledge) for u in groups]

    def group_enemy_units(self) -> List[CombatUnits]:
        groups = defaultdict(list)

        import time

        ns_pf = time.perf_counter_ns()

        if self.cache.enemy_numpy_vectors:
            clustering = DBSCAN(eps=self.enemy_group_distance, min_samples=1, algorithm="kd_tree").fit(self.cache.enemy_numpy_vectors)
            # print(clustering.labels_)
            units = self.ai.all_enemy_units
            for index in range(0, len(clustering.labels_)):
                unit = units[index]
                if unit.type_id in self.unit_values.combat_ignore or not unit.can_be_attacked:
                    continue

                label = clustering.labels_[index]                
                groups[label].append(unit)
            # for label in clustering.labels_:
        ns_pf = time.perf_counter_ns() - ns_pf
        logger.debug(f"Enemy unit grouping (v2) took {ns_pf / 1000 / 1000} ms. groups: {len(groups)}")
        return [CombatUnits(Units(u, bot_object=self.ai), knowledge=self.knowledge) for u in groups.values()]
