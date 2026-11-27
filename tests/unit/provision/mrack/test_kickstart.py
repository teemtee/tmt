from typing import Any

import pytest

from tmt.steps.provision.mrack import CreateJobParameters


def _job_parameters(kickstart: dict[str, str]) -> CreateJobParameters:
    return CreateJobParameters(
        tmt_name='/plan',
        name='Fedora-41',
        os='Fedora-41',
        arch='x86_64',
        hardware=None,
        kickstart=kickstart,
        whiteboard=None,
        beaker_job_owner=None,
        public_key=[],
        beaker_job_group=None,
        bootc_credentials=None,
        bootc_image_url=None,
        bootc=False,
        bootc_check_system_url=None,
    )


@pytest.mark.parametrize(
    ('kickstart', 'expected'),
    [
        (
            {'kernel-options': 'ksdevice=eth1', 'kernel-options-post': 'quiet'},
            {'kernel_options': 'ksdevice=eth1', 'kernel_options_post': 'quiet'},
        ),
        (
            {'kernel-options': 'selinux=0', 'script': 'lang en_US.UTF-8'},
            {
                'kernel_options': 'selinux=0',
                'kernel_options_post': None,
                'ks_append': {'script': 'lang en_US.UTF-8'},
            },
        ),
        (
            {'metadata': 'no_autopart', 'kernel-options-post': 'quiet'},
            {'ks_meta': 'no_autopart', 'kernel_options': None, 'kernel_options_post': 'quiet'},
        ),
    ],
    ids=['kernel-options-only', 'with-script', 'with-metadata'],
)
def test_kickstart_kernel_options(kickstart: dict[str, str], expected: dict[str, Any]) -> None:
    data = _job_parameters(kickstart).to_mrack()

    assert data['beaker'] == expected
