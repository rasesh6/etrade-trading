# E*TRADE Order Placement Fix Plan

> **Date:** 2026-02-15
> **Last Updated:** 2026-02-18 14:35 UTC
> **Status:** 🔧 IN PROGRESS - Fix 4 implemented, needs testing
> **Priority:** HIGH - Core functionality broken

---

## Problem Summary

The order placement feature is NOT working because **E*TRADE requires a preview-then-place flow**, and the XML format for `previewId` was incorrect.

---

## Fix History

### Fix 1 (2026-02-17): Preview-Then-Place Flow ✅ Implemented
- **Problem:** Server was calling `place_order()` without preview
- **Solution:** Modified `server.py` to call `preview_order()` first, then `place_order()` with preview_id
- **Result:** Preview works, but place still fails with Error 101

### Fix 2 (2026-02-17): XML Structure for previewId ❌ Did NOT Work
- **Problem:** E*TRADE Error 101
- **Attempted Solution:** Changed XML format
- **Result:** Still getting Error 101

### Fix 3 (2026-02-17): Removed Delay ❌ Did NOT Work
- **Problem:** Thought timing issue was causing timeout
- **Solution:** Removed 1-second delay between preview and place
- **Result:** Still getting Error 101/1033

### Fix 4 (2026-02-18): Correct PreviewIds XML Format ⏳ TESTING
- **Root Cause Found:** By analyzing pyetrade library source code (order.py lines 400-401):
  ```python
  if "previewId" in kwargs:
      payload[order_type]["PreviewIds"] = {"previewId": kwargs["previewId"]}
  ```
- **Problem:** We were using `<previewId>` directly, but E*TRADE requires `<PreviewIds>` wrapper
- **Wrong Format:**
  ```xml
  <PlaceOrderRequest>
      <previewId>168321663200</previewId>
      ...
  </PlaceOrderRequest>
  ```
- **Correct Format:**
  ```xml
  <PlaceOrderRequest>
      <PreviewIds><previewId>168321663200</previewId></PreviewIds>
      ...
  </PlaceOrderRequest>
  ```
- **Solution:** Updated `_build_order_payload()` in `etrade_client.py`
- **Status:** Needs deployment and testing

---

## Key Learning from pyetrade

The pyetrade library (a known working implementation) shows the correct XML format:

1. **PreviewIds wrapper is REQUIRED** - not just `previewId`
2. **pyetrade does preview+place in same function** - no timing issues
3. **Capitalization matters**: `<PreviewIds>` (capital P, capital I, plural)

---

## Next Steps

1. [ ] Deploy to Railway (push changes)
2. [ ] Test order placement via UI
3. [ ] Verify success in Railway logs (look for FIX4-2026-02-18 marker)
4. [ ] Update VERSION.md if successful
5. [ ] Close this issue

---

## References

- E*TRADE API Docs: `ETRADE_API_REFERENCE.md`
- pyetrade source: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
- Working Version: Tag `v1.0.0-working`
