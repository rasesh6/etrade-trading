# E*TRADE Order Placement Fix Plan

> **Date:** 2026-02-15
> **Last Updated:** 2026-02-17 17:10 UTC
> **Status:** 🔧 IN PROGRESS - Fix 3 needed
> **Priority:** HIGH - Core functionality broken

---

## Problem Summary

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

### Option A: Force Railway Rebuild
Railway may have cached the old Docker image. Need to:
1. Make a trivial code change to force rebuild
2. Or clear Railway build cache
3. Or redeploy manually

### Option B: Alternative XML Format
If wrapper change was deployed and still fails, try:
1. Add delay between preview and place
2. Use `<PreviewIds symbol="SOXL">` format
3. Check pyetrade source for working XML format

### Option C: Debug Output
Add more detailed logging to confirm exact XML being sent

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
5. [ ] **Fix 3:** Force Railway rebuild OR try alternative approach
6. [ ] Test Fix 3 in production mode
7. [ ] Update VERSION.md with new tag
8. [ ] Mark as complete in documentation
