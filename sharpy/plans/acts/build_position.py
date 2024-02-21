from typing import Optional

from sharpy.plans.acts import ActBase
from sharpy.managers.core.roles import UnitTask
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from sc2.ids.ability_id import AbilityId
from sc2.unit import Unit
from sharpy.interfaces import IIncomeCalculator
from sharpy.sc2math import to_new_ticks

worker_trainers = {AbilityId.NEXUSTRAIN_PROBE, AbilityId.COMMANDCENTERTRAIN_SCV}
depot_aliases = {UnitTypeId.SUPPLYDEPOT, UnitTypeId.SUPPLYDEPOTLOWERED, UnitTypeId.SUPPLYDEPOTDROP}
class BuildPosition(ActBase):
    income_calculator: IIncomeCalculator
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
    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.income_calculator = self.knowledge.get_required_manager(IIncomeCalculator)

    async def execute(self) -> bool:
        if self.position is None:
            return True
        unit_type = self.unit_type
        if unit_type == UnitTypeId.SUPPLYDEPOT:
            unit_type = depot_aliases
        for building in self.cache.own(unit_type):  # type: Unit
            if building.distance_to(self.position) < 2:
                if self.only_once:
                    self.position = None
                return True

        position = self.position

        worker = self.get_worker_builder(position, self.builder_tag)
        if worker is None:
            return True  # No worker to build with.

        if self.knowledge.can_afford(self.unit_type, check_supply_cost=False) and worker.distance_to(position) < 5:
            if not self.exact:
                self.position = await self.ai.find_placement(self.unit_type, self.position, 20)
                position = self.position

            if position is not None:
                self.print(f"Building {self.unit_type.name} to {position}")
                worker.build(self.unit_type, position)
                self.set_worker(worker)
            else:
                self.print(f"Could not build {self.unit_type.name} to {position}")
        else:
            unit = self.ai._game_data.units[self.unit_type.value]
            cost = self.ai._game_data.calculate_ability_cost(unit.creation_ability)
            adjusted_income = self.income_calculator.mineral_income * 0.93  # 14 / 15 = 0.933333
            # print(f"Build position income measurement: {adjusted_income}")
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
