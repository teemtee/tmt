#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        ENABLE_PARALLELIZATION="${ENABLE_PARALLELIZATION:-no}"
        ENABLE_CONTAINERS="${ENABLE_CONTAINERS:-no}"
        # TODO: `test` seems more natural, but creates 3 environments,
        # one per available Python installation. I need to check whether
        # to disable or take advantage of it.
        HATCH_ENVIRONMENT="${HATCH_ENVIRONMENT:-dev}"

        rlLogInfo "ENABLE_PARALLELIZATION=$ENABLE_PARALLELIZATION"
        rlLogInfo "ENABLE_CONTAINERS=$ENABLE_CONTAINERS"
        rlLogInfo "WITH_SYSTEM_PACKAGES=$WITH_SYSTEM_PACKAGES"
        rlLogInfo "HATCH_ENVIRONMENT=$HATCH_ENVIRONMENT"

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
        rlLogInfo "hatch is $(which hatch), $(hatch --version)"

        rlRun "make -C $TMT_TREE images-unit-tests"
    rlPhaseEnd

    if [ "$WITH_SYSTEM_PACKAGES" = "yes" ]; then
        rlPhaseStartTest "Unit tests against system Python packages"
            rlRun "TEST_VENV=$(mktemp -d)"

            rlRun "python3 -m venv $TEST_VENV --system-site-packages"
            # pytest-container==0.4.0 is not compatible with c9s pytest 6.2.2
            if rlIsCentOS "=9"; then
                 rlRun "$TEST_VENV/bin/pip install -U pytest"
            fi
            rlRun "$TEST_VENV/bin/pip install pytest-container pytest-xdist"

            # Note: we're not in the root directory!
            rlRun "$TEST_VENV/bin/python3 -m $PYTEST_COMMAND $PYTEST_PARALLELIZE $PYTEST_MARK ."

            rlRun "rm -rf $TEST_VENV"
        rlPhaseEnd
    else
        rlPhaseStartTest "Unit tests"
            rlRun "hatch -v run $HATCH_ENVIRONMENT:$PYTEST_COMMAND $PYTEST_PARALLELIZE $PYTEST_MARK tests/unit"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
