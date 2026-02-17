#!/usr/bin/env python3
"""Test placing order WITHOUT preview - direct placement"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from etrade_client import ETradeClient
from token_manager import get_token_manager

def test_place_without_preview():
    # Get tokens
    token_manager = get_token_manager()
    tokens = token_manager.get_tokens()

    if not tokens:
        print("ERROR: Not authenticated. Run the web app and login first.")
        return

    # Create client
    client = ETradeClient()
    client.set_session(tokens['access_token'], tokens['access_token_secret'])

    # Account key
    account_id_key = "ajPzzppKg8pyOORwqnRE6w"  # Active Trading

    # Order data
    order_data = {
        'symbol': 'AAPL',
        'quantity': 1,
        'orderAction': 'BUY',
        'priceType': 'LIMIT',
        'orderTerm': 'GOOD_FOR_DAY',
        'limitPrice': '255.00'  # Low price so it won't fill
    }

    print("=" * 60)
    print("TESTING: Place order WITHOUT preview")
    print("=" * 60)
    print(f"Symbol: {order_data['symbol']}")
    print(f"Side: {order_data['orderAction']}")
    print(f"Qty: {order_data['quantity']}")
    print(f"Price: {order_data['limitPrice']}")
    print(f"Account: {account_id_key}")
    print("=" * 60)

    try:
        # Place order WITHOUT preview_id
        result = client.place_order(
            account_id_key,
            order_data,
            preview_id=None,  # NO PREVIEW
            client_order_id=None  # Generate new
        )
        print("\nSUCCESS!")
        print(f"Result: {result}")
    except Exception as e:
        print(f"\nFAILED: {e}")

if __name__ == '__main__':
    test_place_without_preview()
