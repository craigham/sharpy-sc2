from enum import IntEnum, Flag,auto
import sys
from typing import Dict, List, TYPE_CHECKING

from sc2.data import Race
from sharpy.interfaces import IEnemyUnitsManager
from sharpy.managers.core.manager_base import ManagerBase

if TYPE_CHECKING:
    from sharpy.managers.core import *

from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from sc2.unit import Unit
from sc2.units import Units

townhall_start_types = {
    UnitTypeId.NEXUS,
    UnitTypeId.HATCHERY,
    UnitTypeId.COMMANDCENTER,
}

workers_types = {UnitTypeId.SCV, UnitTypeId.PROBE, UnitTypeId.DRONE}



class EnemyRushBuild(Flag):
    Macro = auto()
    Pool12 = auto()
    CannonRush = auto()
    ProxyRax = auto()
    OneBaseRax = auto()
    ProxyZealots = auto()
    Zealots = auto()
    OneHatcheryAllIn = auto()
    PoolFirst = auto()
    RoachRush = auto()
    Marauders = auto()
    HatchPool15_14 = auto()
    ProxyRobo = auto()
    RoboRush = auto()
    AdeptRush = auto()
    WorkerRush = auto()
    ProxyReaper = auto()
    ProxyMarauders = auto()
    ProxyRush = ProxyRax | ProxyZealots | ProxyRobo | ProxyReaper | ProxyMarauders


class EnemyMacroBuild(IntEnum):
    StandardMacro = 0
    BattleCruisers = 1
    Banshees = 2
    Tempests = 3
    Carriers = 4
    DarkTemplars = 5
    Lurkers = 6
    Mutalisks = 7
    Mmm = 8


class BuildDetector(ManagerBase):
    """Enemy build detector."""

    enemy_units_manager: IEnemyUnitsManager

    def __init__(self):
        super().__init__()
        self.rush_build = EnemyRushBuild.Macro
        self.macro_build = EnemyMacroBuild.StandardMacro

        # Dictionary of unit or structure types that have been handled. tag is key
        # Note that snapshots of units / structures have a different tag.
        # Only visible buildings should be handled
        self.handled_unit_tags: Dict[int, UnitTypeId] = dict()
        # Timings when the unit was first seen or our estimate when structure was started building
        self.timings: Dict[UnitTypeId, List[float]] = dict()

    async def start(self, knowledge: "Knowledge"):
        # Just put them all her in order to avoid any issues with random enemy types
        if knowledge.ai.enemy_race == Race.Terran:
            self.timings[UnitTypeId.COMMANDCENTER] = [0]
        elif knowledge.ai.enemy_race == Race.Protoss:
            self.timings[UnitTypeId.NEXUS] = [0]
        elif knowledge.ai.enemy_race == Race.Zerg:
            self.timings[UnitTypeId.HATCHERY] = [0]
        elif knowledge.ai.enemy_race == Race.Random:
            self.timings[UnitTypeId.COMMANDCENTER] = [0]
            self.timings[UnitTypeId.NEXUS] = [0]
            self.timings[UnitTypeId.HATCHERY] = [0]

        await super().start(knowledge)

        self.enemy_units_manager = knowledge.get_required_manager(IEnemyUnitsManager)
        self.distance_main_map_center = self.zone_manager.own_main_zone.center_location.distance_to(self.ai.game_info.map_center)

    @property
    def rush_detected(self):
        return self.rush_build != EnemyRushBuild.Macro

    @property
    def worker_rush_detected(self):
        return self.rush_build == EnemyRushBuild.WorkerRush

    async def update(self):
        self._detect_proxy()
        self._update_timings()
        self._rush_detection()
        self._build_detection()

    def _update_timings(self):
        # Let's update just seen structures for now
        for unit in self.ai.enemy_structures:
            if unit.is_snapshot:
                continue

            if unit.tag not in self.handled_unit_tags or self.handled_unit_tags.get(unit.tag) != unit.type_id:
                self.handled_unit_tags[unit.tag] = unit.type_id

                if self.is_first_townhall(unit):
                    continue  # Don't add it to timings

                real_type = self.real_type(unit.type_id)
                list = self.timings.get(real_type, None)
                if not list:
                    list = []
                    self.timings[real_type] = list

                start_time = self.unit_values.building_start_time(self.ai.time, real_type, unit.build_progress)
                list.append(start_time)

    def started(self, type_id: UnitTypeId, index: int = 0) -> float:
        """ Returns an absurdly large number when the building isn't started yet"""
        list = self.timings.get(type_id, None)
        if not list:
            return sys.float_info.max
        if len(list) > index:
            return list[index]
        return sys.float_info.max

    def is_first_townhall(self, structure: Unit) -> bool:
        """Returns true if the structure is the first townhall for a player."""
        # note: this does not handle a case if Terran flies its first CC to another position
        return (
            structure.position == self.zone_manager.enemy_start_location and structure.type_id in townhall_start_types
        )

    async def post_update(self):
        if self.debug:
            if self.rush_build != EnemyRushBuild.Macro:
                msg = f"Enemy build: {self.rush_build.name}"
            else:
                msg = f"Enemy build: {self.macro_build.name}"

            if hasattr(self.ai, "plan"):
                build_order = self.ai.plan
                if hasattr(build_order, "orders"):
                    plan = build_order.orders[0]
                    if hasattr(plan, "response"):
                        msg += f"\nOwn build: {plan.response.name}"
                    else:
                        msg += f"\nOwn build: {type(plan).__name__}"
            self.client.debug_text_2d(msg, Point2((0.75, 0.15)), None, 14)

    def _set_rush(self, value: EnemyRushBuild):
        if self.rush_build == value:
            # Trying to set the value to what it already was, skip.
            return
        self.rush_build = value
        self.print(f"POSSIBLE RUSH: {value.name}.")

    def _rush_detection(self):
        if self.ai.time > 180:
            # Past three minutes, early rushes no longer relevant
            return

        if self.rush_build == EnemyRushBuild.WorkerRush:
            # Worker rush can never change to anything else
            return

        workers_close = self.cache.enemy_workers.filter(
            lambda u: u.distance_to(self.ai.start_location) < u.distance_to(self.zone_manager.enemy_start_location)
        )

        if workers_close.amount > 9:
            self._set_rush(EnemyRushBuild.WorkerRush)

        if self.knowledge.enemy_race == Race.Zerg:
            self._zerg_rushes()

        if self.knowledge.enemy_race == Race.Terran:
            self._terran_rushes()

        if self.knowledge.enemy_race == Race.Protoss:
            self._protoss_rushes()

    def _protoss_rushes(self):
        if len(self.cache.enemy(UnitTypeId.NEXUS)) > 1:
            self._set_rush(EnemyRushBuild.Macro)
            return  # enemy has expanded, no rush detection
        only_nexus_seen = False

        for enemy_nexus in self.cache.enemy(UnitTypeId.NEXUS):  # type: Unit
            if enemy_nexus.position == self.zone_manager.enemy_main_zone.center_location:
                only_nexus_seen = True
            else:
                self._set_rush(EnemyRushBuild.Macro)
                return  # enemy has build expansion, no rush detection
        
        close_buildings = self.cache.enemy_in_range(self.ai.start_location, 80).structure
        if close_buildings:
            if close_buildings(UnitTypeId.ROBOTICSFACILITY):
                self._set_rush(EnemyRushBuild.ProxyRobo)
                return

        if self.ai.time < 125:
            # early game and we have seen enemy Nexus
            close_gateways = (
                self.ai.enemy_structures(UnitTypeId.GATEWAY)
                .closer_than(self.distance_main_map_center, self.zone_manager.own_main_zone.center_location)
                .amount
            )
            core = self.ai.enemy_structures(UnitTypeId.CYBERNETICSCORE).exists

            gates = self.cache.enemy(UnitTypeId.GATEWAY).amount
            robos = self.cache.enemy(UnitTypeId.ROBOTICSFACILITY).amount
            gas = self.cache.enemy(UnitTypeId.ASSIMILATOR).amount

            # if self.ai.time > 110 and close_gateways == 0 and not core and only_nexus_seen \
            #     or close_gateways > 1:
            #     self._set_rush(EnemyRushBuild.ProxyZealots)

            if gates > 2:
                if gas == 1:
                    self._set_rush(EnemyRushBuild.AdeptRush)
                elif gas == 0:
                    self._set_rush(EnemyRushBuild.Zealots)
            elif gates + robos > 2:
                self._set_rush(EnemyRushBuild.RoboRush)
            # if self.ai.enemy_structures(UnitTypeId.FORGE).exists:
            #     self._set_rush(EnemyRushBuild.CannonRush)

    def _terran_rushes(self):
        only_cc_seen = False

        for enemy_cc in self.cache.enemy(
            [UnitTypeId.COMMANDCENTER, UnitTypeId.ORBITALCOMMAND, UnitTypeId.PLANETARYFORTRESS]
        ):  # type: Unit
            if enemy_cc.position == self.zone_manager.enemy_main_zone.center_location:
                only_cc_seen = True
            else:
                return self._set_rush(EnemyRushBuild.Macro)  # enemy has expanded, no rush detection

        if self.ai.time < 120:
            # early game and we have seen enemy CC
            close_barracks = (
                self.ai.enemy_structures(UnitTypeId.BARRACKS)
                .closer_than(30, self.zone_manager.enemy_main_zone.center_location)
                .amount
            )

            barracks = self.ai.enemy_structures(UnitTypeId.BARRACKS).amount
            factories = self.ai.enemy_structures(UnitTypeId.FACTORY).amount

            if (
                self.ai.enemy_structures(UnitTypeId.BARRACKSTECHLAB).amount == barracks
                and barracks >= 1
                and factories == 0
            ):
                return self._set_rush(EnemyRushBuild.Marauders)

            if self.ai.time > 110 and close_barracks == 0 and factories == 0 and only_cc_seen:
                return self._set_rush(EnemyRushBuild.ProxyRax)

            if barracks + factories > 2:
                return self._set_rush(EnemyRushBuild.OneBaseRax)

    def _zerg_rushes(self):
        hatcheries: Units = self.cache.enemy(UnitTypeId.HATCHERY)
        if len(hatcheries) > 2 or self.enemy_units_manager.enemy_worker_count > 20:
            # enemy has expanded TWICE or has large amount of workers, that's no rush
            return self._set_rush(EnemyRushBuild.Macro)

        if self.building_started_before(UnitTypeId.ROACHWARREN, 130) or (
            self.ai.time < 160 and self.cache.enemy(UnitTypeId.ROACH)
        ):
            return self._set_rush(EnemyRushBuild.RoachRush)

        # 12 pool starts at 20sec
        # 13 pool starts at 23sec
        # 14 pool starts at 27sec
        if self.building_started_before(UnitTypeId.SPAWNINGPOOL, 26):
            return self._set_rush(EnemyRushBuild.Pool12)

        if self.building_started_before(UnitTypeId.SPAWNINGPOOL, 40):
            # Very early pool detected
            return self._set_rush(EnemyRushBuild.PoolFirst)

        if (
            self.ai.time > 120
            and self.ai.time < 130
            and self.ai.enemy_structures(UnitTypeId.HATCHERY).amount == 1
            and self.building_started_before(UnitTypeId.SPAWNINGPOOL, 70)
        ):
            return self._set_rush(EnemyRushBuild.OneHatcheryAllIn)

        # 12 pool zerglings are at 1min 22sec or 82 sec
        # 13 pool zerglings are at 1m 27sec or 87 sec
        if self.ai.enemy_units(UnitTypeId.ZERGLING):
            # todo: any kind of unit detection requires determining where they are on the map
            if self.ai.time < 92:
                # self.print(f"Early zerglings at {self.ai.time} seconds.")
                return self._set_rush(EnemyRushBuild.Pool12)

        if (
            self.started(UnitTypeId.HATCHERY, 1) < 50
            and self.started(UnitTypeId.EXTRACTOR) < 70
            and self.started(UnitTypeId.SPAWNINGPOOL) < 70
            and self.enemy_units_manager.enemy_worker_count < 17
            # and self.cache.enemy(UnitTypeId.LARVA).amount >= 3
        ):
            return self._set_rush(EnemyRushBuild.HatchPool15_14)

    def _build_detection(self):
        if self.macro_build != EnemyMacroBuild.StandardMacro:
            # Only set macro build once
            return

        if self.knowledge.enemy_race == Race.Terran:
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.BATTLECRUISER):
                self.macro_build = EnemyMacroBuild.BattleCruisers
            elif self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.BANSHEE):
                self.macro_build = EnemyMacroBuild.Banshees
            elif self.ai.time > 7 * 60 and self.ai.time < 8 * 60:
                mmm_check = (
                    self.enemy_units_manager.unit_count(UnitTypeId.MARINE)
                    > self.enemy_units_manager.unit_count(UnitTypeId.MARAUDER)
                    > 15
                    > self.enemy_units_manager.unit_count(UnitTypeId.MEDIVAC)
                    > 0
                )
                if mmm_check:
                    self.macro_build = EnemyMacroBuild.Mmm

        if self.knowledge.enemy_race == Race.Protoss:
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.TEMPEST):
                self.macro_build = EnemyMacroBuild.Tempests
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.CARRIER):
                self.macro_build = EnemyMacroBuild.Carriers
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.DARKTEMPLAR):
                self.macro_build = EnemyMacroBuild.DarkTemplars

        if self.knowledge.enemy_race == Race.Zerg:
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.MUTALISK):
                self.macro_build = EnemyMacroBuild.Mutalisks
            if self.ai.time < 7 * 60 and self.cache.enemy(UnitTypeId.LURKERMP):
                self.macro_build = EnemyMacroBuild.Lurkers

        if self.macro_build != EnemyMacroBuild.StandardMacro:
            self.print(f"Enemy normal build recognized as {self.macro_build.name}")
    
    def _detect_proxy(self):
        if self.macro_build != EnemyMacroBuild.StandardMacro:
            # Only set macro build once
            return
        
        # workers: Units = self.cache.enemy_workers.closer_than(20,self.zone_manager.enemy_main_zone.center_location)
        # if workers:
        #     pass
        #     self.print(f"# workers in enemy base: {workers.amount}")
        #     print(f"# workers in enemy base: {workers.amount}")
        

        # start by counting workers seen outside the main.
        # also when we have seen the main, should have a number of expected workers
        pass

    def building_started_before(self, type_id: UnitTypeId, start_time_ceiling: int) -> bool:
        """Returns true if a building of type type_id has been started before start_time_ceiling seconds."""
        for unit in self.cache.enemy(type_id):  # type: Unit
            # fixme: for completed buildings this will report a time later than the actual start_time.
            # not fatal, but may be misleading.
            start_time = self.unit_values.building_start_time(self.ai.time, unit.type_id, unit.build_progress)
            if start_time is not None and start_time < start_time_ceiling:
                return True

        return False
