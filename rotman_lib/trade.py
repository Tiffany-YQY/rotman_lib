import re
from collections import defaultdict

from rotman_lib import *
client = OrderAPI(api_key="")

news = []
rv = []
ticker = "RTM"
spread = 0.02

rfr, rv_t, delta_limit, pattern_delta = None, None, None, None

state = {
    "cash": 0.0,
    "position": defaultdict(
        int
    ),  # RTM shares, option contracts (positive for long, negative for short)
    # "price":defaultdict(float), # execute price for each ticker
    "strike": None,
    "side": None,  # "SELL" (short straddle) or "BUY" (long straddle)
}
transaction_log = []
pnl_decomposition = {"options": [], "etf": [], "transaction_cost": [], "total": []}
max_n_option = 1000
max_n_etf = 50000

mult = 100  # shares per option contract
n = int(max_n_option / 2)  # number of straddles

# fetch news
def fetch_and_save_news(client):

    response = client.get_news()
    if response.ok:
        news = response.json()

        sorted_news = sorted(news, key=lambda x: x["news_id"], reverse=True)

        print(f"Saved {len(sorted_news)} news items.")


def log_trade(
    t, ticker, qty, price, gamma, iv, instrument, action, cash_after, note=""
):
    transaction_log.append(
        {
            "tick": t,
            "ticker": ticker,
            "qty": qty,
            "price": price,
            "gamma": gamma,
            "iv": iv,
            "instrument": instrument,
            "action": action,
            "cash_after": cash_after,
            "note": note,
        }
    )


def option_commission(contracts_each_leg, trans_cost_option=1.0):
    return 2 * abs(contracts_each_leg) * trans_cost_option


def stock_commission(shares, trans_cost_etf=0.01):
    return trans_cost_etf * abs(shares)


def place_order(
    ticker, order_type, quantity, action, max_chunk_rtm=10000, max_chunk_option=100
):
    qty = int(round(quantity))
    if qty <= 0:
        return None
    print(f"Placing order: {ticker} {order_type} {qty} {action}")
    def _post_one(q):
        resp = client.post_order(ticker, order_type, int(q), action)
        if not resp.ok:
            # print body so you can see the real reason (even if status=500)
            print("ORDER FAILED:", ticker, order_type, q, action)
            print("status:", resp.status_code)
            print("url:", getattr(resp, "url", ""))
            print("text:", resp.text)
            try:
                print("json:", resp.json())
            except Exception:
                pass
            resp.raise_for_status()
        return resp.json()

    if ticker == "RTM" and qty > max_chunk_rtm:
        results = []
        remaining = qty
        while remaining > 0:
            chunk = min(max_chunk_rtm, remaining)
            results.append(_post_one(chunk))
            remaining -= chunk
        return results
    if ticker.startswith("RTM1") and qty > max_chunk_option:
        results = []
        remaining = qty
        while remaining > 0:
            chunk = min(max_chunk_option, remaining)
            results.append(_post_one(chunk))
            remaining -= chunk
        return results

    # Normal single order
    return _post_one(qty)


if __name__ == "__main__":
    while True:

        case = client.get_case().json()
        tick = case.get("tick")
        status = case.get("status")

        if tick == 0:
            continue
        if status in ("STOPPED", "ENDED", "FINISHED") and tick != 0:
            break

        response = client.get_news()
        news = response.json()
        news_map = {item["news_id"]: item for item in news}

        # extract the risk free rate and realized volatility from the news
        if tick == 1 or rfr is None:
            rfr_news = news_map[1]["body"]
            pattern = r"risk free rate is (\d+(?:\.\d+)?)%.*?realized volatility is (\d+(?:\.\d+)?)%"
            match = re.search(pattern, rfr_news)
            if match:
                rfr = float(match.group(1)) / 100
                rv_t = float(match.group(2)) / 100
                print("rfr:", rfr)
                print("rv:", rv_t)
            else:
                print("No match found.")
                # rfr = float(input("Input risk free rate (%): ")) / 100
                rfr = 0.0
                rv_t = float(input("Input realized volatility (%): ")) / 100

            delta_news = news_map[2]["body"]
            pattern_delta = r"delta limit.*?(\d+).*?penalty percentage is (\d+)%"
            match = re.search(pattern_delta, delta_news, re.IGNORECASE | re.DOTALL)
            if match:
                delta_limit = int(match.group(1))
                penalty_pct = float(match.group(2))
                print(delta_limit, penalty_pct)
            else:
                print("No match found for delta limit.")
                delta_limit = float(input("Input delta limit: "))
                penalty_pct = float(input("Input penalty percentage (%): "))
        elif tick == 74 or tick == 149 or tick == 224:
            rv_news = news_map[(tick + 1) // 75 * 2 + 1]["body"]
            match = re.search(r"(\d+(?:\.\d+)?)%", rv_news)
            if match:
                rv_t = float(match.group(1)) / 100
                print("Update rv:", rv_t)
            else:
                print("No match found for rv update.")
                rv_t = float(input("Input realized volatility (%): ")) / 100

        rv.append(rv_t)

        # strategy
        tte = (300 - tick) / 300 / 12
        etf_info = client.get_securities(ticker).json()[0]
        underlying_price = (etf_info["bid"] + etf_info["ask"]) / 2  # mid_price
        atm_strike = round(underlying_price)

        c_atm_ticker = f"RTM1C{int(atm_strike):02d}"
        p_atm_ticker = f"RTM1P{int(atm_strike):02d}"

        c_atm_info = client.get_securities(c_atm_ticker).json()[0]
        c_atm_price = (c_atm_info["bid"] + c_atm_info["ask"]) / 2  # mid_price

        p_atm_info = client.get_securities(p_atm_ticker).json()[0]
        p_atm_price = (p_atm_info["bid"] + p_atm_info["ask"]) / 2  # mid_price

        atm_premium = (
            (c_atm_price + p_atm_price) * mult * n
        )  # total premium for n straddles

        iv_atm, (delta_atm, vega_atm, gamma_atm) = BlackFormula.implied_vol(
            (c_atm_price + p_atm_price),
            underlying_price,
            atm_strike,
            tte,
            OptionPayoff.STRADDLE,
            rfr,
        )
        have_options = any(k != "RTM" for k in state["position"].keys())

        # if position is empty, open new position based on signal
        if not have_options:
            gap = (
                2 * option_commission(n) * 240 / (underlying_price**2 * gamma_atm * 100 * n)
            )
            signal = atm_straddle_transaction(rv[-1], iv_atm, gap)
            state["side"] = signal

            state["strike"] = atm_strike

            if signal == "SELL":
                # post SELL orders
                print(c_atm_ticker, "MARKET", n, "SELL")
                resp_c = place_order(c_atm_ticker, "MARKET", n, "SELL")
                c_atm_price = client.get_securities(c_atm_ticker).json()[0]["vwap"]
                c_atm_qty = client.get_securities(c_atm_ticker).json()[0]["position"]

                if status != "TRANSACTED":
                    print(f"Order for {c_atm_ticker} not fully filled. Status: {status}")

                resp_p = place_order(p_atm_ticker, "MARKET", n, "SELL")
                p_atm_price = client.get_securities(p_atm_ticker).json()[0]["vwap"]
                p_atm_qty = client.get_securities(p_atm_ticker).json()[0]["position"]
                # status = resp_p["status"]  # TRANSACTED

                state["position"][c_atm_ticker] -= c_atm_qty
                state["position"][p_atm_ticker] -= p_atm_qty
                state["strike"] = atm_strike

                state["cash"] += (
                    c_atm_price * c_atm_qty * mult
                    + p_atm_price * p_atm_qty * mult
                    - option_commission(c_atm_qty)
                )

            elif signal == "BUY":
                print(c_atm_ticker, "MARKET", n, "BUY")
                resp_c = place_order(c_atm_ticker, "MARKET", n, "BUY")
                c_atm_price = client.get_securities(c_atm_ticker).json()[0]["vwap"]
                c_atm_qty = client.get_securities(c_atm_ticker).json()[0]["position"]

                if status != "TRANSACTED":
                    print(f"Order for {c_atm_ticker} not fully filled. Status: {status}")

                resp_p = place_order(p_atm_ticker, "MARKET", n, "BUY")
                p_atm_price = client.get_securities(p_atm_ticker).json()[0]["vwap"]
                p_atm_qty = client.get_securities(p_atm_ticker).json()[0]["position"]
                # status = resp_p["status"]  # TRANSACTED

                state["position"][c_atm_ticker] += c_atm_qty
                state["position"][p_atm_ticker] += p_atm_qty
                state["strike"] = atm_strike

                state["cash"] -= (
                    c_atm_price * c_atm_qty * mult
                    + p_atm_price * p_atm_qty * mult
                    + option_commission(c_atm_qty)
                )

            else:
                pass  # no signal, keep empty position

        # If have options, check flip and check etf limits
        else:
            # get current option and underlying price
            tickers = state["position"].keys()
            strike = state["strike"]

            c_ticker = f"RTM1C{int(strike):02d}"
            p_ticker = f"RTM1P{int(strike):02d}"

            c_price_info = client.get_securities(c_ticker).json()[0]
            c_price = (c_price_info["bid"] + c_price_info["ask"]) / 2

            p_price_info = client.get_securities(p_ticker).json()[0]
            p_price = (p_price_info["bid"] + p_price_info["ask"]) / 2

            # calculate current option price and tick
            iv, (delta, vega, gamma) = BlackFormula.implied_vol(
                (c_price + p_price),
                underlying_price,
                strike,
                tte,
                OptionPayoff.STRADDLE,
                rfr,
            )
            # calculate new signal
            gap = 2 * option_commission(n) * 240 / (underlying_price**2 * gamma * 100 * n)

            signal = atm_straddle_gap_signal(rv[-1], iv, gap)

            if signal is None:
                signal = state["side"]  # if no signal, keep current position

            ## signal changed, need to flip position
            if signal != state["side"]:

                # 1) close existing position
                existing_n = abs(state["position"][c_ticker])
                # premium = (
                #     (c_price + p_price) * mult * existing_n
                # )  # current straddle premium

                if state["side"] == "SELL":  # short -> buy to close

                    resp_c = place_order(c_ticker, "MARKET", n, "BUY")
                    c_price = client.get_securities(c_ticker).json()[0]["vwap"]
                    c_qty = client.get_securities(c_ticker).json()[0]["position"]
                    # status = resp_c["status"]  # TRANSACTED

                    resp_p = place_order(p_ticker, "MARKET", n, "BUY")
                    p_price = client.get_securities(p_ticker).json()[0]["vwap"]
                    p_qty = client.get_securities(p_ticker).json()[0]["position"]
                    # status = resp_p["status"]  # TRANSACTED

                    buy_cost = c_price * c_qty * mult + p_price * p_qty * mult
                    state["cash"] -= buy_cost + option_commission(p_qty)

                else:  # long -> sell to close

                    resp_c = place_order(c_ticker, "MARKET", existing_n, "SELL")
                    c_price = client.get_securities(c_ticker).json()[0]["vwap"]
                    c_qty = client.get_securities(c_ticker).json()[0]["position"]
                    # status = resp_c["status"]  # TRANSACTED

                    resp_p = place_order(p_ticker, "MARKET", existing_n, "SELL")
                    p_price = client.get_securities(p_ticker).json()[0]["vwap"]
                    p_qty = client.get_securities(p_ticker).json()[0]["position"]
                    # status = resp_p["status"]  # TRANSACTED

                    sell_cost = c_price * c_qty * mult + p_price * p_qty * mult
                    state["cash"] += sell_cost - option_commission(p_qty)

                # state["cash"] -= option_commission(c_qty)
                state["position"].pop(c_ticker, None)
                state["position"].pop(p_ticker, None)
                state["strike"] = None
                state["side"] = None

                # 2) open new positions, check new atm option position limit

                # if under etf position limit
                if abs(delta_atm * mult * n) <= max_n_etf:
                    trade_n = n
                # over limit of etf, buy/sell less options
                else:
                    option_delta_keeps = max_n_etf  # if target_rtm > 0 else -max_n_etf
                    trade_n = option_delta_keeps / (delta_atm * mult)
                    atm_premium = (
                        atm_premium / n * trade_n
                    )  # adjust premium for smaller position

                # open new atm straddle position
                if signal == "SELL":
                    state["position"][c_atm_ticker] -= trade_n
                    state["position"][p_atm_ticker] -= trade_n
                    state["strike"] = atm_strike
                    state["side"] = signal
                    # state["cash"] += atm_premium - option_commission(trade_n)

                    resp_c = place_order(c_atm_ticker, "MARKET", trade_n, "SELL")
                    c_atm_price = client.get_securities(c_atm_ticker).json()[0]["vwap"]
                    c_atm_qty = client.get_securities(c_atm_ticker).json()[0]["position"]
                    # status = resp_c["status"]  # TRANSACTED

                    resp_p = place_order(p_atm_ticker, "MARKET", trade_n, "SELL")
                    p_atm_price = client.get_securities(p_atm_ticker).json()[0]["vwap"]
                    p_atm_qty = client.get_securities(p_atm_ticker).json()[0]["position"]
                    # status = resp_p["status"]  # TRANSACTED
                    state["cash"] += (
                        c_atm_price * c_atm_qty * mult
                        + p_atm_price * p_atm_qty * mult
                        - option_commission(c_atm_qty)
                    )
                else:
                    state["position"][c_atm_ticker] += trade_n
                    state["position"][p_atm_ticker] += trade_n
                    state["strike"] = atm_strike
                    state["side"] = signal

                    resp_c = place_order(c_atm_ticker, "MARKET", trade_n, "BUY")
                    c_atm_price = client.get_securities(c_atm_ticker).json()[0]["vwap"]
                    c_atm_qty = client.get_securities(c_atm_ticker).json()[0]["position"]
                    # status = resp_c["status"]  # TRANSACTED

                    resp_p = place_order(p_atm_ticker, "MARKET", trade_n, "BUY")
                    p_atm_price = client.get_securities(p_atm_ticker).json()[0]["vwap"]
                    p_atm_qty = client.get_securities(p_atm_ticker).json()[0]["position"]
                    # status = resp_p["status"]  # TRANSACTED
                    state["cash"] -= (
                        c_atm_price * c_atm_qty * mult
                        + p_atm_price * p_atm_qty * mult
                        + option_commission(c_atm_qty)
                    )
            else:
                pass  # signal not changed, keep position

        # update option indicators
        have_options = any(k != "RTM" for k in state["position"].keys())

        # Delta Hedge every tick
        if have_options:

            opt_pos = 1 if state["side"] == "BUY" else -1  # contracts (same as put)
            c_ticker = f"RTM1C{int(state['strike']):02d}"
            p_ticker = f"RTM1P{int(state['strike']):02d}"

            c_price_info = client.get_securities(c_ticker).json()[0]
            c_price = (c_price_info["bid"] + c_price_info["ask"]) / 2
            p_price_info = client.get_securities(p_ticker).json()[0]
            p_price = (p_price_info["bid"] + p_price_info["ask"]) / 2
            mkt_straddle = c_price + p_price

            iv, (delta, vega, gamma) = BlackFormula.implied_vol(
                mkt_straddle,
                underlying_price,
                state["strike"],
                tte,
                OptionPayoff.STRADDLE,
                rfr,
            )

            pos_contracts = state["position"].get(c_ticker, 0)
            option_delta_shares = opt_pos * delta * mult * pos_contracts

            current_rtm = state["position"].get("RTM", 0)
            target_rtm = int(round(-option_delta_shares))  # hedging amount
            diff_rtm = target_rtm - current_rtm

            if diff_rtm != 0:
                if abs(diff_rtm) > max_n_etf:
                    diff_rtm = max_n_etf if diff_rtm > 0 else -max_n_etf
                qty = abs(diff_rtm)
                side = "BUY" if diff_rtm > 0 else "SELL"

                resp = place_order("RTM", "MARKET", qty, side)
                # exe = resp[0]['vwap']

                # cash_change = -qty * exe if side == "BUY" else +qty * exe
                # state["cash"] += cash_change - stock_commission(qty)
                state["position"]["RTM"] = current_rtm + (qty if side == "BUY" else -qty)
                if state["position"]["RTM"] == 0:
                    state["position"].pop("RTM", None)