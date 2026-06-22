# Benchmark-only node (NOT part of RocketRide). Safe to delete.
from rocketlib import IGlobalBase


class IGlobal(IGlobalBase):
    def beginGlobal(self):
        pass

    def endGlobal(self):
        pass
