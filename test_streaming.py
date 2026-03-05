#!/usr/bin/env python3
"""
E*TRADE Streaming API - CometD/Bayeux Feasibility Test

Tests whether E*TRADE's documented Comet/Bayeux streaming API is accessible
and can be used for push-based order fill notifications.

Prerequisites:
    - Valid OAuth tokens (authenticate via web UI first)
    - pip install aiocometd aiohttp

Usage:
    python test_streaming.py
"""
import asyncio
import logging
import sys
from urllib.parse import urlencode

import aiohttp
from requests_oauthlib import OAuth1

from config import get_credentials, get_base_url, PROD_BASE_URL
from token_manager import get_token_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Candidate CometD endpoints to test
COMETD_ENDPOINTS = [
    'https://api.etrade.com/cometd/cometd',
    'https://api.etrade.com/cometd',
    'https://etwscometd.etrade.com/cometd/cometd',
    'https://etwscometd.etrade.com/cometd',
    # v0 API variants
    'https://api.etrade.com/v0/cometd',
    'https://api.etrade.com/streaming/cometd',
]

# Channels to try subscribing to if handshake succeeds
SUBSCRIBE_CHANNELS = [
    '/order/events',
    '/order/status',
    '/orders',
    '/notifications',
    '/account/orders',
]


def get_oauth_headers(url, method='POST', body=None):
    """
    Generate OAuth1 Authorization header for a request.

    Uses requests-oauthlib to sign the request the same way
    the REST API calls are signed in etrade_client.py.
    """
    consumer_key, consumer_secret = get_credentials()
    tm = get_token_manager()
    tokens = tm.get_tokens()

    if not tokens:
        logger.error("No valid OAuth tokens found. Authenticate via web UI first.")
        sys.exit(1)

    oauth = OAuth1(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=tokens['access_token'],
        resource_owner_secret=tokens['access_token_secret'],
        signature_method='HMAC-SHA1',
        signature_type='auth_header',
        realm=''
    )

    # Use a mock request to generate the Authorization header
    import requests
    req = requests.Request(method, url, data=body)
    prepared = req.prepare()
    oauth(prepared)  # signs in-place

    return {k: (v.decode() if isinstance(v, bytes) else v) for k, v in prepared.headers.items()}


async def test_cometd_handshake(session, endpoint):
    """
    Attempt a CometD/Bayeux handshake at the given endpoint.

    The Bayeux handshake is a POST with:
    [{"channel": "/meta/handshake",
      "version": "1.0",
      "supportedConnectionTypes": ["long-polling"],
      "minimumVersion": "1.0"}]

    Returns (success: bool, detail: str)
    """
    handshake_msg = [{
        'channel': '/meta/handshake',
        'version': '1.0',
        'supportedConnectionTypes': ['long-polling'],
        'minimumVersion': '1.0'
    }]

    # Get OAuth headers for this endpoint
    try:
        oauth_headers = get_oauth_headers(endpoint)
    except Exception as e:
        return False, f"OAuth signing failed: {e}"

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    # Merge OAuth Authorization header
    if 'Authorization' in oauth_headers:
        headers['Authorization'] = oauth_headers['Authorization']

    try:
        async with session.post(
            endpoint,
            json=handshake_msg,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            status = resp.status
            content_type = resp.headers.get('Content-Type', '')
            # Read raw bytes to handle truncated responses
            try:
                body_bytes = await resp.read()
                body_text = body_bytes.decode('utf-8', errors='replace')
            except Exception:
                body_text = ''

            logger.info(f"  Status: {status}")
            logger.info(f"  Content-Type: {content_type}")
            logger.info(f"  Body (first 500 chars): {body_text[:500]}")

            if status == 200:
                # Try to parse as Bayeux response
                try:
                    import json
                    data = json.loads(body_text)
                    if isinstance(data, list) and len(data) > 0:
                        msg = data[0]
                        if msg.get('successful'):
                            client_id = msg.get('clientId', 'unknown')
                            return True, f"Handshake SUCCESS! clientId={client_id}"
                        else:
                            error = msg.get('error', 'unknown error')
                            return False, f"Handshake returned successful=false: {error}"
                    else:
                        return False, f"Unexpected JSON response: {body_text[:200]}"
                except json.JSONDecodeError:
                    return False, f"200 OK but non-JSON response: {body_text[:200]}"
            elif status == 404:
                return False, f"404 Not Found: {body_text[:200]}"
            elif status == 401:
                return False, f"401 Unauthorized: {body_text[:200]}"
            elif status == 403:
                return False, f"403 Forbidden: {body_text[:200]}"
            elif status == 500:
                return False, f"500 Server Error: {body_text[:200]}"
            else:
                return False, f"HTTP {status}: {body_text[:200]}"

    except asyncio.TimeoutError:
        return False, "Connection timed out (15s)"
    except aiohttp.ClientConnectorError as e:
        return False, f"Connection refused: {e}"
    except Exception as e:
        return False, f"Error: {e}"


async def test_subscribe(session, endpoint, client_id, channel):
    """
    Attempt to subscribe to a channel after a successful handshake.

    Returns (success: bool, detail: str)
    """
    subscribe_msg = [{
        'channel': '/meta/subscribe',
        'clientId': client_id,
        'subscription': channel
    }]

    oauth_headers = get_oauth_headers(endpoint)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if 'Authorization' in oauth_headers:
        headers['Authorization'] = oauth_headers['Authorization']

    try:
        async with session.post(
            endpoint,
            json=subscribe_msg,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            status = resp.status
            body_text = await resp.text()
            logger.info(f"    Subscribe {channel}: status={status}, body={body_text[:300]}")

            if status == 200:
                try:
                    import json
                    data = json.loads(body_text)
                    if isinstance(data, list) and len(data) > 0:
                        msg = data[0]
                        if msg.get('successful'):
                            return True, f"Subscribed to {channel}"
                        else:
                            error = msg.get('error', 'unknown')
                            return False, f"Subscribe failed: {error}"
                except Exception:
                    pass
            return False, f"HTTP {status}: {body_text[:200]}"
    except Exception as e:
        return False, f"Error: {e}"


async def test_connect_listen(session, endpoint, client_id, duration=10):
    """
    After subscribing, do a long-poll connect to listen for events.

    Returns any messages received within the duration.
    """
    connect_msg = [{
        'channel': '/meta/connect',
        'clientId': client_id,
        'connectionType': 'long-polling'
    }]

    oauth_headers = get_oauth_headers(endpoint)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if 'Authorization' in oauth_headers:
        headers['Authorization'] = oauth_headers['Authorization']

    logger.info(f"  Listening for events ({duration}s long-poll)...")

    try:
        async with session.post(
            endpoint,
            json=connect_msg,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=duration + 5)
        ) as resp:
            body_text = await resp.text()
            logger.info(f"  Connect response: status={resp.status}, body={body_text[:500]}")
            return body_text
    except asyncio.TimeoutError:
        logger.info(f"  Long-poll timed out after {duration}s (expected behavior)")
        return None
    except Exception as e:
        logger.info(f"  Connect error: {e}")
        return None


async def main():
    print("=" * 70)
    print("E*TRADE Streaming API (CometD/Bayeux) Feasibility Test")
    print("=" * 70)
    print()

    # Verify we have valid tokens
    tm = get_token_manager()
    tokens = tm.get_tokens()
    if not tokens:
        print("ERROR: No valid OAuth tokens. Please authenticate via the web UI first.")
        print("  1. Run: python server.py")
        print("  2. Open http://localhost:5000")
        print("  3. Complete OAuth login")
        print("  4. Then re-run this script")
        sys.exit(1)

    print(f"OAuth tokens found (access_token starts with: {tokens['access_token'][:20]}...)")
    print()

    results = {}

    async with aiohttp.ClientSession() as session:
        # Phase 1: Test handshake on all endpoints
        print("-" * 70)
        print("Phase 1: Testing CometD Handshake Endpoints")
        print("-" * 70)

        successful_endpoint = None
        successful_client_id = None

        for endpoint in COMETD_ENDPOINTS:
            print(f"\nTesting: {endpoint}")
            success, detail = await test_cometd_handshake(session, endpoint)
            results[endpoint] = {'handshake': (success, detail)}

            if success:
                print(f"  PASS: {detail}")
                successful_endpoint = endpoint
                # Extract clientId from detail
                if 'clientId=' in detail:
                    successful_client_id = detail.split('clientId=')[1]
            else:
                print(f"  FAIL: {detail}")

        # Phase 2: If handshake succeeded, try subscribing
        if successful_endpoint and successful_client_id:
            print()
            print("-" * 70)
            print(f"Phase 2: Testing Channel Subscriptions on {successful_endpoint}")
            print("-" * 70)

            successful_channel = None
            for channel in SUBSCRIBE_CHANNELS:
                print(f"\n  Subscribing to: {channel}")
                success, detail = await test_subscribe(
                    session, successful_endpoint, successful_client_id, channel
                )
                if success:
                    print(f"    PASS: {detail}")
                    successful_channel = channel
                else:
                    print(f"    FAIL: {detail}")

            # Phase 3: If subscribed, try listening
            if successful_channel:
                print()
                print("-" * 70)
                print("Phase 3: Listening for Events (10s)")
                print("-" * 70)
                result = await test_connect_listen(
                    session, successful_endpoint, successful_client_id, duration=10
                )
                if result:
                    print(f"  Received: {result[:500]}")
                else:
                    print("  No events received (expected if no orders are active)")

    # Summary
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    any_success = False
    for endpoint, result in results.items():
        success, detail = result['handshake']
        status = "PASS" if success else "FAIL"
        if success:
            any_success = True
        print(f"  [{status}] {endpoint}")
        print(f"         {detail}")

    print()
    if any_success:
        print("VERDICT: Streaming API IS accessible!")
        print("Next step: Build full integration (server-side streaming client)")
    else:
        print("VERDICT: Streaming API is NOT accessible via any tested endpoint.")
        print("Next step: Proceed with Plan B (server-side REST polling + SSE to frontend)")
    print()


if __name__ == '__main__':
    asyncio.run(main())
