# E*TRADE Order Placement Fix Plan

> **Date:** 2026-02-15
> **Last Updated:** 2026-02-17 18:00 UTC
> **Status:** 🔧 IN PROGRESS - Order issue paused, implementing callback URL first
> **Priority:** HIGH - Core functionality broken

---

## Baseline Versions

- **v1.0.0-callback-baseline**: Manual verification code OAuth flow (working)
  - Created: 2026-02-17
  - This is the fallback if callback URL implementation has issues

---

## Callback URL Implementation (2026-02-17)

### Status: ✅ IMPLEMENTED, awaiting testing

### Changes Made:
1. **etrade_client.py**:
   - Added `callback_url` parameter to `get_authorization_url()`
   - Now supports both `'oob'` (manual) and callback URL modes

2. **server.py**:
   - Added `CALLBACK_URL` constant: `https://web-production-9f73cd.up.railway.app/api/auth/callback`
   - Added new `/api/auth/callback` endpoint to handle E*TRADE redirect
   - Stores request tokens keyed by request token (not flow_id)
   - Handles success/error redirects

3. **templates/index.html**:
   - Updated auth section to remove manual verification code input
   - Simplified flow for callback-based authentication

4. **static/js/app.js**:
   - Added `handleCallbackParams()` to process `auth_success` and `auth_error` URL params
   - Updated `startLogin()` to open auth in new window and poll for status
   - Added `pollAuthStatus()` to auto-detect successful authentication

### New OAuth Flow:
1. User clicks "Connect to E*TRADE"
2. Server generates auth URL with callback URL
3. User authorizes on E*TRADE
4. E*TRADE redirects to callback URL with `oauth_token` and `oauth_verifier`
5. Server exchanges tokens automatically
6. Server redirects to `/?auth_success=true`
7. Frontend polls auth status and updates UI

### Rollback if Needed:
```bash
git checkout v1.0.0-callback-baseline
# Revert to manual verification code flow
```

---

## Problem Summary (Order Placement)

The order placement feature is NOT working because **E*TRADE requires a preview-then-place flow**, but the current implementation has issues with Error 101.

---

## Fix History

### Fix 1 (2026-02-17): Preview-Then-Place Flow ✅ Implemented
- **Problem:** Server was calling `place_order()` without preview
- **Solution:** Modified `server.py` to call `preview_order()` first, then `place_order()` with preview_id
- **Result:** Preview works, but place still fails with Error 101

### Fix 2 (2026-02-17): XML Structure for previewId ❌ Did NOT Work
- **Problem:** E*TRADE Error 101 - "For your protection, we have timed out your original order request"
- **Attempted Solution:** Changed XML from `<previewId>` to `<PreviewIds><PreviewId>` wrapper
- **Result:** Still getting Error 101
- **Evidence from Railway (2026-02-17 17:04:52 UTC):**
  ```
  Preview Response (SUCCESS):
  {"PreviewOrderResponse":{..., "PreviewIds":[{"previewId":168321663200}]}}

  Place Request XML Sent:
  <PlaceOrderRequest>
      <previewId>168321663200</previewId>  <!-- STILL SHOWING OLD FORMAT! -->
      <clientOrderId>7876847538</clientOrderId>
      ...
  </PlaceOrderRequest>

  Place Response (FAILED):
  {"Error":{"code":101,"message":"For your protection, we have timed out your original order request..."}}
  ```

- **Key Finding:** Railway logs show OLD `<previewId>` format, NOT the new `<PreviewIds>` wrapper
  - This suggests either:
    1. Railway cached the old Docker image
    2. The fix wasn't deployed properly
    3. Need to force a fresh rebuild

---

## Current Understanding

### What We Know Works:
1. ✅ OAuth authentication works
2. ✅ Account list, balance, portfolio APIs work
3. ✅ Quote API works
4. ✅ Preview order works - returns valid `previewId` and `clientOrderId`
5. ✅ `clientOrderId` matches between preview and place calls

### What's Broken:
1. ❌ Place order always returns Error 101

### Error 101 Possible Causes:
1. XML format is still wrong (Railway may not have deployed fix)
2. Preview session timing issue
3. Order parameters mismatch between preview and place
4. E*TRADE sandbox-specific behavior

---

## Next Steps (Fix 3)

### Fix 3 (2026-02-17): Deployment Marker + Delay ✅ DEPLOYED, ❌ Still Error 101
- **Problem:** Fix 2 may not have been deployed to Railway
- **Solution:**
  1. Added deployment marker `DEPLOYMENT MARKER: FIX3-2026-02-17-1712` to confirm code is deployed
  2. Added 500ms delay between preview and place
  3. Added DEBUG logging for PreviewIds wrapper usage
- **Result:**
  - ✅ Deployment marker confirmed in Railway logs
  - ✅ XML now shows correct `<PreviewIds>` wrapper structure
  - ❌ Still getting Error 101 from E*TRADE
- **Key Finding:** PreviewIds wrapper format IS correct, but Error 101 persists
- **Evidence from Railway (2026-02-17 17:19 UTC):**
  ```
  DEPLOYMENT MARKER: FIX3-2026-02-17-1712
  DEBUG: Using PreviewIds wrapper for preview_id=168359279200

  FULL PLACE ORDER PAYLOAD:
  <PlaceOrderRequest>
      <PreviewIds>
          <PreviewId>
              <previewId>168359279200</previewId>
          </PreviewId>
      </PreviewIds>
      <orderType>EQ</orderType>
      <clientOrderId>2830665722</clientOrderId>
      ...
  </PlaceOrderRequest>

  (Error 101 still returned - need to see full response)
  ```

---

## Next Steps (Fix 4)

Since the PreviewIds wrapper is correct but Error 101 persists, investigate:

### Option A: Research pyetrade Implementation
Check the pyetrade library source for how they handle place order:
1. Look at their XML format for PreviewIds
2. Check if they use any additional headers or parameters
3. Compare their approach with ours

### Option B: Different PreviewIds Format
The response shows: `[{'previewId': 168359279200}]` (symbol is empty)
Try formats:
1. `<PreviewIds><previewId>168359279200</previewId></PreviewIds>` (flat, no wrapper)
2. `<previewId>168359279200</previewId>` (original simple format)

### Option C: Check Order Parameter Matching
Verify ALL parameters match between preview and place:
1. Compare full XML payloads
2. Check if any fields are missing or different

### Option D: Try Without Delay
The 500ms delay might be causing issues. Try:
1. Remove the delay
2. Place immediately after preview

### Option E: Check E*TRADE Production Requirements
Production API may have different requirements than sandbox:
1. Check E*TRADE production docs
2. Look for production-specific headers or parameters

---

## Evidence from Logs (2026-02-17 17:04:52 UTC)

```
Preview Request:
- symbol: SOXL
- quantity: 1
- side: BUY
- priceType: LIMIT
- limitPrice: 64.59
- clientOrderId: 7876847538

Preview Response (SUCCESS):
{"PreviewOrderResponse":{
    "orderType":"EQ",
    "totalOrderValue":64.59,
    "previewTime":1771347892616,
    "accountId":"133368516",
    "Order":[{...}],
    "PreviewIds":[{"previewId":168321663200}]
}}

Place Request:
- previewId: 168321663200
- clientOrderId: 7876847538 (MATCHES)

Place Response (FAILED):
{"Error":{"code":101,"message":"For your protection, we have timed out your original order request..."}}
```

---

## E*TRADE API Requirements (from research)

1. **previewId is REQUIRED** when placing orders that were previewed
2. **clientOrderId must MATCH** between preview and place calls
3. **All order parameters must match** the preview exactly
4. **PreviewIds structure** may need to match the response format
5. Error 101 typically means preview session issue or XML format mismatch

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

## Session Action Items

1. [x] Implement Fix 1: Preview-then-place flow in `server.py`
2. [x] Test Fix 1 - Got Error 101
3. [x] Implement Fix 2: Proper PreviewIds XML structure in `etrade_client.py`
4. [x] Test Fix 2 - Still Error 101 (may not have deployed)
5. [x] **Fix 3:** Force Railway rebuild + add deployment marker
6. [x] Test Fix 3 - PreviewIds wrapper confirmed, still Error 101
7. [ ] **Fix 4:** Research pyetrade or try alternative XML formats
8. [ ] Test Fix 4 in production mode
9. [ ] Update VERSION.md with new tag
10. [ ] Mark as complete in documentation
