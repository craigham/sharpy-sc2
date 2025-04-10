from sc2.ids.unit_typeid import UnitTypeId
from sc2pathlib import MapType, Sc2Map
from sharpy.managers import ManagerBase
from sharpy.managers.core import PathingManager


class EnemyVisionManager(ManagerBase):
    map: Sc2Map
    pather: PathingManager

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.pather = knowledge.get_required_manager(PathingManager)
        self.map = self.pather.map

    async def update(self):
        self.map.clear_vision()
        for unit in self.ai.all_enemy_units:
            if unit.type_id == UnitTypeId.NEXUS:
                sight_range = unit.radius + 2
            else:
                sight_range = unit.sight_range
            self.map.add_vision_params(unit.is_detector, unit.is_flying, unit.position, sight_range)
        self.map.calculate_vision()

    async def post_update(self):
        if self.debug:
            self.map.plot_vision()
