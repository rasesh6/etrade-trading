# E*TRADE Order Placement Fix Plan

> **Date:** 2026-02-15
> **Status:** ✅ IMPLEMENTED (2026-02-17)
> **Priority:** HIGH - Core functionality broken

---

## Problem Summary

The order placement feature is NOT working because **E*TRADE requires a preview-then-place flow**, but the current implementation bypasses this requirement.

### Current (Broken) Flow
```
User clicks "Place Order"
    ↓
Frontend calls /api/orders/place directly
    ↓
Server calls client.place_order() WITHOUT preview_id
    ↓
E*TRADE REJECTS the order (missing previewId)
```

### Required (Working) Flow
```
User clicks "Place Order"
    ↓
1. System calls preview_order() → gets previewId + clientOrderId
    ↓
2. System calls place_order() WITH previewId + clientOrderId
    ↓
E*TRADE ACCEPTS the order
```

---

## Root Cause Analysis

### Issue 1: Frontend Bypasses Preview (app.js:516-528)
```javascript
// CURRENT CODE - No preview step!
async function placeOrder() {
    const response = await fetch('/api/orders/place', {
        method: 'POST',
        body: JSON.stringify({ ...order_data })
    });
    // Directly tries to place without preview
}
```

### Issue 2: Server Doesn't Call Preview (server.py:360-432)
```python
# CURRENT CODE - No preview step!
@app.route('/api/orders/place', methods=['POST'])
def place_order():
    # ...validation...
    result = client.place_order(account_id_key, order_data)
    # Calls place_order WITHOUT preview_id parameter
```

### Issue 3: Client Expects Preview ID (etrade_client.py:484-537)
```python
# The client is correctly written but never receives preview_id
def place_order(self, account_id_key, order_data, preview_id=None, client_order_id=None):
    if preview_id:
        logger.info(f"Building place order with previewId: {preview_id}")
    else:
        logger.error("NO PREVIEW_ID - E*TRADE will reject this order!")
```

---

## E*TRADE API Requirements (from research)

1. **previewId is REQUIRED** when placing orders that were previewed
2. **clientOrderId must MATCH** between preview and place calls
3. **All order parameters must match** the preview exactly
4. Without previewId, E*TRADE returns error code 900 or 400

---

## Fix Options

### Option A: Combined Preview+Place Endpoint (Recommended)

Modify `/api/orders/place` to internally call preview first, then place:

```python
@app.route('/api/orders/place', methods=['POST'])
def place_order():
    # Step 1: Preview the order first
    preview_result = client.preview_order(account_id_key, order_data)
    preview_id = preview_result['preview_id']
    client_order_id = preview_result['client_order_id']

    # Step 2: Place with preview data
    result = client.place_order(
        account_id_key,
        order_data,
        preview_id=preview_id,
        client_order_id=client_order_id
    )
    return result
```

**Pros:**
- Simplest fix
- Frontend requires NO changes
- Works with existing UI

**Cons:**
- User doesn't see preview before placing
- Two API calls per order

### Option B: Separate Preview and Confirm Flow

Add new endpoint and modify frontend to show preview before confirming:

```javascript
// Frontend flow
async function placeOrder() {
    // Step 1: Preview
    const preview = await fetch('/api/orders/preview', { ... });
    showPreviewToUser(preview);

    // Step 2: User confirms
    if (userConfirms) {
        const result = await fetch('/api/orders/confirm', {
            preview_id: preview.preview_id,
            client_order_id: preview.client_order_id,
            ...
        });
    }
}
```

**Pros:**
- User sees estimated commission before placing
- Better UX
- Standard trading flow

**Cons:**
- More frontend changes
- More complex

---

## Recommended Fix: Option A (Minimal Change)

### Files to Modify:

1. **server.py** - Update `/api/orders/place` endpoint
2. **(Optional) app.js** - No changes needed for Option A

### Implementation Steps:

1. Modify `server.py` `place_order()` function to:
   - Call `client.preview_order()` first
   - Extract `preview_id` and `client_order_id`
   - Pass both to `client.place_order()`

2. Test with sandbox credentials

3. Deploy to Railway

---

## Testing Plan

### Test Case 1: Market Order
```bash
curl -X POST https://web-production-9f73cd.up.railway.app/api/orders/place \
  -H "Content-Type: application/json" \
  -d '{
    "account_id_key": "...",
    "symbol": "AAPL",
    "quantity": 1,
    "side": "BUY",
    "priceType": "MARKET"
  }'
```

Expected: Order placed successfully with order_id returned

### Test Case 2: Limit Order
```bash
curl -X POST https://web-production-9f73cd.up.railway.app/api/orders/place \
  -H "Content-Type: application/json" \
  -d '{
    "account_id_key": "...",
    "symbol": "AAPL",
    "quantity": 1,
    "side": "BUY",
    "priceType": "LIMIT",
    "limitPrice": 250.00
  }'
```

Expected: Order placed successfully

---

## Rollback Plan

If fix causes issues:
```bash
cd ~/Projects/etrade
git checkout v1.0.0-working
git push origin main --force
```

---

## References

- E*TRADE API Docs: `ETRADE_API_REFERENCE.md`
- Working Version: Tag `v1.0.0-working`
- pyetrade GitHub issues mention previewId requirement

---

## Next Session Action Items

1. [x] Implement Option A fix in `server.py`
2. [ ] Test in sandbox mode
3. [ ] Test in production mode
4. [ ] Update VERSION.md with new tag
5. [ ] Deploy to Railway

---

## Code Snippet for Fix

```python
# server.py - Updated place_order function
@app.route('/api/orders/place', methods=['POST'])
def place_order():
    """Place an order (with automatic preview)"""
    try:
        client = _get_authenticated_client()
        data = request.get_json()

        # ... validation code remains the same ...

        # Build order data
        order_data = {
            'symbol': symbol,
            'quantity': quantity,
            'orderAction': side,
            'priceType': price_type,
            'orderTerm': data.get('orderTerm', 'GOOD_FOR_DAY'),
            'limitPrice': str(limit_price) if limit_price else ''
        }

        # STEP 1: Preview the order first (E*TRADE requirement)
        logger.info(f"Previewing order: {symbol} {side} {quantity} @ {price_type}")
        preview_result = client.preview_order(account_id_key, order_data)

        preview_id = preview_result.get('preview_id')
        client_order_id = preview_result.get('client_order_id')

        if not preview_id:
            raise Exception('Preview failed - no preview_id returned')

        logger.info(f"Preview successful, preview_id={preview_id}")

        # STEP 2: Place the order with preview data
        logger.info(f"Placing order with preview_id={preview_id}")
        result = client.place_order(
            account_id_key,
            order_data,
            preview_id=preview_id,
            client_order_id=client_order_id
        )

        return jsonify({
            'success': True,
            'order': {
                'order_id': result.get('order_id'),
                'symbol': symbol,
                'quantity': quantity,
                'side': side,
                'price_type': price_type,
                'limit_price': limit_price,
                'estimated_commission': preview_result.get('estimated_commission'),
                'message': result.get('message', 'Order placed successfully')
            }
        })

    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
```
