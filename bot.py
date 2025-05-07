from datetime import datetime
from lumibot.backtesting import BacktestingBroker, PolygonDataBacktesting
from lumibot.credentials import IS_BACKTESTING
from lumibot.strategies import Strategy
from lumibot.traders import Trader


class SwingHigh(Strategy):
    parameters = {
        "symbol" : "X:BTCUSD",
        "quantity" : 0.00001
    }

    def get_position_size(self):
        symbol = self.parameters['symbol']
        last_price = self.get_last_price(symbol)
        cash = self.get_cash()
        rsi = self.calculate_rsi(self.vars.data)
        if rsi is None:
            rsi = 30
        # Scale position size based on RSI: lower RSI = larger position
        # RSI range: 0-30, position size range: 0.5% to 0.1%
        #position_percentage = 0.005 - (rsi / 30) * 0.004
        position_percentage = 0.2
        # Adjust position size based on volatility (Bollinger Band width)
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(self.vars.data)
        if upper_band is not None and lower_band is not None:
            bb_width = (upper_band - lower_band) / middle_band
            # Reduce position size as volatility increases
            position_percentage *= (1 / (1 + bb_width))
        return (cash / last_price) * position_percentage

    def initialize(self):
        self.sleeptime = "30M"
        self.set_market("24/7")
        self.vars.data = []
        self.vars.last_trade_date = None
        self.vars.rsi_below_threshold = False
        self.vars.price_below_bb = False
        self.vars.last_order_price = None
        self.vars.last_trade_week = None
        self.vars.last_month = None
        self.vars.pending_orders = {}  # Track pending orders

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(-period, 0):
            delta = prices[i] - prices[i-1]
            if delta > 0:
                gains.append(delta)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-delta)
        average_gain = sum(gains) / period
        average_loss = sum(losses) / period
        if average_loss == 0:
            return 100
        rs = average_gain / average_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_bollinger_bands(self, prices, period=20, num_std=2):
        if len(prices) < period:
            return None, None, None
        sma = sum(prices[-period:]) / period
        squared_diff_sum = sum((p - sma) ** 2 for p in prices[-period:])
        std = (squared_diff_sum / period) ** 0.5
        upper_band = sma + (num_std * std)
        lower_band = sma - (num_std * std)
        return upper_band, sma, lower_band

    def calculate_sma(self, prices, period=20):
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def cancel_pending_orders(self):
        """Cancel all pending orders"""
        for order_id, order in list(self.vars.pending_orders.items()):
            try:
                self.cancel_order(order)
                self.log_message(f"Cancelled pending order {order_id}")
            except Exception as e:
                self.log_message(f"Error cancelling order {order_id}: {str(e)}")
        self.vars.pending_orders.clear()

    def on_trading_iteration(self):
        symbol = self.parameters['symbol']
        entry_price = self.get_last_price(symbol)
        self.log_message(f"Position: {self.get_position(symbol)}")
        self.vars.data.append(entry_price)
        # Only keep the last 100 prices to avoid memory issues
        if len(self.vars.data) > 100:
            self.vars.data = self.vars.data[-100:]
        
        # Check if it's the first day of the month (only in backtesting mode)
        current_date = self.get_round_day()
        current_month = current_date.month
        
        if IS_BACKTESTING:
            if self.vars.last_month is None or self.vars.last_month != current_month:
                if current_date.day == 1:
                    self.log_message("First day of the month - adding 100 to cash balance (backtesting mode)")
                    self._set_cash_position(self.get_cash() + 1)
                    self.log_message(f"New cash balance: {self.get_cash()}")
                self.vars.last_month = current_month
        
        # Check and update pending orders
        current_time = self.get_datetime()
        for order_id, order_info in list(self.vars.pending_orders.items()):
            order_time = order_info['time']
            if (current_time - order_time).total_seconds() > 3600:  # 1 hour timeout
                self.log_message(f"Order {order_id} timed out after 1 hour, cancelling")
                try:
                    self.cancel_order(order_info['order'])
                    del self.vars.pending_orders[order_id]
                except Exception as e:
                    self.log_message(f"Error cancelling timed out order {order_id}: {str(e)}")
        
        # Cancel all pending orders at the end of the day
        if self.vars.last_trade_date is not None and current_date > self.vars.last_trade_date:
            self.log_message("New trading day - cancelling all pending orders")
            self.cancel_pending_orders()
        
        rsi = self.calculate_rsi(self.vars.data)
        self.log_message(f"RSI: {rsi}")
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(self.vars.data)
        self.log_message(f"Bollinger Bands - Upper: {upper_band}, Middle: {middle_band}, Lower: {lower_band}")
        
        # Check if conditions are met
        if rsi is not None and lower_band is not None:
            # Update state flags
            if rsi < 30:
                self.vars.rsi_below_threshold = True
                self.log_message("RSI below 30 - waiting for recovery")
            if entry_price < lower_band:
                self.vars.price_below_bb = True
                self.log_message("Price below lower Bollinger Band - waiting for recovery")
            
            # Check for recovery conditions
            rsi_recovered = self.vars.rsi_below_threshold and rsi > 30
            price_recovered = self.vars.price_below_bb and entry_price > lower_band
            
            current_week = current_date.isocalendar()[1]  # Get week number
            cash = self.get_cash()
            
            if cash < 1:
                self.log_message("Cash under 1 USD, skipping trade.")
                return
                
            # Check if we can trade based on weekly and daily limits
            can_trade = False
            if self.vars.last_trade_week is None or self.vars.last_trade_week != current_week:
                # First trade of the week
                can_trade = True
                self.log_message("First trade of the week")
            elif self.vars.last_order_price is not None:
                # Calculate price drop percentage
                price_drop_percentage = ((self.vars.last_order_price - entry_price) / self.vars.last_order_price) * 100
                if price_drop_percentage >= 5:
                    can_trade = True
                    self.log_message(f"Price dropped {price_drop_percentage:.2f}% from last trade price {self.vars.last_order_price}")
                else:
                    self.log_message(f"Price drop {price_drop_percentage:.2f}% is less than 5% threshold")
            
            # Make trade if conditions are met
            if (rsi_recovered and price_recovered and 
                (self.vars.last_trade_date is None or self.vars.last_trade_date != current_date) and 
                can_trade):
                self.log_message("Executing trade")
                position_size = self.get_position_size()
                
                # Create limit order slightly below current price (0.1% lower)
                limit_price = entry_price * 0.999
                order = self.create_order(
                    symbol,
                    position_size,
                    'buy',
                    limit_price=limit_price
                )
                self.submit_order(order)
                
                # Track the order
                self.vars.pending_orders[order.identifier] = {
                    'order': order,
                    'time': current_time
                }
                
                self.vars.last_trade_date = current_date
                self.vars.last_trade_week = current_week
                self.vars.last_order_price = entry_price
                # Reset flags after trade
                self.vars.rsi_below_threshold = False
                self.vars.price_below_bb = False


if __name__ == "__main__":
    if IS_BACKTESTING: 
        start = datetime(2025,1,1)
        end = datetime(2025,1,30)
        SwingHigh.backtest(
            PolygonDataBacktesting,
            start,
            end,
            budget=100,
            benchmark_asset = "X:BTCUSD"
        )
    else:    
        strategy = SwingHigh()
        trader = Trader()
        trader.add_strategy(strategy)
        trader.run_all()
        