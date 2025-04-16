import logging
import sys


class LoggerAdapter:
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level

    def write(self, message):
        if message and not message.isspace():
            self.logger.log(self.level, message.rstrip())
        return len(message)

    def flush(self):
        pass

    def fileno(self):
        return sys.stderr.fileno()
