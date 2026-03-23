from unittest.mock import MagicMock, patch

from tmt.base.core import DependencySimple
from tmt.steps.prepare import Prepare
from tmt.steps.prepare.artifact import VERIFY_PHASE_NAME, PrepareArtifact
from tmt.steps.prepare.install import PrepareInstall
from tmt.steps.prepare.verify_installation import PrepareVerifyInstallation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _artifact_phase(
    auto_verify: bool = True, where: list[str] | None = None, order: int = 50
) -> MagicMock:
    phase = MagicMock(spec=PrepareArtifact)
    phase.data = MagicMock()
    phase.data.auto_verify = auto_verify
    phase.data.where = where if where is not None else []
    phase.data.order = order
    return phase


def _verify_phase() -> MagicMock:
    return MagicMock(spec=PrepareVerifyInstallation)


# ---------------------------------------------------------------------------
# _inject_artifact_verify_phase
# ---------------------------------------------------------------------------


def test_inject_no_artifact_phases() -> None:
    """No artifact phases → no verify phase injected."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = []
    Prepare._inject_artifact_verify_phase(prepare)
    assert len(prepare._phases) == 0


def test_inject_artifact_verify_true() -> None:
    """Artifact phase with auto_verify=True → verify phase injected with correct data."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = [_artifact_phase(auto_verify=True)]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        mock_delegate.return_value = _verify_phase()
        Prepare._inject_artifact_verify_phase(prepare)
    mock_delegate.assert_called_once()
    injected_data = mock_delegate.call_args.kwargs['data']
    assert injected_data.name == VERIFY_PHASE_NAME
    assert injected_data.verify == {}


def test_inject_artifact_verify_false() -> None:
    """Artifact phase with auto_verify=False → no verify phase injected."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = [_artifact_phase(auto_verify=False)]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        Prepare._inject_artifact_verify_phase(prepare)
    mock_delegate.assert_not_called()


def test_inject_explicit_verify_phase_present() -> None:
    """Explicit verify-installation already present → auto phase injected in addition."""
    prepare = MagicMock(spec=Prepare)
    # The explicit phase has a user-chosen name, not the auto-injected name.
    explicit = _verify_phase()
    explicit.name = 'my-custom-verify'
    prepare._phases = [_artifact_phase(auto_verify=True), explicit]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        mock_delegate.return_value = _verify_phase()
        Prepare._inject_artifact_verify_phase(prepare)
    # Auto phase must be injected alongside the user's explicit phase.
    mock_delegate.assert_called_once()


def test_inject_our_own_phase_already_present() -> None:
    """Auto-injected phase already present (re-entrant guard) → no double injection."""
    prepare = MagicMock(spec=Prepare)
    already_injected = _verify_phase()
    already_injected.name = VERIFY_PHASE_NAME
    prepare._phases = [_artifact_phase(auto_verify=True), already_injected]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        Prepare._inject_artifact_verify_phase(prepare)
    mock_delegate.assert_not_called()


def test_inject_where_union() -> None:
    """Verify phase mirrors the union of where= from all artifact phases with auto_verify=True."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = [
        _artifact_phase(auto_verify=True, where=['host-a']),
        _artifact_phase(auto_verify=True, where=['host-b']),
    ]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        mock_delegate.return_value = _verify_phase()
        Prepare._inject_artifact_verify_phase(prepare)
    injected_data = mock_delegate.call_args.kwargs['data']
    assert set(injected_data.where) == {'host-a', 'host-b'}


def test_inject_where_empty_means_all_guests() -> None:
    """If any artifact phase has empty where (all guests), verify phase runs on all guests."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = [
        _artifact_phase(auto_verify=True, where=[]),
        _artifact_phase(auto_verify=True, where=['host-a']),
    ]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        mock_delegate.return_value = _verify_phase()
        Prepare._inject_artifact_verify_phase(prepare)
    injected_data = mock_delegate.call_args.kwargs['data']
    assert injected_data.where == []


def test_inject_mixed_verify_flags() -> None:
    """With mixed auto_verify flags, inject only when at least one phase has auto_verify=True."""
    prepare = MagicMock(spec=Prepare)
    prepare._phases = [
        _artifact_phase(auto_verify=True),
        _artifact_phase(auto_verify=False),
    ]
    with patch('tmt.steps.prepare.PreparePlugin.delegate') as mock_delegate:
        mock_delegate.return_value = _verify_phase()
        Prepare._inject_artifact_verify_phase(prepare)
    mock_delegate.assert_called_once()


# ---------------------------------------------------------------------------
# PrepareInstall._prepare_installables
# ---------------------------------------------------------------------------


def test_debuginfo(root_logger):
    """
    Check debuginfo package parsing
    """

    plugin = MagicMock(spec=PrepareInstall)

    PrepareInstall._prepare_installables(
        plugin,
        dependencies=[
            # Regular packages
            DependencySimple("wget"),
            DependencySimple("debuginfo-something"),
            DependencySimple("elfutils-debuginfod"),
            # Debuginfo packages
            DependencySimple("grep-debuginfo"),
            DependencySimple("elfutils-debuginfod-debuginfo"),
        ],
        directories=[],
        logger=root_logger,
    )

    assert plugin.packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
    ]
    assert plugin.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
    ]
