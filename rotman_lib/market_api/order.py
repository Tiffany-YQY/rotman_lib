from .client import RITClient
from typing import Optional
from ..analytics.bs_formula import BlackFormula


class OrderAPI(RITClient):

    def place_underlying_order(
        self,
        quantity: float,
        order_type: str = "MARKET",
        action: str = "BUY",
        price: Optional[float] = None,
        **kwargs,
    ):
        """
        Place Underlying ETF order
        """
        assert order_type in ["MARKET", "LIMIT"], "order_type must be MARKET or LIMIT"
        assert action in ["BUY", "SELL"], "action must be BUY or SELL"

        if order_type == "LIMIT" and price is None:
            raise ValueError("Price must be specified for LIMIT orders")

        return self.post_order(
            ticker="RTM",
            order_type=order_type,
            quantity=quantity,
            action=action,
            price=price,
            **kwargs,
        )

    def place_atm_option_order(
        self,
        quantity: float,
        order_type: str = "MARKET",
        action: str = "BUY",
        option_type: str = "C",
        etf_price: float = None,
        price: Optional[float] = None,
        **kwargs,
    ):
        """
        place At-The-Money Option order
        1. pull out the ATM price
        2. generate the option ticker
        3. post the order
        """

        assert option_type in ["C", "P"], "option_type must be C or P"
        assert order_type in ["MARKET", "LIMIT"], "order_type must be MARKET or LIMIT"
        assert action in ["BUY", "SELL"], "action must be BUY or SELL"
        # etf_price = self.get_current_price("RTM")

        if etf_price < 45:
            atm = 45
        elif etf_price > 54:
            atm = 54
        else:
            atm = round(etf_price)

        option_ticker = f"RTM1{option_type}{atm:02d}"
        return self.post_order(
            ticker=option_ticker,
            order_type=order_type,
            quantity=quantity,
            action=action,
            price=price,
            **kwargs,
        )

    def place_straddle(
        self,
        quantity: float,
        order_type: str = "MARKET",
        action: str = "BUY",
        price: Optional[float] = None,
        etf_price: float = None,
        **kwargs,
    ):
        """
        Place ATM Straddle order
        """
        self.place_atm_option_order(
            quantity=quantity,
            order_type=order_type,
            action=action,
            option_type="C",
            etf_price=etf_price,
        )
        self.place_atm_option_order(
            quantity=quantity,
            order_type=order_type,
            action=action,
            option_type="P",
            etf_price=etf_price,
        )
        print("Straddle order placed")
        return True

    # delta hedging trades
    def delta_hedge(self, delta):

        if delta > 0:
            action = "SELL"
        else:
            action = "BUY"

        return self.place_underlying_order(
            quantity=abs(delta), action=action, order_type="MARKET", price=None
        )

    def straddle_delta_hedge(
        self,
        quantity: float,
        order_type: str = "MARKET",
        action: str = "BUY",
        price: Optional[float] = None,
        **kwargs,
    ):
        """
        Place delta-hedged straddle portfolio
        """
        # # calculate tte
        # tick = self.get_case().json().get("tick")
        # tte = (300 - tick) / 300 / 12

        # # find option tickers
        # etf_price = self.get_securities_book("RTM", limit=1).json()
        # strike = round(
        #     (etf_price["bids"][0]["price"] + etf_price["asks"][0]["price"]) / 2
        # )
        c_ticker = f"RTM1C{strike:02d}"
        p_ticker = f"RTM1P{strike:02d}"

        c_price = self.get_securities_book(c_ticker, limit=1).json()
        c_price = (c_price["bids"][0]["price"] + c_price["asks"][0]["price"]) / 2

        p_price = self.get_securities_book(p_ticker, limit=1).json()
        p_price = (p_price["bids"][0]["price"] + p_price["asks"][0]["price"]) / 2

        # calculate delta
        _, risk_c = BlackFormula.implied_vol(c_price, etf_price, strike, tte, "C")
        delta_c = risk_c[0]
        _, risk_p = BlackFormula.implied_vol(p_price, etf_price, strike, tte, "P")
        delta_p = risk_p[0]

        # integer quantity for the underlying order
        delta = round(100 * (delta_c + delta_p) * quantity)

        self.place_straddle(
            quantity=quantity,
            action=action,
            order_type=order_type,
            price=price,
            etf_price=etf_price,
            **kwargs,
        )
        self.delta_hedge(delta)

        print("Delta hedge order placed")
        return True
