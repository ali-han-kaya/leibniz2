# Design Note: rn-expo Zero-Surface Claim and ZERO_SIGNATURES Tests

## Overview

This design note explains why a real Expo (rn-expo) application would require amending the existing `zero-surface` claim and the associated `ZERO_SIGNATURES` tests. The current claims were written for synthetic/package-less skill surfaces, but real-world Expo applications have a different package structure and signing pattern.

## Background

The `zero-surface` mechanism in the skill verification pipeline identifies skills/modules that should have zero (no) cryptographic signatures expected. This is based on the `ZERO_SIGNATURES` dictionary in `_calisma/CIKTI/check_skill_surfaces.py`, which currently lists:

```python
ZERO_SIGNATURES = {
    "rn-expo": ["react-native", "expo", "@expo/cli", "expo-image",
                "@react-navigation/native", "@react-navigation/native-stack",
                "@shopify/flash-list", "react-native-reanimated"],
    "wrangler": [...],
    "xlsx": [...]
}
```

The `test_check_skill_surfaces.py` test asserts that for `rn-expo`, all of these packages must be absent from the scanned `package.json` files; if any are found, the test fails with a "zero-surface" violation.

## Problem: Synthetic vs. Real Expo Apps

The current `ZERO_SIGNATURES` claim was designed for **synthetic skill surfaces** — hypothetical or minimally-configured skill packages that have no native dependencies. However, a **real Expo application** fundamentally differs:

### Real Expo App Package Structure

A typical Expo (managed workflow) app has these packages in its `package.json`:

```json
{
  "dependencies": {
    "react": "18.2.0",
    "react-native": "0.73.4",
    "expo": "~51.0.0",
    "expo-image": "~2.0.0",
    "@react-navigation/native": "^6.1.18",
    "@react-navigation/native-stack": "^6.14.4",
    "@shopify/flash-list": "^1.6.0",
    "react-native-reanimated": "^3.8.1"
  }
}
```

All of these packages appear in the current `ZERO_SIGNATURES["rn-expo"]` list, which means a real Expo app would **automatically fail** the zero-surface check — not because it has invalid signatures, but because it legitimately depends on these packages.

### Why This Matters

1. **Fail-closed vs. Reality**: The test is fail-closed by design (any signature found = FAIL), but it was written assuming skill surfaces would have no or minimal dependencies. Real Expo apps inherently depend on the Expo SDK and ecosystem packages.

2. **Intent of zero-surface**: The `zero-surface` claim is meant to flag skills that claim "no signatures needed" but actually have them. For Expo apps, the packages listed are **intentional dependencies**, not missing signatures.

3. **Manifest/signing reality**: In a real Expo workflow, these packages are installed via `expo install` or `npm install` and are part of the normal build. They don't represent "unsigned" code — they're just dependencies that the skill surface verification wasn't designed to account for.

## Required Amendments

### Option A: Remove Expo packages from ZERO_SIGNATURES

If the intent is that Expo apps should not be held to zero-surface strictness (since these are legitimate framework dependencies), the Expo-specific packages should be removed from `ZERO_SIGNATURES["rn-expo"]`:

```python
ZERO_SIGNATURES = {
    "rn-expo": [],  # Empty — Expo apps have legitimate deps
    "wrangler": [...],
    "xlsx": [...]
}
```

This would mean `rn-expo` zero-surface claims are automatically satisfied for any Expo app, since the listed packages are expected.

### Option B: Add Expo-aware exemption logic

Modify `check_skill_surfaces.py` to exclude Expo-fingerprinted packages from the zero-surface check:

```python
# In the zero-surface validation logic
EXPO_EXEMPT_PACKAGES = {"react-native", "expo", "expo-image",
                        "@react-navigation/native", "@react-navigation/native-stack",
                        "@shopify/flash-list", "react-native-reanimated"}

# When checking rn-expo, skip these packages
for domain, signatures in ZERO_SIGNATURES.items():
    if domain == "rn-expo":
        signatures = [s for s in signatures if s not in EXPO_EXEMPT_PACKAGES]
    # ... rest of check
```

### Option C: Create separate zero-surface categories

Distinguish between:
- **True zero-surface**: Skills that claim no signatures but have unrelated unsigned code
- **Expo framework packages**: Skills that legitimately depend on the Expo SDK

This would require changes to both `check_skill_surfaces.py` and `test_check_skill_surfaces.py`.

## Impact on Tests

The `test_check_skill_surfaces.py` test at line 377-381 currently asserts:

```python
for domain in ("rn-expo", "wrangler", "xlsx"):
    self.assertIn(domain, gate.ZERO_SIGNATURES)
self.assertIn("react-native", gate.ZERO_SIGNATURES["rn-expo"])
self.assertIn("expo", gate.ZERO_SIGNATURES["rn-expo"])
# ... etc
```

After amendment, this test would need to either:
- Be updated to reflect the new expected state (empty list or exempted packages)
- Be restructured to test the correct behavior

## Recommendation

**Option A (simplest)**: Remove all Expo packages from `ZERO_SIGNATURES["rn-expo"]` and update the test assertions accordingly. This aligns the verification with reality: Expo apps legitimately depend on these packages, and the zero-surface claim should not flag them.

**Rationale**: The zero-surface mechanism is intended to catch genuinely missing signatures or misconfigured skills, not to enforce that Expo apps have zero dependencies. The current claim creates a false positive for all real-world Expo applications.

## Files That Would Need Updates

1. `_calisma/CIKTI/check_skill_surfaces.py` - `ZERO_SIGNATURES` dict and validation logic
2. `_calisma/CIKTI/test_check_skill_surfaces.py` - test assertions for rn-expo
3. `_calisma/CIKTI/gen_skill_surface_inventory.py` - manifest generation that references zero-surface
4. `docs/SKILL_SURFACE_INVENTORY.md` - documentation of surface inventory
5. `_calisma/CIKTI/skill_surfaces.list` - skill surface inventory list

## Conclusion

The rn-expo zero-surface claim as currently written is incompatible with real Expo application architectures. A real Expo app will always have `react-native`, `expo`, and other SDK packages in its `package.json`, making the current zero-surface check always fail. The claim needs to be amended to either exclude these framework packages or remove them entirely from the zero-surface expectations, with corresponding updates to the test suite.