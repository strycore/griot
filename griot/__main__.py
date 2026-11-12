"""Run the griot gateway: `python -m griot`."""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path

from griot import config as griot_config
from griot.gateway import Gateway, make_server

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main() -> int:
    parser = argparse.ArgumentParser(prog="griot", description=__doc__)
    parser.add_argument("--config", type=Path,
                        help=f"config file (default: ${griot_config.CONFIG_ENV} or griot.toml)")
    parser.add_argument("--host", help="override the configured listen address")
    parser.add_argument("--port", type=int, help="override the configured port")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format=LOG_FORMAT)
    log = logging.getLogger("griot")

    try:
        config = griot_config.load(args.config)
        overrides = {key: value for key in ("host", "port")
                     if (value := getattr(args, key)) is not None}
        gateway = Gateway(dataclasses.replace(config, **overrides))
    except griot_config.ConfigError as error:
        log.error("%s", error)
        return 2

    for name, engine in gateway.engines.items():
        log.info("engine %s: %s", name,
                 "available" if engine.available() else "NOT available")
    server = make_server(gateway)
    log.info("listening on http://%s:%d (default voice: %s)", gateway.config.host,
             gateway.config.port, gateway.config.default_voice or "none")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
