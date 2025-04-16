import os


class NullLogger:
    def __init__(self):
        self.devnull = open(os.devnull, "w")

    def write(self, message):
        return len(message)

    def flush(self):
        self.devnull.flush()

    def fileno(self):
        return self.devnull.fileno()

    def close(self):
        self.devnull.close()
