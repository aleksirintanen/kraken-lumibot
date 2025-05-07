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
        position_percentage = 0.1
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

    def on_trading_iteration(self):
        symbol = self.parameters['symbol']
        entry_price = self.get_last_price(symbol)
        self.log_message(f"Position: {self.get_position(symbol)}")
        self.vars.data.append(entry_price)
        # Only keep the last 100 prices to avoid memory issues
        if len(self.vars.data) > 100:
            self.vars.data = self.vars.data[-100:]
        rsi = self.calculate_rsi(self.vars.data)
        self.log_message(f"RSI: {rsi}")
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(self.vars.data)
        self.log_message(f"Bollinger Bands - Upper: {upper_band}, Middle: {middle_band}, Lower: {lower_band}")
        sma = self.calculate_sma(self.vars.data)
        self.log_message(f"SMA: {sma}")
        current_date = self.get_round_day()
        cash = self.get_cash()
        if cash < 10:
            self.log_message("Cash under 10 USD, skipping trade.")
            return
        if rsi is not None and rsi < 30 and lower_band is not None and entry_price < lower_band and (self.vars.last_trade_date is None or self.vars.last_trade_date != current_date):
            position_size = self.get_position_size()
            order = self.create_order(symbol, position_size, 'buy')
            self.submit_order(order)
            self.vars.last_trade_date = current_date


if __name__ == "__main__":
    if IS_BACKTESTING: 
        start = datetime(2025,1,2)
        end = datetime(2025,2,28)
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
        