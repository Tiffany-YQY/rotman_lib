import json
import requests
import signal


# Exception to be raised on a timeout.
class TimeoutException(Exception):
    pass


# Signal handler for timeouts.
def timeout_handler(signum, frame):
    raise TimeoutException("HTTP request timed out")


class RITClient:
    """
    Client for the Rotman Interactive Trader (RIT) REST API.

    This client implements functions corresponding to the endpoints documented
    in the swagger YAML file. It attempts to use a signal-based timeout if available,
    otherwise it falls back to the built-in timeout support of the requests library.
    """

    def __init__(
        self,
        host="localhost",
        port=9999,
        base_path="/v1",
        api_key="0LC89D18",
        default_timeout=20,
    ):
        """
        Initializes the client.

        :param host: Hostname where the API server is running.
        :param port: Port on which the API server is listening.
        :param base_path: Base path for the API endpoints.
        :param api_key: API key required for authorization.
        :param default_timeout: Default timeout (in seconds) for each HTTP request.
        """
        self.host = host
        self.port = port
        self.base_path = base_path
        self.api_key = api_key
        self.default_timeout = default_timeout
        self.base_url = f"http://{self.host}:{self.port}{self.base_path}"
        self.headers = {
            "X-API-Key": self.api_key,
        }

    def _request(self, method, path, params=None, data=None, timeout=None):
        """
        Internal helper to perform HTTP requests.

        If the platform supports signal-based alarms (i.e. if signal.SIGALRM exists),
        then it uses a signal-based timeout. Otherwise, it relies on requests' built-in timeout.

        :param method: HTTP method ('get', 'post', or 'delete').
        :param path: The API path (e.g. '/case').
        :param params: URL query parameters.
        :param data: POST data (if applicable).
        :param timeout: Timeout in seconds for this request.
        :return: The response from the requests library.
        :raises TimeoutException: If the request times out.
        """
        if timeout is None:
            timeout = self.default_timeout

        url = self.base_url + path

        # Check if the platform supports SIGALRM.
        if hasattr(signal, "SIGALRM"):
            # Use signal.alarm-based timeout.
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            try:
                if method.lower() == "get":
                    response = requests.get(url, headers=self.headers, params=params)
                elif method.lower() == "post":
                    response = requests.post(
                        url, headers=self.headers, params=params, data=data
                    )
                elif method.lower() == "delete":
                    response = requests.delete(url, headers=self.headers, params=params)
                else:
                    raise ValueError("Unsupported HTTP method")
            finally:
                # Cancel the alarm and restore the old signal handler.
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            return response
        else:
            # Fallback: Use requests' built-in timeout support.
            try:
                if method.lower() == "get":
                    response = requests.get(
                        url, headers=self.headers, params=params, timeout=timeout
                    )
                elif method.lower() == "post":
                    response = requests.post(
                        url,
                        headers=self.headers,
                        params=params,
                        data=data,
                        timeout=timeout,
                    )
                elif method.lower() == "delete":
                    response = requests.delete(
                        url, headers=self.headers, params=params, timeout=timeout
                    )
                else:
                    raise ValueError("Unsupported HTTP method")
            except requests.Timeout:
                raise TimeoutException("HTTP request timed out")
            return response

    # === Endpoints defined in the swagger file ===

    def get_case(self):
        """Gets information about the current case."""
        return self._request("get", "/case")

    def get_trader(self):
        """Gets information about the currently signed in trader."""
        return self._request("get", "/trader")

    def get_limits(self):
        """Gets the trading limits for the current case."""
        return self._request("get", "/limits")

    def get_news(self, since=None, limit=None):
        """
        Gets the most recent news.

        :param since: Retrieve only news items after a particular news id.
        :param limit: Maximum number of news items to return.
        """
        params = {}
        if since is not None:
            params["since"] = since
        if limit is not None:
            params["limit"] = limit
        return self._request("get", "/news", params=params)

    def get_assets(self, ticker=None):
        """
        Gets a list of available assets.

        :param ticker: (Optional) Filter by asset ticker.
        """
        params = {}
        if ticker is not None:
            params["ticker"] = ticker
        return self._request("get", "/assets", params=params)

    def get_assets_history(self, ticker=None, period=None, limit=None):
        """
        Gets the activity log for assets.

        :param ticker: (Optional) Filter by asset ticker.
        :param period: (Optional) Specify the period (defaults to the current period).
        :param limit: (Optional) Limit the number of log entries.
        """
        params = {}
        if ticker is not None:
            params["ticker"] = ticker
        if period is not None:
            params["period"] = period
        if limit is not None:
            params["limit"] = limit
        return self._request("get", "/assets/history", params=params)

    def get_securities(self, ticker=None):
        """
        Gets a list of available securities and associated positions.

        :param ticker: (Optional) Filter by security ticker.
        """
        params = {}
        if ticker is not None:
            params["ticker"] = ticker
        return self._request("get", "/securities", params=params)

    def get_securities_book(self, ticker, limit=20):
        """
        Gets the order book of a security.

        :param ticker: Security ticker (required).
        :param limit: Maximum number of orders per side (default: 20).
        """
        params = {"ticker": ticker, "limit": limit}
        return self._request("get", "/securities/book", params=params)

    def get_securities_history(self, ticker, period=None, limit=None):
        """
        Gets the OHLC history for a security.

        :param ticker: Security ticker (required).
        :param period: (Optional) Specify the period.
        :param limit: (Optional) Limit the number of ticks.
        """
        params = {"ticker": ticker}
        if period is not None:
            params["period"] = period
        if limit is not None:
            params["limit"] = limit
        return self._request("get", "/securities/history", params=params)

    def get_securities_tas(self, ticker, after=None, period=None, limit=None):
        """
        Gets time & sales history for a security.

        :param ticker: Security ticker (required).
        :param after: (Optional) Only retrieve data with an id greater than this value.
        :param period: (Optional) Specify the period.
        :param limit: (Optional) Specify how many ticks to include.
        """
        params = {"ticker": ticker}
        if after is not None:
            params["after"] = after
        if period is not None:
            params["period"] = period
        if limit is not None:
            params["limit"] = limit
        return self._request("get", "/securities/tas", params=params)

    def get_orders(self, status="OPEN"):
        """
        Gets a list of all orders.

        :param status: Filter orders by status (defaults to 'OPEN').
        """
        params = {"status": status}
        return self._request("get", "/orders", params=params)

    def post_order(
        self, ticker, order_type, quantity, action, price=None, dry_run=None
    ):
        """
        Inserts a new order.

        :param ticker: Security ticker.
        :param order_type: 'MARKET' or 'LIMIT'.
        :param quantity: Order quantity.
        :param action: 'BUY' or 'SELL'.
        :param price: (Optional) Price for LIMIT orders.
        :param dry_run: (Optional) 0 or 1. Simulates order execution if provided.
        """
        params = {
            "ticker": ticker,
            "type": order_type,
            "quantity": quantity,
            "action": action,
        }
        if price is not None:
            params["price"] = price
        if dry_run is not None:
            params["dry_run"] = dry_run
        return self._request("post", "/orders", params=params)

    def get_order(self, order_id):
        """
        Gets the details of a specific order.

        :param order_id: The id of the order.
        """
        return self._request("get", f"/orders/{order_id}")

    def delete_order(self, order_id):
        """
        Cancels an open order.

        :param order_id: The id of the order to cancel.
        """
        return self._request("delete", f"/orders/{order_id}")

    def get_tenders(self):
        """Gets a list of all active tenders."""
        return self._request("get", "/tenders")

    def post_tender(self, tender_id, price=None):
        """
        Accepts a tender.

        :param tender_id: The id of the tender.
        :param price: (Optional) Price if the tender is not fixed-bid.
        """
        params = {}
        if price is not None:
            params["price"] = price
        return self._request("post", f"/tenders/{tender_id}", params=params)

    def delete_tender(self, tender_id):
        """
        Declines a tender.

        :param tender_id: The id of the tender.
        """
        return self._request("delete", f"/tenders/{tender_id}")

    def get_leases(self):
        """Gets a list of all assets currently being leased or used."""
        return self._request("get", "/leases")

    def post_lease(
        self,
        ticker,
        from1=None,
        quantity1=None,
        from2=None,
        quantity2=None,
        from3=None,
        quantity3=None,
    ):
        """
        Leases or uses an asset.

        :param ticker: Ticker of the asset.
        :param from1: (Optional) 1st source ticker.
        :param quantity1: (Optional) 1st source quantity.
        :param from2: (Optional) 2nd source ticker.
        :param quantity2: (Optional) 2nd source quantity.
        :param from3: (Optional) 3rd source ticker.
        :param quantity3: (Optional) 3rd source quantity.
        """
        params = {"ticker": ticker}
        if from1 is not None:
            params["from1"] = from1
        if quantity1 is not None:
            params["quantity1"] = quantity1
        if from2 is not None:
            params["from2"] = from2
        if quantity2 is not None:
            params["quantity2"] = quantity2
        if from3 is not None:
            params["from3"] = from3
        if quantity3 is not None:
            params["quantity3"] = quantity3
        return self._request("post", "/leases", params=params)

    def get_lease(self, lease_id):
        """
        Gets the details of a specific lease.

        :param lease_id: The id of the lease.
        """
        return self._request("get", f"/leases/{lease_id}")

    def post_lease_use(
        self,
        lease_id,
        from1,
        quantity1,
        from2=None,
        quantity2=None,
        from3=None,
        quantity3=None,
    ):
        """
        Uses a leased asset.

        :param lease_id: The id of the lease.
        :param from1: 1st source ticker.
        :param quantity1: 1st source quantity.
        :param from2: (Optional) 2nd source ticker.
        :param quantity2: (Optional) 2nd source quantity.
        :param from3: (Optional) 3rd source ticker.
        :param quantity3: (Optional) 3rd source quantity.
        """
        params = {"from1": from1, "quantity1": quantity1}
        if from2 is not None:
            params["from2"] = from2
        if quantity2 is not None:
            params["quantity2"] = quantity2
        if from3 is not None:
            params["from3"] = from3
        if quantity3 is not None:
            params["quantity3"] = quantity3
        return self._request("post", f"/leases/{lease_id}", params=params)

    def delete_lease(self, lease_id):
        """
        Unleases an asset.

        :param lease_id: The id of the lease.
        """
        return self._request("delete", f"/leases/{lease_id}")

    def post_cancel_command(self, all=None, ticker=None, ids=None, query=None):
        """
        Bulk cancels open orders. Exactly one cancellation parameter must be provided.

        :param all: Set to 1 to cancel all open orders.
        :param ticker: Cancel all open orders for a specific ticker.
        :param ids: Comma-separated list of order ids to cancel.
        :param query: A query string to select orders for cancellation.
        :return: A response indicating which orders were cancelled.
        :raises ValueError: If no parameter is provided.
        """
        params = {}
        if all is not None:
            params["all"] = all
        elif ticker is not None:
            params["ticker"] = ticker
        elif ids is not None:
            params["ids"] = ids
        elif query is not None:
            params["query"] = query
        else:
            raise ValueError(
                "One cancellation parameter must be specified (all, ticker, ids, or query)"
            )
        return self._request("post", "/commands/cancel", params=params)

    def get_mid_price(self, ticker):
        book = self.get_securities_book(ticker, limit=1).json()
        bid = book["bids"][0]["price"]
        ask = book["asks"][0]["price"]
        return (bid + ask) / 2
    
