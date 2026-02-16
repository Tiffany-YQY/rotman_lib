from enum import Enum

# vanilla Option payoffs
class OptionPayoff:
    CALL = 1
    PUT = -1
    FORWARD = 0
    STRADDLE = 2
    # STRANGLE = 3