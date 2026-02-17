# E*TRADE Order Placement Fix Plan

> **Date:** 2026-02-15
> **Last Updated:** 2026-02-17
> **Status:** 🔧 IN PROGRESS - Fix 2 needed for Error 101
> **Priority:** HIGH - Core functionality broken

---

## Problem Summary

The order placement feature is NOT working because **E*TRADE requires a preview-then-place flow**, but the current implementation has issues.

---

## Fix History

### Fix 1 (2026-02-17): Preview-Then-Place Flow ✅ Implemented
- **Problem:** Server was calling `place_order()` without preview
- **Solution:** Modified `server.py` to call `preview_order()` first, then `place_order()` with preview_id
- **Result:** Preview works, but place still fails with Error 101

### Fix 2 (2026-02-17): XML Structure for previewId 🔧 In Progress
- **Problem:** E*TRADE Error 101 - "For your protection, we have timed out your original order request"
- **Root Cause:** The `<previewId>` XML element structure may be incorrect
- **Current XML:**
  ```xml
  <PlaceOrderRequest>
      <previewId>168289872200</previewId>
      <orderType>EQ</orderType>
      ...
  </PlaceOrderRequest>
  ```
- **E*TRADE may require:** The `PreviewIds` wrapper with symbol information
  ```xml
  <PlaceOrderRequest>
      <PreviewIds>
          <PreviewId>
              <previewId>168289872200</previewId>
              <symbol>SOXL</symbol>  <!-- May need symbol -->
          </PreviewId>
      </PreviewIds>
      <orderType>EQ</orderType>
      ...
  </PlaceOrderRequest>
  ```

---

## Evidence from Logs (2026-02-17 16:55:54 UTC)

```
Preview Response (SUCCESS):
{"PreviewOrderResponse":{...,"Order":[{...}],"PreviewIds":[{"previewId":168289872200}]}}

Place Request (FAILED):
Error 101: "For your protection, we have timed out your original order request"
```

**Key Observations:**
1. Preview returns `PreviewIds` as a **list of objects** with `previewId`
2. Current code uses simple `<previewId>` element without wrapper
3. E*TRADE may require matching the response structure with `<PreviewIds>` wrapper

---

## E*TRADE API Requirements (from research)

1. **previewId is REQUIRED** when placing orders that were previewed
2. **clientOrderId must MATCH** between preview and place calls
3. **All order parameters must match** the preview exactly
4. **PreviewIds structure** may need to match the response format
5. Error 101 typically means preview session issue or XML format mismatch

---

## Fix 2 Implementation Plan

### File to Modify: `etrade_client.py`

Update `_build_order_payload()` function to use proper `PreviewIds` structure:

```python
# Current (broken):
if preview_id:
    preview_id_element = f'<previewId>{preview_id}</previewId>\n    '

# Fixed:
if preview_id:
    symbol = order_data.get('symbol', '').upper()
    preview_id_element = f'''<PreviewIds>
        <PreviewId>
            <previewId>{preview_id}</previewId>
        </PreviewId>
    </PreviewIds>
    '''
```

---

## Testing Plan

### Test Case: Limit Order
```bash
curl -X POST https://web-production-9f73cd.up.railway.app/api/orders/place \
  -H "Content-Type: application/json" \
  -d '{
    "account_id_key": "nJwwXIOSGgn6IAzTOdUV0w",
    "symbol": "SOXL",
    "quantity": 1,
    "side": "BUY",
    "priceType": "LIMIT",
    "limitPrice": 63
  }'
```

Expected: Order placed successfully with order_id returned

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
3. [ ] Implement Fix 2: Proper PreviewIds XML structure in `etrade_client.py`
4. [ ] Test Fix 2 in production mode
5. [ ] Update VERSION.md with new tag
6. [ ] Mark as complete in documentation
