import logging

import uvicorn

from .config import load_settings


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run("stratum_api.main:app", host=settings.api_host, port=settings.api_port, log_level="warning")


if __name__ == "__main__":
    main()
