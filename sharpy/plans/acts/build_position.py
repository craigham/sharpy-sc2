from typing import List, Optional, Set

from sharpy.plans.acts import ActBase
from sharpy.managers.core.roles import UnitTask
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from sc2.ids.ability_id import AbilityId
from sc2.unit import Unit
from sharpy.interfaces import IBuildingSolver, IIncomeCalculator
from sharpy.sc2math import to_new_ticks

worker_trainers = {AbilityId.NEXUSTRAIN_PROBE, AbilityId.COMMANDCENTERTRAIN_SCV}
depot_aliases = {UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOTLOWERED, UnitTypeId.SUPPLYDEPOTDROP}
buildings_w_addons = {UnitTypeId.BARRACKS, UnitTypeId.FACTORY, UnitTypeId.STARPORT}
footprint_2x2 = {
    UnitTypeId.SUPPLYDEPOT,
    UnitTypeId.SUPPLYDEPOTLOWERED,
    UnitTypeId.SUPPLYDEPOTDROP,
    UnitTypeId.PYLON,
}
NO_SOLVER_SLOT_LOG_INTERVAL_SEC = 5.0


class BuildPosition(ActBase):
    income_calculator: IIncomeCalculator
    building_solver: IBuildingSolver
    last_iteration_moved: int

    def __init__(self, unit_type: UnitTypeId, position: Point2, exact: bool = True, only_once: bool = False):
        super().__init__()
        self.exact = exact
        self.position = position
        self.unit_type = unit_type
        self.only_once = only_once
        self.builder_tag: Optional[int] = None
        self.last_iteration_moved = -10
        self.consider_worker_production = True
        self._resolved_position: Optional[Point2] = None
        self._last_no_slot_log_time: float = -NO_SOLVER_SLOT_LOG_INTERVAL_SEC

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.income_calculator = self.knowledge.get_required_manager(IIncomeCalculator)
        self.building_solver = self.knowledge.get_required_manager(IBuildingSolver)

    def _match_types(self):
        if self.unit_type == UnitTypeId.SUPPLYDEPOT:
            return depot_aliases
        return self.unit_type

    def _completion_anchors(self) -> List[Point2]:
        anchors: List[Point2] = []
        if self.position is not None:
            anchors.append(self.position)
        if self._resolved_position is not None and self._resolved_position not in anchors:
            anchors.append(self._resolved_position)
        return anchors

    def _structure_near_anchors(self) -> bool:
        match_types = self._match_types()
        for building in self.cache.own(match_types):  # type: Unit
            for anchor in self._completion_anchors():
                if building.distance_to(anchor) < 2:
                    return True
        return False

    async def _is_placeable(self, position: Point2) -> bool:
        return bool(await self.ai.can_place_single(self.unit_type, position))

    def _solver_candidate_points(self) -> List[Point2]:
        if self.unit_type in footprint_2x2:
            return list(self.building_solver.buildings2x2)
        if self.unit_type == UnitTypeId.COMMANDCENTER:
            return list(getattr(self.building_solver, "buildings5x5", []) or [])
        return list(self.building_solver.buildings3x3)

    async def _find_building_solver_slot(self) -> Optional[Point2]:
        buildings = self.ai.structures
        reserved_landing_locations: Set[Point2] = set(self.building_solver.structure_target_move_location.values())
        free_addon_locations = getattr(self.building_solver, "free_addon_locations", set()) or set()

        for point in self._solver_candidate_points():
            if point in reserved_landing_locations:
                continue
            if point in free_addon_locations:
                continue
            if buildings.closer_than(1, point):
                continue
            if self.unit_type in buildings_w_addons:
                add_on_center: Point2 = point.offset((2.5, -0.5))
                if not await self.ai.can_place_single(UnitTypeId.SUPPLYDEPOT, add_on_center):
                    continue
            if not await self._is_placeable(point):
                continue
            return point
        return None

    def _log_no_building_solver_slot(self) -> None:
        now = float(getattr(self.ai, "time", 0.0) or 0.0)
        if now - self._last_no_slot_log_time < NO_SOLVER_SLOT_LOG_INTERVAL_SEC:
            return
        self._last_no_slot_log_time = now
        own_count = len(self.cache.own(self._match_types()))
        self.print(
            "BuildPosition placement failed reason=no_building_solver_slot "
            f"unit_type={self.unit_type.name} requested={self.position} exact={self.exact} own_count={own_count}"
        )

    async def _resolve_build_position(self) -> Optional[Point2]:
        if self._resolved_position is not None:
            if await self._is_placeable(self._resolved_position):
                return self._resolved_position
            self._resolved_position = None

        requested = self.position
        if requested is None:
            return None

        if self.exact:
            if await self._is_placeable(requested):
                self._resolved_position = requested
                return requested
        else:
            found = await self.ai.find_placement(self.unit_type, requested, 20)
            if found is not None and await self._is_placeable(found):
                self._resolved_position = found
                self.position = found
                return found

        slot = await self._find_building_solver_slot()
        if slot is None:
            self._log_no_building_solver_slot()
            return None
        self._resolved_position = slot
        return slot

    async def execute(self) -> bool:
        if self.position is None:
            return True

        if self._structure_near_anchors():
            if self.only_once:
                self.position = None
                self._resolved_position = None
            return True

        position = await self._resolve_build_position()
        if position is None:
            return False

        worker = self.get_worker_builder(position, self.builder_tag)
        if worker is None:
            return True  # No worker to build with.

        if self.knowledge.can_afford(self.unit_type, check_supply_cost=False) and worker.distance_to(position) < 5:
            if await self._is_placeable(position):
                self.print(f"Building {self.unit_type.name} to {position}")
                worker.build(self.unit_type, position)
                self.set_worker(worker)
            else:
                # Cached/exact became invalid mid-frame; clear and retry next execute.
                self._resolved_position = None
        else:
            unit = self.ai._game_data.units[self.unit_type.value]
            cost = self.ai._game_data.calculate_ability_cost(unit.creation_ability)
            adjusted_income = self.income_calculator.mineral_income * 0.93  # 14 / 15 = 0.933333
            d = worker.distance_to(position)
            time = d / to_new_ticks(worker.movement_speed)
            if self.last_iteration_moved >= self.knowledge.iteration - 1:
                # stop indecisiveness
                time += 5

            available_minerals = self.ai.minerals - self.knowledge.reserved_minerals
            available_gas = self.ai.vespene - self.knowledge.reserved_gas

            if self.consider_worker_production and adjusted_income > 0:
                for town_hall in self.ai.townhalls:  # type: Unit
                    # TODO: Zerg(?)
                    if town_hall.orders:
                        starting_next_probe_in = -50 / adjusted_income
                        order = town_hall.orders[0]  # Only consider first order
                        if order.ability.id in worker_trainers:
                            starting_next_probe_in += 12 * (1 - order.progress)

                        if starting_next_probe_in < time:
                            available_minerals -= 50  # should start producing workers soon now
                    else:
                        available_minerals -= 50  # should start producing workers soon now

            if (
                available_minerals + time * adjusted_income >= cost.minerals
                and available_gas + time * self.income_calculator.gas_income >= cost.vespene
            ):
                # Go wait
                self.set_worker(worker)
                self.knowledge.reserve(cost.minerals, cost.vespene)

                if not self.has_build_order(worker):
                    worker.move(position)
                    self.last_iteration_moved = self.knowledge.iteration

        return False

    def set_worker(self, worker: Unit):
        self.roles.set_task(UnitTask.Building, worker)
        self.builder_tag = worker.tag
