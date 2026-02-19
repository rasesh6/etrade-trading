#!/usr/bin/env python3
"""
Test script to verify E*TRADE callback OAuth is working.

This script tests if the callback URL is registered with E*TRADE by
attempting to get a request token with a callback URL.
"""

import os
import sys
from requests_oauthlib import OAuth1Session

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_credentials, REQUEST_TOKEN_URL, AUTHORIZE_URL

CALLBACK_URL = "https://web-production-9f73cd.up.railway.app/api/auth/callback"


def test_callback_oauth():
    """Test if callback OAuth is working with E*TRADE"""
    consumer_key, consumer_secret = get_credentials()

    print("=" * 60)
    print("E*TRADE Callback OAuth Test")
    print("=" * 60)
    print(f"Consumer Key: {consumer_key}")
    print(f"Callback URL: {CALLBACK_URL}")
    print(f"Request Token URL: {REQUEST_TOKEN_URL}")
    print("=" * 60)

    try:
        # Create OAuth1Session with callback URL (like pyetrade)
        oauth_session = OAuth1Session(
            consumer_key,
            consumer_secret,
            callback_uri=CALLBACK_URL,
            signature_type='AUTH_HEADER'
        )

        print("\nAttempting to fetch request token with callback URL...")

        # Try to fetch request token
        token = oauth_session.fetch_request_token(REQUEST_TOKEN_URL)

        print("\n" + "=" * 60)
        print("SUCCESS! Callback OAuth is working!")
        print("=" * 60)
        print(f"\nRequest Token: {token.get('oauth_token', 'N/A')[:30]}...")
        print(f"Request Token Secret: {token.get('oauth_token_secret', 'N/A')[:30]}...")
        print(f"\nCallback Confirmed: {token.get('oauth_callback_confirmed', 'N/A')}")

        # Build authorization URL
        request_token = token.get('oauth_token')
        auth_url = f"{AUTHORIZE_URL}?key={consumer_key}&token={request_token}"
        print(f"\nAuthorization URL:\n{auth_url}")

        return True

    except Exception as e:
        error_msg = str(e)

        print("\n" + "=" * 60)
        print("FAILED! Callback OAuth is NOT working")
        print("=" * 60)

        if 'callback_rejected' in error_msg.lower():
            print("\nError: Callback URL was REJECTED by E*TRADE")
            print(f"This means the callback URL is NOT registered with E*TRADE.")
            print(f"\nCallback URL: {CALLBACK_URL}")
            print(f"\nThe API returned: oauth_acceptable_callback=oob")
            print("\nAction Required:")
            print("1. Contact E*TRADE support")
            print("2. Ask them to register this callback URL for your API key")
            print(f"   API Key: {consumer_key}")
            print(f"   Callback URL: {CALLBACK_URL}")
        else:
            print(f"\nError: {error_msg}")

        return False


def test_oob_oauth():
    """Test OOB (out-of-band) OAuth as a baseline"""
    consumer_key, consumer_secret = get_credentials()

    print("\n" + "=" * 60)
    print("E*TRADE OOB OAuth Test (baseline)")
    print("=" * 60)

    try:
        oauth_session = OAuth1Session(
            consumer_key,
            consumer_secret,
            callback_uri='oob',
            signature_type='AUTH_HEADER'
        )

        print("Attempting to fetch request token with OOB...")

        token = oauth_session.fetch_request_token(REQUEST_TOKEN_URL)

        print("SUCCESS! OOB OAuth is working (as expected)")
        print(f"Request Token: {token.get('oauth_token', 'N/A')[:30]}...")

        return True

    except Exception as e:
        print(f"FAILED! Even OOB OAuth is not working: {e}")
        return False


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("E*TRADE Callback OAuth Verification")
    print("=" * 60)

    # First test OOB as baseline
    oob_works = test_oob_oauth()

    # Then test callback
    callback_works = test_callback_oauth()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"OOB OAuth (baseline): {'WORKING' if oob_works else 'FAILED'}")
    print(f"Callback OAuth:       {'WORKING' if callback_works else 'NOT REGISTERED'}")

    if callback_works:
        print("\nYou can now use callback-based OAuth for seamless authentication!")
    else:
        print("\nCallback OAuth is NOT registered. Continue using OOB (manual code entry).")
