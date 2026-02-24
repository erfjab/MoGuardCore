from copy import deepcopy
from uvicorn.config import LOGGING_CONFIG
from logging import getLogger

logger = getLogger("uvicorn.error")


def config_uvicorn_log():
    log_config = deepcopy(LOGGING_CONFIG)
    default_fmt = "[%(asctime)s] %(levelprefix)s %(message)s"
    date_fmt = "%m/%d %H:%M:%S"
    log_config["formatters"]["default"]["fmt"] = default_fmt
    log_config["formatters"]["default"]["datefmt"] = date_fmt
    log_config["formatters"]["access"]["fmt"] = default_fmt
    log_config["formatters"]["access"]["datefmt"] = date_fmt
    return log_config
