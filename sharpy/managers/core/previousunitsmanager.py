from typing import Dict, Optional, NamedTuple, Iterator
from collections.abc import Iterable
from collections import defaultdict, deque
from sc2.position import Point2
from sharpy.interfaces import IPreviousUnitsManager
from sharpy.managers.core import ManagerBase
from sc2.unit import Unit
from sc2.units import Units

DamageReading = NamedTuple('DamageReading', [('health_percentage', float), ('game_step', int)]) 

# class UnitsHealthTracker(object):
#     def __init__(self, ai, max_len:int=10):
#         self.ai = ai
#         self.max_len:int = max_len
#         self.max_age:int = max_len * ai.client.game_step
#         self.history:dict[int, deque[DamageReading]] = defaultdict(lambda: deque(maxlen=max_len))

#     def track(self, units:Units)->None:
#         # expire old readings
#         # self.ai.state.game_loop
#         # self.ai.client.game_step
#         current_game_step = self.ai.state.game_loop

#         for _, readings in self.history.items():            
#             if readings[0].game_step < current_game_step - self.max_age:
#                 _ = readings.popleft()

#         for unit in units:
#             self.history[unit.tag].append(DamageReading(unit.health_percentage, current_game_step))

#     def units_taking_damage(self)->Iterator[Unit]:
#         print(self.history)


class PreviousUnitsManager(ManagerBase, IPreviousUnitsManager):
    """Keeps track of units from the previous iteration. Useful for checking eg. which unit died."""

    def __init__(self):
        super().__init__()
        self.previous_units: Dict[int, Unit] = dict()
        self.history:dict[int, deque[DamageReading]] = defaultdict(lambda: deque(maxlen=10))

    async def start(self, knowledge: "Knowledge"):
        await super().start(knowledge)

    async def update(self):
        pass

    def last_unit(self, tag: int) -> Optional[Unit]:
        return self.previous_units.get(tag, None)

    def last_position(self, unit: Unit) -> Point2:
        """
        Return unit position in last frame, or current if unit was just created.
        """
        previous_unit = self.previous_units.get(unit.tag, unit)
        return previous_unit.position

    async def post_update(self):
        """Updates previous units so we know what they are on the next iteration.
        Needs to be run right before the end of an iteration."""
        self.previous_units = dict()

        for unit in self.ai.all_units:  # type: Unit
            self.previous_units[unit.tag] = unit
            self.history[unit.tag].append(DamageReading(unit.health_percentage, self.ai.state.game_loop))
