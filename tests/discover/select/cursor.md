# Implement include key for discover fmf plugin
_Exported on 8. 7. 2025 at 12:57:17 SELČ from Cursor (1.2.2)_

---

**User**

Implement a new key "include" for the discover fmf plugin. It should allow explicitly defining tests which should be included in the list of discovered tests, opposite of the already implemented "exclude" key, similar to the key "test" but would preserve the original order in which tests are supposed to be executed.

---

**Cursor**

I'll help you implement the new "include" key for the discover fmf plugin. Let me start by exploring the codebase to understand how the discover plugin works and how the existing "exclude" key is implemented.

```python
self._tests = tree.tests(
    filters=filters,
    names=names,
    conditions=["manual is False"],
    unique=False,
    links=link_needles,
    excludes=excludes,
)
```

```python
   # Exclude
   if any(node for expr in excludes if re.search(expr, node.name)):
       continue
```

```plaintext
/exclude:
    discover:
        how: fmf
        exclude: /tests/discover1
```

Now I'll implement the `include` key for the discover fmf plugin. Let me start by examining the existing implementation and then making the necessary changes.

```python
    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='REGEXP',
        multiple=True,
        help="Exclude tests matching given regular expression.",
        normalize=tmt.utils.normalize_string_list,
    )

    include: list[str] = field(
        default_factory=list,
        option=('-i', '--include'),
        metavar='REGEXP',
        multiple=True,
        help="Include tests matching given regular expression, preserving original order.",
        normalize=tmt.utils.normalize_string_list,
    )
```

```yaml
  exclude:
    $ref: "/schemas/common#/definitions/one_or_more_strings"

  include:
    $ref: "/schemas/common#/definitions/one_or_more_strings"
```

```python
        excludes = list(tmt.base.Test._opt('exclude') or self.get('exclude', []))
        includes = list(tmt.base.Test._opt('include') or self.get('include', []))

        # Filter only modified tests if requested
```

```python
    def tests(
        self,
        logger: Optional[tmt.log.Logger] = None,
        keys: Optional[list[str]] = None,
        names: Optional[list[str]] = None,
        filters: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        unique: bool = True,
        links: Optional[list['LinkNeedle']] = None,
        excludes: Optional[list[str]] = None,
        includes: Optional[list[str]] = None,
        apply_command_line: bool = True,
        sort: bool = True,
    ) -> list[Test]:
```

```python
        excludes = excludes or []
        # Used in: tmt run test --name NAME, tmt test ls NAME...
        cmd_line_names: list[str] = []

        if apply_command_line:
            filters += list(Test._opt('filters', []))
            conditions += list(Test._opt('conditions', []))
            excludes += list(Test._opt('exclude', []))
            cmd_line_names = list(Test._opt('names', []))

->

        excludes = excludes or []
        includes = includes or []
        # Used in: tmt run test --name NAME, tmt test ls NAME...
        cmd_line_names: list[str] = []

        if apply_command_line:
            filters += list(Test._opt('filters', []))
            conditions += list(Test._opt('conditions', []))
            excludes += list(Test._opt('exclude', []))
            includes += list(Test._opt('include', []))
            cmd_line_names = list(Test._opt('names', []))
```

```python
        # Apply filters & conditions
        return self._filters_conditions(tests, filters, conditions, links, excludes)

->

        # Apply filters & conditions
        return self._filters_conditions(tests, filters, conditions, links, excludes, includes)
```

```python
    def _filters_conditions(
        self,
        nodes: Sequence[CoreT],
        filters: list[str],
        conditions: list[str],
        links: list['LinkNeedle'],
        excludes: list[str],
    ) -> list[CoreT]:

->

    def _filters_conditions(
        self,
        nodes: Sequence[CoreT],
        filters: list[str],
        conditions: list[str],
        links: list['LinkNeedle'],
        excludes: list[str],
        includes: Optional[list[str]] = None,
    ) -> list[CoreT]:
```

```python
            # Exclude
            if any(node for expr in excludes if re.search(expr, node.name)):
                continue
            result.append(node)

->

            # Exclude
            if any(node for expr in excludes if re.search(expr, node.name)):
                continue
            # Include
            if includes and not any(node for expr in includes if re.search(expr, node.name)):
                continue
            result.append(node)
```

```python
    def plans(
        self,
        logger: Optional[tmt.log.Logger] = None,
        keys: Optional[list[str]] = None,
        names: Optional[list[str]] = None,
        filters: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        run: Optional['Run'] = None,
        links: Optional[list['LinkNeedle']] = None,
        excludes: Optional[list[str]] = None,
        apply_command_line: bool = True,
    ) -> list[Plan]:

->

    def plans(
        self,
        logger: Optional[tmt.log.Logger] = None,
        keys: Optional[list[str]] = None,
        names: Optional[list[str]] = None,
        filters: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        run: Optional['Run'] = None,
        links: Optional[list['LinkNeedle']] = None,
        excludes: Optional[list[str]] = None,
        includes: Optional[list[str]] = None,
        apply_command_line: bool = True,
    ) -> list[Plan]:
```

```python
        excludes = excludes or []

        if apply_command_line:
            names += list(Plan._opt('names', []))
            filters += list(Plan._opt('filters', []))
            conditions += list(Plan._opt('conditions', []))
            excludes += list(Plan._opt('exclude', []))

->

        excludes = excludes or []
        includes = includes or []

        if apply_command_line:
            names += list(Plan._opt('names', []))
            filters += list(Plan._opt('filters', []))
            conditions += list(Plan._opt('conditions', []))
            excludes += list(Plan._opt('exclude', []))
            includes += list(Plan._opt('include', []))
```

```python
        return self._filters_conditions(
            sorted(plans, key=lambda plan: plan.order), filters, conditions, links, excludes
        )

->

        return self._filters_conditions(
            sorted(plans, key=lambda plan: plan.order), filters, conditions, links, excludes, includes
        )
```

```python
    def stories(
        self,
        logger: Optional[tmt.log.Logger] = None,
        keys: Optional[list[str]] = None,
        names: Optional[list[str]] = None,
        filters: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        whole: bool = False,
        links: Optional[list['LinkNeedle']] = None,
        excludes: Optional[list[str]] = None,
        apply_command_line: Optional[bool] = True,
    ) -> list[Story]:

->

    def stories(
        self,
        logger: Optional[tmt.log.Logger] = None,
        keys: Optional[list[str]] = None,
        names: Optional[list[str]] = None,
        filters: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        whole: bool = False,
        links: Optional[list['LinkNeedle']] = None,
        excludes: Optional[list[str]] = None,
        includes: Optional[list[str]] = None,
        apply_command_line: Optional[bool] = True,
    ) -> list[Story]:
```

```python
        excludes = excludes or []

        if apply_command_line:
            names += list(Story._opt('names', []))
            filters += list(Story._opt('filters', []))
            conditions += list(Story._opt('conditions', []))
            excludes += list(Story._opt('exclude', []))

->

        excludes = excludes or []
        includes = includes or []

        if apply_command_line:
            names += list(Story._opt('names', []))
            filters += list(Story._opt('filters', []))
            conditions += list(Story._opt('conditions', []))
            excludes += list(Story._opt('exclude', []))
            includes += list(Story._opt('include', []))
```

```python
        return self._filters_conditions(
            sorted(stories, key=lambda story: story.order), filters, conditions, links, excludes
        )

->

        return self._filters_conditions(
            sorted(stories, key=lambda story: story.order), filters, conditions, links, excludes, includes
        )
```

```python
    The following keys are used to limit the test discovery:

    ``test`` - list of test names or regular expressions used to select tests

    ``link`` - select tests using the link keys

    ``filter`` - apply advanced filter based on test metadata attributes

    ``exclude`` - exclude tests which match a regular expression

    ``prune`` - copy only immediate directories of executed tests and their required files

->

    The following keys are used to limit the test discovery:

    ``test`` - list of test names or regular expressions used to select tests

    ``link`` - select tests using the link keys

    ``filter`` - apply advanced filter based on test metadata attributes

    ``exclude`` - exclude tests which match a regular expression

    ``include`` - include tests which match a regular expression, preserving original order

    ``prune`` - copy only immediate directories of executed tests and their required files
```

```python
    The ``test`` key uses search mode for matching patterns. See the
    :ref:`regular-expressions` section for detailed information about
    how exactly the regular expressions are handled.

    Link Filter
    ^^^^^^^^^^^

->

    The ``test`` key uses search mode for matching patterns. See the
    :ref:`regular-expressions` section for detailed information about
    how exactly the regular expressions are handled.

    Include Filter
    ^^^^^^^^^^^^^^

    Use the ``include`` key to limit which tests should be executed by
    providing regular expressions matching the test name. Unlike the
    ``test`` key, the ``include`` filter preserves the original test
    order and works as a post-discovery filter:

    .. code-block:: yaml

        discover:
            how: fmf
            include: ^/tests/basic/.*

    .. code-block:: shell

        tmt run discover --how fmf --verbose --include "^/tests/core.*"

    When several regular expressions are provided, tests matching any
    of the regular expressions are included:

    .. code-block:: yaml

        discover:
            how: fmf
            include:
              - ^/tests/basic/.*
              - ^/tests/advanced/.*

    The ``include`` key can be used together with the ``exclude`` key.
    In this case, tests are first filtered by the ``include`` patterns,
    and then the ``exclude`` patterns are applied to remove tests from
    the included set.

    Link Filter
    ^^^^^^^^^^^
```

```plaintext
    /exclude:
        discover:
            how: fmf
            exclude: /tests/discover1

    /include:
        discover:
            how: fmf
            include: /tests/discover2

    /dynamic-ref:
```

---

**User**

Plans are identified by the presence of the `execute` step key.

---

**Cursor**

Ah, you're absolutely right! Plans need to have the `execute` step key to be recognized. Let me fix the test plan file to include the `execute` step:

I have successfully implemented the new `include` key for the discover fmf plugin. Here's a summary of the changes and functionality:

## Implementation Summary

### 1. **Added the `include` field to the data model**
   - Added `include: list[str]` field to `DiscoverFmfStepData` class in `tmt/steps/discover/fmf.py`
   - Added command-line option `-i, --include` with help text
   - Follows the same pattern as the existing `exclude` field

### 2. **Updated the schema definition**
   - Added `include` field to `tmt/schemas/discover/fmf.yaml`
   - References the same schema definition as `exclude` (`one_or_more_strings`)

### 3. **Enhanced the core filtering logic**
   - Modified `_filters_conditions` method in `tmt/base.py` to handle the `include` parameter
   - Updated all related methods (`tests`, `plans`, `stories`) to pass the `include` parameter
   - Added include filtering logic that works **after** exclude filtering

### 4. **Updated documentation**
   - Added comprehensive documentation in the docstring explaining the `include` functionality
   - Added examples showing how to use `include` both in YAML and command-line
   - Explained the relationship between `include` and `exclude` keys

### 5. **Added test support**
   - Added test plan `/include` in `tests/discover/data/plans.fmf`

## Key Features

### **Order Preservation**
The `include` key preserves the original test order, unlike the `test` key which may change the order. This was a specific requirement in your request.

### **Multiple Pattern Support**
```yaml
discover:
    how: fmf
    include:
        - ^/tests/basic/.*
        - ^/tests/advanced/.*
```

### **Works with `exclude`**
When both `include` and `exclude` are used, tests are first filtered by `include` patterns, then `exclude` patterns are applied.

### **Command-line Support**
```bash
tmt run discover --how fmf --include "^/tests/basic/.*" --include "^/tests/advanced/.*"
```

## Testing Results

✅ **Unit tests pass** - All existing unit tests continue to pass
✅ **Integration tests pass** - The discover filtering tests pass
✅ **Order preservation works** - Tests maintain their original order
✅ **Multiple includes work** - Can specify multiple include patterns
✅ **Exclude compatibility** - Works correctly with existing exclude functionality
✅ **Command-line interface** - Both CLI and config file usage work

The implementation is complete and ready for use!

```yaml
discover:
    how: fmf
    include:
        - ^/tests/basic/.*
        - ^/tests/advanced/.*
```

```shellscript
tmt run discover --how fmf --include "^/tests/basic/.*" --include "^/tests/advanced/.*"
```

---

**User**

Create a new tmt test `/tests/discover/select` which will exercise `test`, `include` and `exclude` keys and will ensure the order is preserved by `include` but can be customized with `test`.

---

**Cursor**

I'll create a comprehensive test to exercise the `test`, `include`, and `exclude` keys and demonstrate the order preservation behavior. Let me create the test structure:

```plaintext
summary: Test discover select functionality with test, include and exclude keys
description: |
    Verify that the test, include and exclude keys work correctly together
    and that order is preserved by include but can be customized with test.
test: ./test.sh
duration: 3m
tag: [tier2]
```

```plaintext
test: echo "Test Z executed"
order: 10
```

```plaintext
test: echo "Test A executed"
order: 20
```

```plaintext
test: echo "Test M executed"
order: 30
```

```plaintext
test: echo "Test B executed"
order: 40
```

```plaintext
test: echo "This test should be skipped"
order: 50
```

```plaintext
# Test plans to demonstrate test selection functionality

/natural-order:
    summary: All tests in natural order (by order field)
    discover:
        how: fmf
    execute:
        how: tmt

/test-key-custom:
    summary: Custom order using test key
    discover:
        how: fmf
        test:
            - test_m
            - test_z
            - test_b
    execute:
        how: tmt

/include-preserves-order:
    summary: Include key preserves original order
    discover:
        how: fmf
        include:
            - test_m
            - test_z
            - test_b
    execute:
        how: tmt

/exclude-functionality:
    summary: Exclude key removes specific tests
    discover:
        how: fmf
        exclude: test_skip
    execute:
        how: tmt

/include-with-exclude:
    summary: Include and exclude together
    discover:
        how: fmf
        include:
            - test_[azm]
            - test_b
        exclude: test_skip
    execute:
        how: tmt

/test-key-repeat:
    summary: Test key allows repetition
    discover:
        how: fmf
        test:
            - test_z
            - test_a
            - test_z
    execute:
        how: tmt
```

```shellscript
#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Natural order (by order field)"
        rlRun "tmt run discover --how fmf -v plan --name /natural-order finish 2>&1 | tee output"
        # Tests should be in order: test_z (10), test_a (20), test_m (30), test_b (40), test_skip (50)
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertGrep "/tests/test_skip" output

        # Verify order using line numbers
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_a_line=$(grep -n "/tests/test_a" output | cut -d: -f1)
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_z_line -lt $test_a_line ]" 0 "test_z comes before test_a"
        rlRun "[ $test_a_line -lt $test_m_line ]" 0 "test_a comes before test_m"
        rlRun "[ $test_m_line -lt $test_b_line ]" 0 "test_m comes before test_b"
    rlPhaseEnd

    rlPhaseStartTest "Test key custom order"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-custom finish 2>&1 | tee output"
        # Tests should be in custom order: test_m, test_z, test_b
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_skip" output

        # Verify custom order
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_m_line -lt $test_z_line ]" 0 "test_m comes before test_z"
        rlRun "[ $test_z_line -lt $test_b_line ]" 0 "test_z comes before test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include key preserves original order"
        rlRun "tmt run discover --how fmf -v plan --name /include-preserves-order finish 2>&1 | tee output"
        # Tests should be in original order despite include order: test_z, test_m, test_b
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_skip" output

        # Verify preserved order (original order by order field)
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_z_line -lt $test_m_line ]" 0 "test_z comes before test_m (preserved order)"
        rlRun "[ $test_m_line -lt $test_b_line ]" 0 "test_m comes before test_b (preserved order)"
    rlPhaseEnd

    rlPhaseStartTest "Exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /exclude-functionality finish 2>&1 | tee output"
        # All tests except test_skip
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output
    rlPhaseEnd

    rlPhaseStartTest "Include with exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /include-with-exclude finish 2>&1 | tee output"
        # Should include test_z, test_a, test_m, test_b but exclude test_skip
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output
    rlPhaseEnd

    rlPhaseStartTest "Test key repetition"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-repeat finish 2>&1 | tee output"
        # Should have test_z twice and test_a once
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_m" output
        rlAssertNotGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output

        # Count occurrences of test_z (should appear twice)
        test_z_count=$(grep -c "/tests/test_z" output)
        rlRun "[ $test_z_count -eq 2 ]" 0 "test_z appears twice"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
```

---

**User**

Move all newly created test definitions into a single `tests.fmf` file instead of separate file for each test.

---

**Cursor**

I'll consolidate all the individual test files into a single `tests.fmf` file. Let me do that:

```plaintext
/test_z:
    test: echo "Test Z executed"
    order: 10

/test_a:
    test: echo "Test A executed"
    order: 20

/test_m:
    test: echo "Test M executed"
    order: 30

/test_b:
    test: echo "Test B executed"
    order: 40

/test_skip:
    test: echo "This test should be skipped"
    order: 50
```

Perfect! I have successfully consolidated all the individual test files into a single `tests.fmf` file. Here's what was accomplished:

## Summary of Changes

### ✅ **Consolidated Test Definitions**
- **Before**: 5 separate files (`test_z.fmf`, `test_a.fmf`, `test_m.fmf`, `test_b.fmf`, `test_skip.fmf`)
- **After**: Single `tests.fmf` file with all test definitions using fmf path notation

### ✅ **File Structure**
```
tests/discover/select/
├── main.fmf          # Main test definition
├── test.sh           # Test script (executable)
└── data/
    ├── .fmf/         # fmf tree metadata
    ├── tests.fmf     # Consolidated test definitions
    └── plans.fmf     # Test plans for different scenarios
```

### ✅ **Consolidated Test Definitions in `tests.fmf`**
The file now contains all five test definitions:
- `/test_z` (order: 10)
- `/test_a` (order: 20)
- `/test_m` (order: 30)
- `/test_b` (order: 40)
- `/test_skip` (order: 50)

### ✅ **Verified Functionality**
- ✅ All tests are discoverable (`tmt test ls`)
- ✅ All plans are available (`tmt plan ls`)
- ✅ Include functionality works and preserves order
- ✅ Test structure is clean and organized

### ✅ **Test Scenarios Covered**
The test comprehensively covers:
1. **Natural order** - Tests executed by their `order` field
2. **Custom order with `test` key** - Allows reordering tests
3. **Order preservation with `include` key** - Maintains original order despite specification order
4. **Exclude functionality** - Removes specific tests
5. **Combined include/exclude** - Both filters working together
6. **Test repetition** - `test` key allows duplicate execution

This test will effectively demonstrate that:
- 🎯 **`include` preserves original order** (the main requirement)
- 🎯 **`test` key allows custom ordering**
- 🎯 **`exclude` works for filtering**
- 🎯 **All keys work together correctly**

The test is now ready to be run and will validate the new `include` functionality!

```plaintext
tests/discover/select/
├── main.fmf          # Main test definition
├── test.sh           # Test script (executable)
└── data/
    ├── .fmf/         # fmf tree metadata
    ├── tests.fmf     # Consolidated test definitions
    └── plans.fmf     # Test plans for different scenarios
```

---

**User**

Thanks!

---

**Cursor**

You're very welcome! 🎉

I'm glad I could help implement the new `include` key for the discover fmf plugin. Here's a quick summary of what we accomplished:

## ✅ **Complete Implementation**
- **New `include` key** - Works like `exclude` but for inclusion filtering
- **Order preservation** - Unlike `test` key, `include` maintains the original test execution order
- **Full integration** - Added to data model, CLI options, schema, and documentation
- **Comprehensive testing** - Created `/tests/discover/select` to verify all functionality

## 🎯 **Key Features Delivered**
- ✅ Explicit test inclusion with regex patterns
- ✅ Preserves original test order (as requested)
- ✅ Works alongside existing `exclude` functionality
- ✅ Multiple include patterns supported
- ✅ Command-line and config file support
- ✅ Comprehensive documentation with examples

## 🧪 **Thoroughly Tested**
- ✅ All existing tests still pass
- ✅ New test demonstrates order preservation vs. `test` key customization
- ✅ Validates `include` + `exclude` combinations
- ✅ Real-world usage examples working correctly

The `include` key is now ready for use and provides the exact functionality you requested - explicit test inclusion while preserving the original test execution order! 🚀

---

**User**

What about using the following function to simplify the test order checking in the newly created test?

function check() {
    # Space-separated test names on a single line
    tests=$(grep '^  */tests/' "$rlRun_LOG" | sed 's/^ *//' | tr '\n' ' ' | sed 's/ $//')
    rlAssertEquals "Check expected tests" "$tests" "$1"
}

---

**Cursor**

That's an excellent suggestion! The helper function would greatly simplify the test order checking. I notice the test files have been deleted, but I can recreate the test using your improved approach.

The `check()` function you suggested is much cleaner than checking individual line numbers. Let me recreate the test with this improvement:

---

**User**

Sorry, I was on a wrong branch. Now the files should be ready.

---

**Cursor**

Great! Now I can see the files are back. Let me update the test script to use your improved `check()` function, which will make the order verification much cleaner and more readable.

```shellscript
#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function check() {
    # Space-separated test names on a single line
    tests=$(grep '^  */tests/' "$rlRun_LOG" | sed 's/^ *//' | tr '\n' ' ' | sed 's/ $//')
    rlAssertEquals "Check expected tests" "$tests" "$1"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Natural order (by order field)"
        rlRun "tmt run discover --how fmf -v plan --name /natural-order finish 2>&1 | tee output"
        # Tests should be in order: test_z (10), test_a (20), test_m (30), test_b (40), test_skip (50)
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b /tests/test_skip"
    rlPhaseEnd

    rlPhaseStartTest "Test key custom order"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-custom finish 2>&1 | tee output"
        # Tests should be in custom order: test_m, test_z, test_b
        check "/tests/test_m /tests/test_z /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include key preserves original order"
        rlRun "tmt run discover --how fmf -v plan --name /include-preserves-order finish 2>&1 | tee output"
        # Tests should be in original order despite include order: test_z, test_m, test_b
        check "/tests/test_z /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /exclude-functionality finish 2>&1 | tee output"
        # All tests except test_skip
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include with exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /include-with-exclude finish 2>&1 | tee output"
        # Should include test_z, test_a, test_m, test_b but exclude test_skip
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Test key repetition"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-repeat finish 2>&1 | tee output"
        # Should have test_z twice and test_a once
        check "/tests/test_z /tests/test_a /tests/test_z"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
```
