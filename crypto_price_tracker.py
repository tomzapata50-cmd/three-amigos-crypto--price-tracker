#!/usr/bin/env python3
"""
crypto_price_tracker.py

Terminal crypto price tracker with:
- symbol -> CoinGecko ID mapping (pass LTC, DOGE, SOL, etc. or full CoinGecko ids)
- configurable coins & refresh interval via CLI
- CSV logging of historical prices (append mode)
- percent change since previous poll
- graceful handling of network errors and Ctrl+C
- colorized terminal output (colorama)

Usage examples:
  python crypto_price_tracker.py
  python crypto_price_tracker.py --coins LTC,DOGE,SOL --once
  python crypto_price_tracker.py --coins bitcoin,ethereum --interval 60 --csv prices.csv
  python crypto_price_tracker.py --coins ltc,doge,sol --no-csv --no-color
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests
from colorama import Fore, Style, init

init(autoreset=True)

# Default configuration
DEFAULT_COINS = ["bitcoin", "ethereum", "dogecoin", "solana", "litecoin"]
DEFAULT_INTERVAL = 30  # seconds
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_CSV = "crypto_prices.csv"

# Common symbol -> CoinGecko id map (case-insensitive)
SYMBOL_TO_ID: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
    "DOGE": "dogecoin",
    "SOL": "solana",
    "ADA": "cardano",
    "XRP": "ripple",
    "BCH": "bitcoin-cash",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "BNB": "binancecoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2",
    "SHIB": "shiba-inu",
    "TRX": "tron",
    "UNI": "uniswap",
    # add more mappings as desired
}


def build_url(coins: List[str]) -> str:
    ids = ",".join(coins)
    return f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"


def resolve_input_coins(raw: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Resolve a comma-separated user input string into a list of CoinGecko ids.
    Returns (resolved_ids, mapping) where mapping maps the original token -> resolved id.
    If a token can't be mapped (and isn't obviously an id), we keep the token lowercased (hoping it's an id).
    """
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    resolved: List[str] = []
    mapping: Dict[str, str] = {}
    seen = set()

    for t in tokens:
        up = t.upper()
        if up in SYMBOL_TO_ID:
            cid = SYMBOL_TO_ID[up]
        else:
            # assume user provided a CoinGecko id (e.g., "bitcoin" or "solana") — normalize to lower-case
            cid = t.lower()
        # avoid duplicates
        if cid not in seen:
            resolved.append(cid)
            seen.add(cid)
        mapping[t] = cid

    return resolved, mapping


def fetch_prices(coins: List[str], timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Dict[str, float]]:
    """Fetch prices from CoinGecko. Raises requests.RequestException on network errors."""
    url = build_url(coins)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def ensure_csv_header(path: str, coins: List[str]) -> None:
    if not path:
        return
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            header = ["timestamp"] + [f"{c}_usd" for c in coins]
            writer.writerow(header)


def append_prices_to_csv(path: str, coins: List[str], prices: Dict[str, Optional[float]]) -> None:
    if not path:
        return
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        row = [time.strftime("%Y-%m-%d %H:%M:%S")] + [prices.get(c, "") for c in coins]
        writer.writerow(row)


def format_price(price: Optional[float]) -> str:
    if price is None:
        return "N/A"
    return f"${price:,.4f}"


def format_pct(delta: Optional[float]) -> str:
    if delta is None:
        return "   N/A   "
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta * 100:7.2f}%"


def print_prices(
    coins: List[str],
    data: Dict[str, Dict[str, float]],
    prev: Dict[str, float],
) -> Dict[str, Optional[float]]:
    """Print table and return current prices dict to be used as previous next poll."""
    print("--------------------------------------------------------------")
    print(f"{'Crypto':<12}{'Price (USD)':>16}{'Change':>14}")
    print("--------------------------------------------------------------")

    current_prices: Dict[str, Optional[float]] = {}

    for coin in coins:
        coin_data = data.get(coin, {})
        price = coin_data.get("usd")
        current_prices[coin] = price

        prev_price = prev.get(coin)
        if price is None or prev_price is None:
            pct_change = None
        else:
            pct_change = ((price - prev_price) / prev_price) if prev_price != 0 else None

        if price is None:
            price_str = Fore.YELLOW + "N/A"
            pct_str = Fore.YELLOW + format_pct(pct_change)
        else:
            price_str = (Fore.GREEN if price > 1 else Fore.RED) + format_price(price)
            if pct_change is None:
                pct_str = Fore.YELLOW + format_pct(pct_change)
            else:
                pct_str = (Fore.GREEN if pct_change > 0 else Fore.RED if pct_change < 0 else Fore.CYAN) + format_pct(pct_change)

        print(f"{coin.capitalize():<12}{price_str:>16}{pct_str:>14}")

    print("--------------------------------------------------------------")
    return current_prices


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal crypto price tracker with CSV logging and percent-change.")
    parser.add_argument("--coins", "-c", help="Comma-separated coin ids or symbols (e.g. BTC,ETH or bitcoin,ethereum). Default: common set", default=",".join(DEFAULT_COINS))
    parser.add_argument("--interval", "-i", type=int, help="Refresh interval in seconds", default=DEFAULT_INTERVAL)
    parser.add_argument("--timeout", "-t", type=int, help="HTTP request timeout in seconds", default=DEFAULT_TIMEOUT)
    parser.add_argument("--csv", "-o", help="CSV file to append prices to (set empty to disable)", default=DEFAULT_CSV)
    parser.add_argument("--no-csv", action="store_true", help="Disable CSV logging (overrides --csv)")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit")
    parser.add_argument("--no-color", action="store_true", help="Disable colorized output")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    if args.no_color:
        global Fore, Style
        class _NoColor:
            RED = GREEN = CYAN = MAGENTA = YELLOW = ""
        Fore = _NoColor()
        Style = _NoColor()

    # Resolve symbols/ids into CoinGecko ids
    resolved_coins, mapping = resolve_input_coins(args.coins)
    if not resolved_coins:
        print(Fore.RED + "No coins specified. Exiting.")
        sys.exit(1)

    interval = max(1, args.interval)
    timeout = max(1, args.timeout)
    csv_path = "" if args.no_csv else (args.csv or "")

    if csv_path:
        ensure_csv_header(csv_path, resolved_coins)

    # Show how user inputs were resolved (helpful when using symbols)
    print("Resolved coin inputs:")
    for orig, cid in mapping.items():
        print(f"  {orig} -> {cid}")
    print("Starting tracker for:", ", ".join(resolved_coins))
    print()

    prev_prices: Dict[str, float] = {}

    try:
        while True:
            try:
                data = fetch_prices(resolved_coins, timeout=timeout)
                current_prices = print_prices(resolved_coins, data, prev_prices)

                csv_row_prices: Dict[str, Optional[float]] = {c: current_prices.get(c) for c in resolved_coins}
                if csv_path:
                    append_prices_to_csv(csv_path, resolved_coins, csv_row_prices)

                print(Fore.CYAN + f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                if args.once:
                    break
                print(Fore.MAGENTA + f"Next update in {interval} seconds...")
                prev_prices = {k: v for k, v in current_prices.items() if v is not None}
                time.sleep(interval)

            except requests.RequestException as e:
                print(Fore.RED + "Network/API error: " + str(e))
                print(Fore.MAGENTA + f"Retrying in {interval} seconds...")
                time.sleep(interval)
            except Exception as e:
                print(Fore.RED + "Unexpected error: " + str(e))
                print(Fore.MAGENTA + f"Retrying in {interval} seconds...")
                time.sleep(interval)

    except KeyboardInterrupt:
        print(Style.BRIGHT + "\nExiting (keyboard interrupt). Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()