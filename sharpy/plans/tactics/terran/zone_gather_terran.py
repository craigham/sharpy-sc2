from typing import List, Optional
import py_trees
from py_trees.common import Status
import sc2
from sc2.ids.ability_id import AbilityId
from sharpy.interfaces import IGatherPointSolver, IUnitValues
from sharpy.interfaces.combat_manager import MoveType
from sharpy.plans.acts import ActBase
from sc2.ids.unit_typeid import UnitTypeId
from sc2.position import Point2
from sc2.unit import Unit

from sharpy.knowledges import Knowledge
import terranbot.trees.behaviours.general as bh_general 


# if terran opponent, split early bio between reaper jump near 3rd/4th and the ramp
#TODO handle criteria for each gather point?  eg. 1/2 of bio produced with max 4, etc
class SplitBioGatherPoints(bh_general.BotBehaviour):
    def __init__(self, namespace=None, name: str = None, gather_points:Optional[List[Point2]] = None):
        super().__init__(namespace, name or self.__class__.__name__)

    def setup(self, **kwargs: bh_general.Any) -> None:
        super().setup(**kwargs)
    
    
    def update(self) -> Status:
        return Status.RUNNING


def build_tree(ai):
    opponent_race_selector = py_trees.composites.Selector("Opponent Race Selector", memory=True)
    terran_sequence = py_trees.composites.Sequence("Terran Sequence", memory=False)
    default_sequence = py_trees.composites.Sequence("Default Sequence", memory=False)
    opponent_race_selector.add_child(terran_sequence, default_sequence)

    return py_trees.trees.BehaviourTree(opponent_race_selector)

class PlanZoneGatherTerran(ActBase):
    gather_point: Point2
    gather_set: List[int]
    gather_point_solver: IGatherPointSolver
    unit_values: IUnitValues

    def __init__(self):
        super().__init__()

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)
        self.gather_point_solver = knowledge.get_required_manager(IGatherPointSolver)
        self.unit_values = knowledge.get_required_manager(IUnitValues)
        self.gather_point = self.gather_point_solver.gather_point
        self.gather_set: List[int] = []

    async def execute(self) -> bool:
        random_variable = (self.ai.state.game_loop % 120) * 0.1
        random_variable *= 0.6
        unit: Unit
        if self.gather_point != self.gather_point_solver.gather_point:
            self.gather_set.clear()
            self.gather_point = self.gather_point_solver.gather_point
            main_ramp = self.zone_manager.own_main_zone.ramp
            if main_ramp and main_ramp.top_center.distance_to(self.gather_point) < 5:
                # Nudge gather point just a slightly further
                self.gather_point = main_ramp.top_center

        unit: Unit
        for unit in self.cache.own([UnitTypeId.BARRACKS, UnitTypeId.FACTORY]).tags_not_in(self.gather_set):
            # Rally point is set to prevent units from spawning on the wrong side of wall in
            pos: Point2 = unit.position
            pos = pos.towards(self.gather_point, 1)
            unit(AbilityId.RALLY_BUILDING, pos)
            self.gather_set.append(unit.tag)

        units = []
        units.extend(self.roles.idle)

        for unit in units:
            if self.unit_values.should_attack(unit):
                d = unit.position.distance_to(self.gather_point)
                if unit.type_id == UnitTypeId.SIEGETANK and d < random_variable:
                    ramp = self.zone_manager.expansion_zones[0].ramp
                    if unit.distance_to(ramp.bottom_center) > 5 and unit.distance_to(ramp.top_center) > 4:
                        unit(AbilityId.SIEGEMODE_SIEGEMODE)
                elif (d > 6.5 and unit.type_id != UnitTypeId.SIEGETANKSIEGED) or d > 9:
                    self.combat.add_unit(unit)

        self.combat.execute(self.gather_point, move_type=MoveType.DefensiveRetreat)
        return True  # Always non blocking
