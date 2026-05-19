# tmt AI Instructions

This file contains instructions for AI assistants (Claude Code, Gemini CLI, GitHub Copilot, etc.)
when working with the tmt codebase. Different sections cover different tasks.

## Communication Style

Provide matter-of-fact technical communication without praise or enthusiasm.

**Avoid**:

- Exclamations: "Perfect!", "Excellent!", "Great!", "That's wonderful!"
- Praise: "Good catch", "Nice work", "Well done"
- Enthusiasm markers: exclamation points, checkmarks (✓)
- Commentary on collaboration: "Our analysis shows...", "We've successfully..."

**Instead**:

- State facts directly: "The file is now 132 lines" (not "Successfully reduced to 132 lines!")
- Confirm completion: "Done" or "Updated" (not "Done! Looking good!")
- Report results: "Test passes" (not "Test passes ✓")
- Be matter-of-fact: "The mechanism is present" (not "Perfect! The mechanism is confirmed!")

## Investigation Principles

### Correlation vs Causation

- When debugging tmt/fmf behavior, distinguish between correlation and causation
- If a state change correlates with a behavioral difference, explicitly investigate whether it's
  causal or coincidental before presenting conclusions
- For each causal claim, provide: (1) supporting evidence, (2) a falsification test,
  (3) confidence level

### Evidence-Based Analysis

- Work bottom-up from concrete evidence (logs, test/plan/story metadata, reproducers) rather than
  top-down from assumptions
- When investigating why a tool/analyzer misses a bug, systematically enumerate all possible root
  causes before deep-diving into any single hypothesis
- Expect multiple independent root causes - don't stop at the first plausible explanation

## Project Overview

tmt (Test Management Tool) is a comprehensive Python-based testing framework that provides
a user-friendly way to work with tests. It implements the Metadata Specification using the Flexible
Metadata Format (fmf, which extends YAML syntax with special features) for storing test execution
data directly within git repositories.

## Development Commands

When tasked with executing builds or tests in the terminal, use the following commands. Follow
the purpose of each command listed below.

### Setup and Dependencies

```bash
# Install development dependencies
make develop

# Install build dependencies
make build-deps
```

### Testing

```bash
# Run pre-commit checks
pre-commit run --all-files

# Run the core test plan - runs on developer's workstation
tmt --feeling-safe -vv run -a provision -h local plan -n '^/plans/features/core$'
```

### Building and Packaging

```bash
# Build documentation
make docs

# Build man page
make man

# Build RPM packages
make rpm

# Build SRPM
make srpm
```

### Container Images

```bash
# Build tmt container images
make images

# Build test container images
make images/test

# Update base images for tmt containers
make images/test/bases

# Clean up container images
make clean/images
make clean/images/test
```

### Development Utilities

```bash
# Clean temporary files and build artifacts
make clean

# Show available make targets
make help
```

## Architecture

### Core Components

#### Base Classes (`tmt/base/*.py`)

- `Tree`: Represents the metadata tree structure
- `Test`: Individual test metadata and execution
- `Plan`: Test execution plans with step definitions
- `Story`: User story requirements
- `Run`: Test run execution context

#### Steps Framework (`tmt/steps/`)

tmt uses a 7-phase execution model:

1. **discover**: Find and select tests to run
2. **provision**: Prepare testing environment (guests/containers)
3. **prepare**: Install dependencies and configure environment
4. **execute**: Run the actual tests
5. **report**: Generate and publish test results
6. **finish**: Cleanup and finalization tasks
7. **cleanup**: Remove temporary resources

Each step is implemented as a plugin system supporting multiple `how` methods.

#### Plugin System

- Steps can have multiple implementations (e.g., `provision: local`, `container`, `virtual`, `beaker`)
- Plugins are dynamically loaded based on the `how` field in step configuration
- Common plugins: `ansible`, `shell`, `fmf`, `beakerlib` framework

#### Key Directories

- `tmt/checks/`: Additional checks running before/after tests (AVC, journalctl, coredumpct, ...)
- `tmt/frameworks/`: Test framework support (beakerlib, shell)
- `tmt/guest/`: Abstraction of guest hosting the tests
- `tmt/package_managers/`: Abstraction of package manager actions used by the rest of tmt code
- `tmt/steps/discover/`: Test discovery implementations (fmf, shell)
- `tmt/steps/provision/`: Environment provisioning (local, container, virtual, artemis, bootc)
- `tmt/steps/prepare/`: Environment preparation (ansible, shell, install packages)
- `tmt/steps/execute/`: Test execution (internal, upgrade)
- `tmt/steps/report/`: Result reporting (display, html, junit, polarion)
- `tmt/steps/finish/`: Cleanup tasks (ansible, shell)
- `tmt/utils/`: Utility modules (git, filesystem, command execution)

### Configuration and Metadata

#### fmf Integration

tmt heavily uses the Flexible Metadata Format (fmf) for:

- Test definitions and metadata
- Plan configurations
- Context and environment specifications
- Inheritance and data organization

#### Config System (`tmt/config/`)

- Centralized configuration management
- Hardware requirements specification
- Theme and styling options

### Testing Structure

#### Tests Organization

- `tests/unit/`: Unit tests using pytest
- `tests/integration/`: Integration tests with external services
- Tests use both pytest and shell-based test execution
- Container-based testing for isolation
- Beakerlib framework integration for complex test scenarios

### CLI and User Interface

#### Command Structure

- Main CLI in `tmt/cli/` with modular command organization
- Consistent option handling across commands
- Support for multiple output formats and verbosity levels
- Context-aware command execution

## Working with tmt Code

### Adding New Step Plugins

1. Create plugin module in appropriate `tmt/steps/<step>/` directory
2. Inherit from base plugin class of the step
3. Implement required methods (`go()`, `show()`, `wake()`)
4. Add plugin registration and CLI options

### Test Development

- Unit tests should mock external dependencies
- Integration tests can use the container framework
- Follow existing test patterns in `tests/` directory (e.g. refer to `/tests/prepare/install`).

### Code Standards

- **Target Python 3.9+:** Use syntax compatible with Python 3.9 and newer.
- **Use strict type hints:** Fully type all values, including function signatures, class attributes,
  and module-level constants. tmt code must pass validation by `mypy` and `pyright` linters.
- **Adhere to `ruff`:** Format and lint code strictly according to `pyproject.toml`.
- **Write comprehensive docstrings:** Document modules, classes, and functions.


## Release Notes Generation

If the task involves generating release notes, load and follow the instructions in
agents/release-notes.md.
