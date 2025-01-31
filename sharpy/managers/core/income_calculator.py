from sharpy.interfaces import IIncomeCalculator
from sharpy.managers.core.manager_base import ManagerBase
from sc2.unit import Unit

MINERAL_MINE_RATE = 1  # this isn't needed in calculations
GAS_MINE_RATE = 0.9433962264


class IncomeCalculator(ManagerBase, IIncomeCalculator):
    def __init__(self):
        super().__init__()
        self._mineral_income = 0
        self._gas_income = 0
        self.use_ingame = False

        self.last_mineral_use_amount = 0
        self.last_mineral_use_sample_time = 0
        self.last_rate = 0
    @property
    def mineral_income(self):
        return self._mineral_income

    @property
    def gas_income(self):
        return self._gas_income

    async def update(self):
        if self.ai.time -2 > self.last_mineral_use_sample_time:
            last_timed_rate = (self.ai.state.score.collected_minerals - self.last_mineral_use_amount)/(self.ai.time - self.last_mineral_use_sample_time)
            smoothed_rate = (last_timed_rate + self.last_rate)/2
            self.last_mineral_use_amount = self.ai.state.score.collected_minerals
            self.last_mineral_use_sample_time = self.ai.time
            self.last_rate = smoothed_rate
        
        # print(f"Game state mineral collection rate: {self.ai.state.score.collection_rate_minerals / 60}")
        
        # print(f"Collected minerals: {self.ai.state.score.collected_minerals}")
        if self.use_ingame:            
            self._mineral_income = self.ai.state.score.collection_rate_minerals/ 60            
            self._gas_income = self.ai.state.score.collection_rate_vespene / 60
        else:
            self._mineral_income = self.mineral_rate_calc()
            self._gas_income = self.vespene_rate_calc()

        # TODO: Calculate enemy income and minerals harvested here

    def mineral_rate_calc(self) -> float:
        # rate = 0
        # nexus: Unit
        # for nexus in self.ai.townhalls:
        #     rate += min(nexus.assigned_harvesters, nexus.ideal_harvesters)
        #     rate += max(nexus.assigned_harvesters - nexus.ideal_harvesters, 0) * 0.5  # half power mining?
        # With two workers per mineral patch, a large node with 1800 minerals will exhaust after 15 minutes
        # multiplier = 1800.0 / 60 / 15 / 2 => 1
        
        if self.ai.time < 30:
            factor = 1.5
        elif self.ai.time > 60:
            factor = 1.25
        else:
            factor = 1
        return self.last_rate * factor

    def vespene_rate_calc(self) -> float:
        rate = 0
        vespene_miner: Unit
        for vespene_miner in self.knowledge.unit_cache.own(self.unit_values.gas_miners):
            rate += min(vespene_miner.assigned_harvesters, vespene_miner.ideal_harvesters)
        # A standard vespene geyser contains 2250 gas and will exhaust after 13.25 minutes of saturated extraction.
        # multiplier = 2250 / 60 / 13.25 / 3 => 0.94339622641509433962264150943396
        return rate * GAS_MINE_RATE

    async def post_update(self):
        pass
