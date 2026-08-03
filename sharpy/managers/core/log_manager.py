import logging
import string
import sys
from configparser import ConfigParser
from typing import Any, Optional

from loguru import logger

from sc2.main import logger as sc2_logger
from sharpy.interfaces import ILogManager
from .manager_base import ManagerBase

# Map Python logging levels to loguru levels
LOG_LEVEL_MAP = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL"
}


def default_log_filtering() -> dict[str, str]:
    """Baseline per-module loguru levels before config merge."""
    return {
        "": "INFO",
        "terranbot": "INFO",
    }


def merge_config_log_levels(filtering: dict[str, str], config: ConfigParser) -> dict[str, str]:
    """Apply ``[log_levels]`` overrides; config-local.ini wins when merged upstream."""
    if not config.has_section("log_levels"):
        return filtering
    merged = dict(filtering)
    for module, level in config.items("log_levels"):
        merged[module] = level.upper()
    return merged


def build_log_filtering(knowledge) -> dict[str, str]:
    """Build the per-module filter dict used by all loguru sinks."""
    filtering = default_log_filtering()
    if hasattr(knowledge, "config") and knowledge.config is not None:
        filtering = merge_config_log_levels(filtering, knowledge.config)
    return filtering


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
            
        # Map Python logging level to loguru level
        loguru_level = LOG_LEVEL_MAP.get(log_level, "INFO")
        self.logger.log(loguru_level, message)

    def setup_loguru(self, knowledge):
        def formatter(record):
            last_step_time = round(self.ai.step_time[3])
            message = (f"{knowledge.ai.time_formatted.rjust(5)} {str(knowledge.ai.state.game_loop).rjust(4)} {str(last_step_time).rjust(4)}ms  ",
                       f"{str(knowledge.ai.minerals).rjust(4)}M {str(knowledge.ai.vespene).rjust(4)}G ",
                       f"{str(knowledge.ai.supply_used).rjust(3)}/{str(knowledge.ai.supply_cap).rjust(3)}U ",
                       f"{record['level']} {record['name']}:{record['line']} {record['message']}\n")
            return "".join(message)
        
        # fmt = "{self.ai.time_formatted.rjust(5)} {str(last_step_time).rjust(4)}ms  {name} - {message}"
        filtering = build_log_filtering(knowledge)

        # Preserve any file sinks (added by LoggingUtility.set_logger_file) before removing
        file_sinks = []
        for handler_id, handler in logger._core.handlers.items():
            sink = handler._sink
            # FileSink instances have a _path attribute
            if hasattr(sink, '_path'):
                file_sinks.append((sink._path, handler._levelno, handler._filter))

        logger.remove()
        logger.add(sys.stderr, level="DEBUG", format=formatter, filter=filtering)

        # Re-add file sinks that were present before (from GameStarter/ladder).
        # LoggingUtility registers separate sharpy/terranbot filters on the same path — keep one.
        seen_file_paths: set[str] = set()
        for file_path, level, _orig_filter in file_sinks:
            path_str = str(file_path)
            if path_str in seen_file_paths:
                continue
            seen_file_paths.add(path_str)
            logger.add(path_str, level="DEBUG", format=formatter, filter=filtering)