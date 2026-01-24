# TMT Login Command Test Suite Summary

This document describes all 65 test scenarios for the `tmt login` command, covering various combinations of options including `-t` (test mode), `--when` (conditional login), `--step` (login at specific step), and result types.

---

## Understanding and Purpose

### The Problem

GitHub Issue [#1918](https://github.com/teemtee/tmt/issues/1918) describes a bug in the `tmt login` command:

When using `login -t` (test mode), the command incorrectly triggers login in **BOTH** the execute step (after each test) AND the finish step (at the end). This is unintended behavior because:

1. The `-t` flag is specifically designed for **per-test** login during the execute step
2. Users expect `login -t` to only log in after each test, not again at the end
3. This duplicate login is confusing and wastes time

### Root Cause

The bug is in `tmt/steps/__init__.py` in the `Login._parse_phases()` method:

- When no `--step` is provided, it defaults to the **last enabled step** (typically `finish`)
- The `-t` flag sets `Login._enabled = True` for per-test behavior
- But it doesn't prevent the default step (finish) from also triggering login

**Result**: `login -t` → login in execute (per-test) AND login in finish (default step)

### The Solution

PR [#1933](https://github.com/teemtee/tmt/pull/1933) proposes the fix:

**When `-t` is used without explicit `--step`, implicitly add `--step execute`**

This ensures that:
- `login -t` only logs in during execute step (per-test)
- `login -t --when fail` only logs in after failing tests (in execute)
- No duplicate login in finish step

**Important exception**: Explicit `--step` should override this implicit behavior:
- `login -t --step finish` → login in finish step (intentional, not per-test)
- `login -t --when fail --step finish` → login in finish if any test fails

### What We Want To Do

1. **Document all scenarios**: Create comprehensive test coverage for all possible `login` command combinations
2. **Define expected behavior**: Establish clear rules for how each option combination should work
3. **Create test suite**: Write 65 beakerlib tests that verify the correct behavior
4. **Fix the bug**: Implement the solution in PR #1933
5. **Verify with tests**: Run the test suite to ensure the fix works and doesn't break existing functionality

### Test Categories

| Category | Purpose | Count |
|----------|---------|-------|
| **Base (B-01 to B-15)** | Default behavior without `-t` flag | 15 |
| **Test Mode (T-01 to T-12)** | Per-test login with `-t` flag | 12 |
| **Combined (C-01 to C-10)** | Multiple option combinations | 10 |
| **Multiple Conditions (M-01 to M-08)** | Multiple `--when` clauses | 8 |
| **Edge Cases (E-01 to E-15)** | Boundary conditions | 15 |
| **Result Variations (R-01 to R-05)** | Different result types | 5 |
| **Total** | | **65** |

---

## Background

The `tmt login` command provides interactive shell access during test execution with several key options:

- `-t, --test`: Login after each test during execute step (same environment as test)
- `--when RESULT`: Conditional login based on test result (`pass`, `fail`, `error`, `warn`, `info`)
- `--step STEP[:PHASE]`: Login during specific step (`discover`, `provision`, `prepare`, `execute`, `finish`, `report`)
- `--command CMD`: Run specific command instead of default shell

**Key difference**: `-t` triggers per-test login in execute step, while `--when` triggers at the end of finish step (or specified step).

---

## B-01 to B-15: Base Scenarios

Default behavior without `-t` flag.

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **B-01** | Default login (no options) | `login -c true` | Login at end of finish step (default step) |
| **B-02** | Login with --when fail | `login --when fail -c true` | Login in finish step only if test fails |
| **B-03** | Login with --when error | `login --when error -c true` | Login in finish step only if test errors |
| **B-04** | Login with --when pass | `login --when pass -c true` | Login in finish step only if test passes |
| **B-05** | Login with --when warn | `login --when warn -c true` | Login in finish step if test has warnings |
| **B-06** | Login with --step execute | `login --step execute -c true` | Login during execute step (after all tests) |
| **B-07** | Login with --step finish | `login --step finish -c true` | Login during finish step |
| **B-08** | Login with --step prepare | `login --step prepare -c true` | Login during prepare step |
| **B-09** | Login with --when fail --step execute | `login --when fail --step execute -c true` | Login in execute step only if test fails |
| **B-10** | Login with --when error --step execute | `login --when error --step execute -c true` | Login in execute step only if test errors |
| **B-11** | Login with --when pass --step execute | `login --when pass --step execute -c true` | Login in execute step only if test passes |
| **B-12** | Login with --step discover | `login --step discover -c true` | Error: No guests ready during discover |
| **B-13** | Login with --step provision | `login --step provision -c true` | Error: No guests ready during provision |
| **B-14** | Login with --step report | `login --step report -c true` | Login during report step |
| **B-15** | Login with --when info | `login --when info -c true` | Login in finish step if test has info messages |

---

## T-01 to T-12: Test Mode Scenarios

Tests with `-t` flag (per-test login during execute step).

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **T-01** | Login -t (test mode) | `login -t -c true` | Login after each test in execute step |
| **T-02** | Login -t --when fail | `login -t --when fail -c true` | Login after each failing test in execute |
| **T-03** | Login -t --when error | `login -t --when error -c true` | Login after each errored test in execute |
| **T-04** | Login -t --when pass | `login -t --when pass -c true` | Login after each passing test in execute |
| **T-05** | Login -t --step finish | `login -t --step finish -c true` | Login at end of finish step (not per-test) |
| **T-06** | Login -t --step prepare | `login -t --step prepare -c true` | Login during prepare step (not per-test) |
| **T-07** | Login -t --when warn | `login -t --when warn -c true` | Login after each test with warnings |
| **T-08** | Login -t --when info | `login -t --when info -c true` | Login after each test with info messages |
| **T-09** | Login -t --step provision | `login -t --step provision -c true` | Login during provision step |
| **T-10** | Login -t --step discover | `login -t --step discover -c true` | Error: No guests ready during discover |
| **T-11** | Login -t --step report | `login -t --step report -c true` | Login during report step (not per-test) |
| **T-12** | Login -t --step execute | `login -t --step execute -c true` | Login after each test in execute (same as -t) |

---

## C-01 to C-10: Combined Scenarios

Tests combining multiple options.

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **C-01** | Login -t --when fail --step finish | `login -t --when fail --step finish -c true` | Login in finish step if any test fails (not per-test) |
| **C-02** | Login -t --step execute:finish | `login -t --step execute:finish -c true` | Login in both execute (after tests) AND finish steps |
| **C-03** | Login --when fail --when error | `login --when fail --when error -c true` | Login in finish if any test fails or errors |
| **C-04** | Login -t --when fail --when error | `login -t --when fail --when error -c true` | Login in execute after each fail/error test |
| **C-05** | Login -t --when error --step finish | `login -t --when error --step finish -c true` | Login in finish if any test errors (not per-test) |
| **C-06** | Login -t --step prepare:finish | `login -t --step prepare:finish -c true` | Login in both prepare AND finish steps |
| **C-07** | Login -t --when fail --step execute:finish | `login -t --when fail --step execute:finish -c true` | Login in execute (fail tests) AND finish (if any fail) |
| **C-08** | Login --when pass --when fail | `login --when pass --when fail -c true` | Login in finish for any passing or failing test |
| **C-09** | Login --when fail --step finish | `login --when fail --step finish -c true` | Login in finish if any test fails |
| **C-10** | Login -t --when pass --when fail | `login -t --when pass --when fail -c true` | Login in execute after each pass/fail test |

---

## M-01 to M-08: Multiple Conditions

Tests with multiple `--when` clauses.

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **M-01** | Login --when fail --when error | `login --when fail --when error -c true` | Login in finish if any test fails or errors |
| **M-02** | Login --when fail --when warn | `login --when fail --when warn -c true` | Login in finish if any test fails or has warnings |
| **M-03** | Login -t --when fail --when error | `login -t --when fail --when error -c true` | Login in execute after each fail/error test |
| **M-04** | Login --when error --when warn | `login --when error --when warn -c true` | Login in finish if any test errors or has warnings |
| **M-05** | Login -t --when fail --when warn | `login -t --when fail --when warn -c true` | Login in execute after each fail/warn test |
| **M-06** | Login --when pass --when fail --when error | `login --when pass --when fail --when error -c true` | Login in finish for pass, fail, or error |
| **M-07** | Login -t --when pass --when fail | `login -t --when pass --when fail -c true` | Login in execute after each pass/fail test |
| **M-08** | Login -t --when fail --when error --step finish | `login -t --when fail --when error --step finish -c true` | Login in finish if any test fails or errors |

---

## E-01 to E-15: Edge Cases

Boundary conditions and special scenarios.

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **E-01** | Login -t (all tests pass) | `login -t -c true` (all tests pass) | Login after each passing test |
| **E-02** | Login -t --when fail (all fail) | `login -t --when fail -c true` (all fail) | Login after each failing test (3 logins for 3 tests) |
| **E-03** | Login --when fail --step prepare | `login --when fail --step prepare -c true` | Login in prepare step if any test fails (future-looking) |
| **E-04** | Login -t --step execute | `login -t --step execute -c true` | Same as `login -t`, login after each test |
| **E-05** | Login -t --when pass (all pass) | `login -t --when pass -c true` (all pass) | Login after each passing test |
| **E-06** | Login -t (no tests) | `login -t -c true` (no tests) | No login occurs (no tests to trigger) |
| **E-07** | Login --when fail (no tests) | `login --when fail -c true` (no tests) | No login occurs (no failed tests) |
| **E-08** | Login --when fail (all pass) | `login --when fail -c true` (all pass) | No login (no failed tests) |
| **E-09** | Login -t --step provision | `login -t --step provision -c true` | Login during provision step |
| **E-10** | Login -t --step discover | `login -t --step discover -c true` | Error: No guests ready during discover |
| **E-11** | Login -t --step report | `login -t --step report -c true` | Single login in report step (not per-test) |
| **E-12** | Login -t --when fail (all fail) | `login -t --when fail -c true` (all fail) | Login after each failing test (3 logins) |
| **E-13** | Login -t --step execute:finish | `login -t --step execute:finish -c true` | Login in execute (per-test) AND finish steps |
| **E-14** | Login -t with single test | `login -t -c true` (1 test) | 1 login in execute (matches Issue #1918 scenario) |
| **E-15** | Login -t with local provision | `login -t -c true` (local provision) | Login per-test with local provision |

---

## R-01 to R-05: Result Variations

Tests covering different result types (`pass`, `fail`, `error`, `warn`, `info`).

| Test | Summary | Command | Expected Behavior |
|------|---------|---------|-------------------|
| **R-01** | Result type - pass | `login --when pass -c true` | Login in finish if any test passes |
| **R-02** | Result type - fail | `login --when fail -c true` | Login in finish if any test fails |
| **R-03** | Result type - error | `login --when error -c true` | Login in finish if any test errors |
| **R-04** | Result type - warn | `login --when warn -c true` | Login in finish if any test has warnings |
| **R-05** | Result type - info | `login --when info -c true` | Login in finish if any test has info messages |

---

## Key Behavioral Rules

### 1. Step Hierarchy
- Without `--step`, login defaults to the **last enabled step** (typically `finish`)
- With `--step`, login occurs at the specified step

### 2. Test Mode (-t)
- `-t` means "per-test" during execute step
- Without explicit `--step execute`, `-t` should implicitly add `--step execute`
- `-t` with explicit `--step finish` disables per-test behavior, logs once at end

### 3. When Conditions
- `--when RESULT` filters when login should occur based on test results
- Multiple `--when` conditions are OR'd together (login if ANY condition matches)
- With `-t`, conditions are evaluated per-test
- Without `-t`, conditions are evaluated at the end (finish step)

### 4. Step Availability
- `discover`: No guests ready → Error
- `provision`: No guests ready → Error
- `prepare`: Guests available → Login works
- `execute`: Guests available → Login works (per-test with `-t`)
- `finish`: Guests available → Login works (default)
- `report`: Guests available → Login works

### 5. Multiple Steps
- `--step execute:finish` means login in BOTH steps
- Order matters: `--step execute:finish` vs `--step finish:execute`

---

## Issue #1918 Context

The bug being fixed: When `login -t` is used without explicit `--step`, it currently defaults to the last enabled step (finish), causing unwanted login in BOTH execute AND finish steps.

**Fix**: When `-t` is used without `--step`, implicitly add `--step execute` to prevent duplicate login.

**Exception**: Explicit `--step finish` overrides this, allowing `login -t --when fail --step finish` for intentional finish-step login with conditional behavior.
