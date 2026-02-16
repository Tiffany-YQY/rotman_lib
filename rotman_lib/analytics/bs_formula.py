import numpy as np
from scipy.stats import norm
from typing import Dict, Optional, Union
from scipy.stats import norm
from scipy.optimize import minimize
from enum import Enum
from .strategies import OptionStrategy
from .definitions import OptionPayoff


class BlackFormula:
    @classmethod
    def bs_option_price(
        cls,
        underlying_price: float,
        strike: float,
        tte: float,
        vol: float,
        opt_type: OptionPayoff,
        rfr: float = 0.0,
        calc_risk: Optional[bool] = False,
    ):
        d1 = (np.log(underlying_price / strike) + (rfr + 0.5 * vol**2) * tte) / (
            vol * np.sqrt(tte)
        )
        d2 = d1 - vol * np.sqrt(tte)

        df = np.exp(-rfr * tte)

        price = 0.0
        delta, gamma, vega = 0.0, 0.0, 0.0

        # CALL / STRADDLE(call leg)
        if opt_type == OptionPayoff.CALL or opt_type == OptionPayoff.STRADDLE:
            price += underlying_price * norm.cdf(d1) - strike * df * norm.cdf(d2)
            if calc_risk:
                delta += norm.cdf(d1)
                gamma += norm.pdf(d1) / (underlying_price * vol * np.sqrt(tte))
                vega += underlying_price * norm.pdf(d1) * np.sqrt(tte)

        # PUT / STRADDLE(put leg)
        if opt_type == OptionPayoff.PUT or opt_type == OptionPayoff.STRADDLE:
            price += strike * df * norm.cdf(-d2) - underlying_price * norm.cdf(-d1)
            if calc_risk:
                delta += norm.cdf(d1) - 1.0
                gamma += norm.pdf(d1) / (underlying_price * vol * np.sqrt(tte))
                vega += underlying_price * norm.pdf(d1) * np.sqrt(tte)

        return price, (delta, vega, gamma)

    @classmethod
    def implied_vol(
        cls,
        option_price: float,
        forward: float,
        strike: float,
        tte: float,
        opt_type: OptionPayoff,
        rfr: float = 0.0,
        init_vol: Optional[float] = 0.05,
        lb: Optional[float] = 0.0,
        ub: Optional[float] = 100.0,
        precision: Optional[float] = 1.0e-5,
        max_iteration: Optional[int] = 200,
    ):
        if opt_type == OptionPayoff.STRADDLE:
            vol = option_price / (forward) * np.sqrt(2 * np.pi / tte)
        elif opt_type == OptionPayoff.CALL or opt_type == OptionPayoff.PUT:
            vol = option_price / forward * np.sqrt(np.pi / (2 * tte))

        for _ in range(max_iteration):
            price, risk = BlackFormula.bs_option_price(
                forward, strike, tte, vol, opt_type, rfr, True
            )
            if risk[1] == 0:
                return np.nan, risk
            diff = option_price - price
            if vol > ub or vol < lb:
                return np.nan, risk
            if abs(diff) < precision:
                return vol, risk
            vol += diff / risk[1]

        return np.nan, risk

    @classmethod
    def portfolio(
        cls,
        portfolio: OptionStrategy,
        forward: float,
        option_price: Dict,
        tte: float,
        rfr: float = 0.0,
    ):
        results = []
        for opt_type, strike in portfolio.content.keys():
            k = (opt_type, strike)
            assert k in option_price, f"Option price for {k} not provided"

            iv, risk = cls.implied_vol(
                option_price=option_price[k],
                forward=forward,
                strike=strike,
                tte=tte,
                opt_type=opt_type,
                rfr=rfr,
            )
            results.append([iv, risk])

        return results
