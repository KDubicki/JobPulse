import logging
import sys
from pathlib import Path

# Prevent adding handlers multiple times when re-importing in notebooks/tests
_logging_setup_done = False


def setup_logging(log_level: str = "INFO", log_file: str = "jobpulse.log") -> None:
    """Configure logging to console (stdout) and rotating file."""
    global _logging_setup_done
    if _logging_setup_done:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, handlers will filter by level

    # Define formatters
    console_format = logging.Formatter("%(levelname)-8s | %(name)s | %(message)s")
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File Handler
    try:
        # Use FileHandler or RotatingFileHandler if you want rotation
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)
    except IOError:
        sys.stderr.write(f"Warning: Could not open log file '{log_file}' for writing.\n")

    # Mute noisy libraries slightly
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    _logging_setup_done = True
    logging.info("Logging configured. Writing detailed logs to %s", log_file)
