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
        '[03_some '
        '- 04!some - '
        '?05?some?'
        '!06!some! '
        '#07#some#'
        '@08@some@'
        '&09&some&'
        '*10&some*'
        '(11()some)'
        '+12+some+'
        ';13;some;'
        '=14=some='
    do
        rlPhaseStartTest "$i"
            rlRun "phase-name: ${i}"
        rlPhaseEnd
    done
rlJournalEnd
