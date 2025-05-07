# Kraken Lumibot Trading Bot

A trading bot built with Lumibot that uses RSI, Bollinger Bands, and SMA indicators for trading decisions.

## Features

- RSI-based entry signals
- Bollinger Bands for volatility measurement
- SMA for trend detection
- Dynamic position sizing
- One trade per day limit
- Minimum cash balance check

## Requirements

- Python 3.12+
- Docker (optional)

## Running with Docker

1. Build the Docker image:
```bash
docker build -t kraken-lumibot .
```

2. Run the container:
```bash
docker run kraken-lumibot
```

## Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the bot:
```bash
python bot.py
```

## Configuration

The bot's parameters can be modified in the `bot.py` file:
- Trading symbol
- Position sizing
- RSI period
- Bollinger Bands period
- SMA period

## Backtesting

The bot includes backtesting capabilities. To run a backtest, modify the date range and budget in the `bot.py` file. 