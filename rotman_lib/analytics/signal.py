import numpy as np
from .bs_formula import BlackFormula, OptionPayoff


def atm_straddle_signal(
    rv: float,  # realized volatility
    iv: float,
):
    if rv > iv:
        signal = "BUY"
    else:
        signal = "SELL"

    return signal


def atm_straddle_gap_signal(rv: float, iv: float, k: float):  # realized volatility
    if rv / iv > (1 + k):
        return "BUY"
    elif rv / iv < (1 - k):
        return "SELL"
    else:
        return None


def atm_straddle_transaction(rv: float, iv: float, gap: float):
    if rv**2 > (iv**2 + gap):
        return "BUY"
    elif rv**2 < (iv**2 - gap):
        return "SELL"
    else:
        return None


def strangle_signal(
    rv: float, tte: float, underlying_price: float, strike_gap: float, premium: float
):

    ev = (premium + strike_gap) / underlying_price
    if ev > rv * np.sqrt(tte):
        signal = "SELL"
    else:
        signal = "BUY"
    return signal
