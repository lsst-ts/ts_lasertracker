import enum


class ASCDetailedState(enum.intEnum):
    DISABLED = 1
    ENABLED = 2
    FAULT = 3
    OFFLINE = 4
    STANDBY = 5
    MEASURING = 6
