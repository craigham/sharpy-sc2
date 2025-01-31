import logging
import string
import sys
from configparser import ConfigParser
from typing import Any, Optional

from loguru import logger

from sc2.main import logger as sc2_logger
from sharpy.interfaces import ILogManager
from .manager_base import ManagerBase




class LogManager(ManagerBase, ILogManager):
    config: ConfigParser
    logger: Any  # TODO: type?
    start_with: Optional[str]

    def __init__(self) -> None:
        super().__init__()
        self.start_with = None

    async def start(self, knowledge: "Knowledge"):
        self.setup_loguru(knowledge)
        await super().start(knowledge)
        self.logger = logger
        self.config = knowledge.config

    async def update(self):
        pass

    async def post_update(self):
        pass

    def print(self, message: string, tag: string = None, stats: bool = True, log_level=logging.INFO):
        """
        Prints a message to log.

        :param message: The message to print.
        :param tag: An optional tag, which can be used to indicate the logging component.
        :param stats: When true, stats such as time, minerals, gas, and supply are added to the log message.
        :param log_level: Optional logging level. Default is INFO.
        """

        if self.ai.run_custom and self.ai.player_id != 1 and not self.ai.realtime:
            # No logging for player 2 in custom games
            return

        if tag is not None:
            debug_log = self.config["debug_log"]
            enabled = debug_log.getboolean(tag, fallback=True)
            if not enabled:
                return

        if tag is not None:
            message = f"[{tag}] {message}"

        if stats:
            last_step_time = round(self.ai.step_time[3])

            message = (
                # f"{self.ai.time_formatted.rjust(5)} {str(last_step_time).rjust(4)}ms "
                # f"{str(self.ai.minerals).rjust(4)}M {str(self.ai.vespene).rjust(4)}G "
                f"{message}"
            )

        if self.start_with:
            message = self.start_with + message
        self.logger.log(log_level, message)

    def setup_loguru(self, knowledge):
        def formatter(record):
            last_step_time = round(self.ai.step_time[3])
            message = (f"{knowledge.ai.time_formatted.rjust(5)} {str(knowledge.ai.state.game_loop).rjust(4)} {str(last_step_time).rjust(4)}ms  ",
                       f"{str(knowledge.ai.minerals).rjust(4)}M {str(knowledge.ai.vespene).rjust(4)}G ",
                       f"{str(knowledge.ai.supply_used).rjust(3)}/{str(knowledge.ai.supply_cap).rjust(3)}U ",
                       f"{record['name']}:{record['line']} {record['message']}\n")
            return "".join(message)
        
        # fmt = "{self.ai.time_formatted.rjust(5)} {str(last_step_time).rjust(4)}ms  {name} - {message}"
        filtering = {
            "": "INFO",  # Default.          
            "terranbot": "INFO",              
            # "terranbot.managers.build_detector": "INFO",
            # "terranbot.managers.pathing_manager": "INFO",
            # "terranbot.managers.map_analysis_manager": "INFO",
            # "terranbot.builds": "INFO",
            # "terranbot.builds.plans.acts": "INFO",
            # "terranbot.activity.t_build_grid": "INFO",
            # "terranbot.builds.plans.acts.dict_unit_spawner": "DEBUG",
            "terranbot.builds.plans.acts.zone_defense": "DEBUG",
            # "terranbot.builds.plans.tactics.terran.addon_swap": "DEBUG",
            "terranbot.grouping": "INFO",
            # "terranbot.combat.vectors": "DEBUG",
            "terranbot.combat.maneuvers": "DEBUG",
            "terranbot.combat.handle_groups": "DEBUG",
            "terranbot.trees.behaviours.gather": "DEBUG",
            # "terranbot.activity": "DEBUG",
            # "terranbot.actions": "DEBUG",
            # "terranbot.buildsplans.acts.zerg_attack_utility": "DEBUG",
            # "terranbot.trees": "DEBUG",
            "terranbot.combat.trees": "INFO",
            # "terranbot.combat.micro.utility": "DEBUG",
            # "terranbot.utilityai": "DEBUG",
            # "terranbot.utilityai.actions": "DEBUG",
            # "terranbot.utilityai.consideration": "DEBUG",
            # "terranbot.utilityai.maps": "DEBUG",            
        }
        logger.remove()
        logger.add(sys.stderr, level="DEBUG", format=formatter, filter=filtering)