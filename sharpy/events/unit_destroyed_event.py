from typing import Optional

from sc2.unit import Unit


class UnitDestroyedEvent:
    """An event indicating which unit just died."""

    def __init__(self, unit_tag: int, unit: Optional[Unit]):
        assert isinstance(unit_tag, int)
        assert isinstance(unit, Unit) or unit is None

        self.unit_tag: int = unit_tag
        self.unit: Optional[Unit] = unit

class UnitDamagedEvent:
    """An event indicating which unit just took damage."""

    def __init__(self, unit: Unit, damage:int):        
        assert isinstance(unit, Unit) or unit is None        
        self.unit: Unit = unit
        self.damage: int = damage