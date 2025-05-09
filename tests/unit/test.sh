#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        ENABLE_PARALLELIZATION="${ENABLE_PARALLELIZATION:-no}"
        ENABLE_CONTAINERS="${ENABLE_CONTAINERS:-no}"

        rlLogInfo "ENABLE_PARALLELIZATION=$ENABLE_PARALLELIZATION"
        rlLogInfo "ENABLE_CONTAINERS=$ENABLE_CONTAINERS"
        rlLogInfo "WITH_SYSTEM_PACKAGES=$WITH_SYSTEM_PACKAGES"

        if [ "$ENABLE_PARALLELIZATION" = "yes" ]; then
            PYTEST_PARALLELIZE="-n auto"
        else
            PYTEST_PARALLELIZE="-n 0"
        fi

        if [ "$ENABLE_CONTAINERS" = "yes" ]; then
            PYTEST_MARK="-m containers"
        else
            PYTEST_MARK="-m 'not containers'"
        fi

        rlLogInfo "PYTEST_PARALLELIZE=$PYTEST_PARALLELIZE"
        rlLogInfo "PYTEST_MARK=$PYTEST_MARK"

        rlRun "PYTEST_COMMAND='pytest -vvv -ra --showlocals'"

        rlLogInfo "pip is $(which pip), $(pip --version)"
        rlLogInfo "uv is $(which uv), $(uv --version 2>/dev/null || echo 'uv not found or version command failed')" # Added uv version check

        . ../images.sh || exit 1
        build_container_images --force
    rlPhaseEnd

    if [ "$WITH_SYSTEM_PACKAGES" = "yes" ]; then
        rlPhaseStartTest "Unit tests against system Python packages"
            rlRun "TEST_VENV=$(mktemp -d)"

            rlRun "python3 -m venv $TEST_VENV --system-site-packages"
            rlRun "$TEST_VENV/bin/python -m uv pip install 'pytest-container>=0.4.1' pytest-xdist"

            # Note: we're not in the root directory!
            rlRun "$TEST_VENV/bin/python3 -m $PYTEST_COMMAND $PYTEST_PARALLELIZE $PYTEST_MARK ."

            rlRun "rm -rf $TEST_VENV"
        rlPhaseEnd
    else
        rlPhaseStartTest "Unit tests"
            # Note: we're not in the root directory!
            rlRun "uv run $PYTEST_COMMAND $PYTEST_PARALLELIZE $PYTEST_MARK ."
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
