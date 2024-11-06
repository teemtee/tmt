#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    for i in \
        # Ensure the regression from #teemtee/tmt/3333 is covered
        /sbin/ldconfig \
        /usr/sbin/ldconfig \

        # Cover other special characters in the phase name
        '//01_some/-phase//na--me-' \
        '\$02_so\$me<->phase?!*na--me/-'
    do
        rlPhaseStartTest "$i"
            rlRun "phase-name: ${i}"
        rlPhaseEnd
    done
rlJournalEnd
