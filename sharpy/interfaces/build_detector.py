from abc import abstractmethod, ABC
import enum

from sc2.unit import Unit
from sc2.units import Units

class EnemyRushBuild(enum.IntEnum):
    Macro = 0
    Pool12 = 1
    CannonRush = 2
    ProxyRax = 3
    OneBaseRax = 4
    ProxyZealots = 5
    Zealots = 6
    OneHatcheryAllIn = 7
    PoolFirst = 8
    RoachRush = 9
    Marauders = 10
    HatchPool15_14 = 11
    ProxyRobo = 12
    RoboRush = 13
    AdeptRush = 14
    WorkerRush = 15
    Proxy_Unknown = 16


class EnemyMacroBuild(enum.IntEnum):
    StandardMacro = 0
    BattleCruisers = 1
    Banshees = 2
    Tempests = 3
    Carriers = 4
    DarkTemplars = 5
    Lurkers = 6
    Mutalisks = 7
    Mmm = 8


class IBuildDetector(ABC):
    rush_build: EnemyRushBuild
    macro_build:EnemyMacroBuild
    # @property
    # @abstractmethod
    # def rush_build(self) -> EnemyRushBuild:
    #     """Returns latest snapshot for all units that we know of but which are currently not visible."""
    #     pass

    # @property
    # @abstractmethod
    # def macro_build(self) -> EnemyMacroBuild:
    #     """Returns latest snapshot for all units that we know of but which are currently not visible."""
    #     pass