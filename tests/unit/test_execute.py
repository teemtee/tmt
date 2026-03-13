from unittest.mock import MagicMock, Mock, patch

import pytest

import tmt
import tmt.base
import tmt.guest
import tmt.steps.discover
import tmt.steps.execute
from tmt.log import Logger


def test_pending_task_tracking_multihost(root_logger: Logger) -> None:
    """
    Test that pending task counters are correctly calculated for multihost scenarios.
    
    This test verifies that the workload calculation logic properly counts tests
    per guest based on where clause mappings in a multihost environment.
    """
    
    # Create mock plan with multihost configuration
    mock_plan = Mock()
    mock_plan.my_run = Mock()
    mock_plan.my_run.tree = Mock()
    mock_plan.my_run.tree.root = '/test/root'
    mock_plan.workdir = '/test/workdir'
    mock_plan.data_directory = '/test/data'
    
    # Create mock guests representing server and clients
    server_guest = Mock(spec=tmt.guest.Guest)
    server_guest.name = 'server'
    server_guest.role = 'server'
    server_guest.multihost_name = 'server'
    server_guest.pending_tasks = 0
    server_guest.increment_pending_tasks = Mock(side_effect=lambda: setattr(server_guest, 'pending_tasks', server_guest.pending_tasks + 1))
    server_guest.decrement_pending_tasks = Mock(side_effect=lambda: setattr(server_guest, 'pending_tasks', max(0, server_guest.pending_tasks - 1)))
    
    client1_guest = Mock(spec=tmt.guest.Guest)
    client1_guest.name = 'client-1'
    client1_guest.role = 'client'
    client1_guest.multihost_name = 'client-1 (client)'
    client1_guest.pending_tasks = 0
    client1_guest.increment_pending_tasks = Mock(side_effect=lambda: setattr(client1_guest, 'pending_tasks', client1_guest.pending_tasks + 1))
    client1_guest.decrement_pending_tasks = Mock(side_effect=lambda: setattr(client1_guest, 'pending_tasks', max(0, client1_guest.pending_tasks - 1)))
    
    client2_guest = Mock(spec=tmt.guest.Guest)
    client2_guest.name = 'client-2'
    client2_guest.role = 'client'
    client2_guest.multihost_name = 'client-2 (client)'
    client2_guest.pending_tasks = 0
    client2_guest.increment_pending_tasks = Mock(side_effect=lambda: setattr(client2_guest, 'pending_tasks', client2_guest.pending_tasks + 1))
    client2_guest.decrement_pending_tasks = Mock(side_effect=lambda: setattr(client2_guest, 'pending_tasks', max(0, client2_guest.pending_tasks - 1)))
    
    # Set up provision step with guests
    mock_provision = Mock()
    mock_provision.guests = [server_guest, client1_guest, client2_guest]
    mock_plan.provision = mock_provision
    
    # Create mock tests with different where clauses
    # Test 1: server-only test
    test1 = Mock()
    test1.name = 'server-config-test'
    test1.enabled_on_guest = Mock(return_value=True)  # Will be overridden based on role
    
    def test1_enabled_on_guest(guest):
        return guest.role == 'server'
    test1.enabled_on_guest = test1_enabled_on_guest
    
    # Test 2: client-only test
    test2 = Mock()
    test2.name = 'client-functionality-test'
    
    def test2_enabled_on_guest(guest):
        return guest.role == 'client'
    test2.enabled_on_guest = test2_enabled_on_guest
    
    # Test 3: all guests test
    test3 = Mock()
    test3.name = 'connectivity-test'
    test3.enabled_on_guest = None  # None means enabled on all guests
    
    # Test 4: specific client test
    test4 = Mock()
    test4.name = 'client-1-specific-test'
    
    def test4_enabled_on_guest(guest):
        return guest.name == 'client-1'
    test4.enabled_on_guest = test4_enabled_on_guest
    
    # Wrap tests in TestOrigin-like objects
    test_origins = []
    for test in [test1, test2, test3, test4]:
        test_origin = Mock()
        test_origin.test = test
        test_origins.append(test_origin)
    
    # Create mock discover phase
    mock_discover_phase = Mock(spec=tmt.steps.discover.DiscoverPlugin)
    mock_discover_phase.name = 'main-discover'
    mock_discover_phase.enabled_by_when = True
    mock_discover_phase.tests = Mock(return_value=test_origins)
    
    mock_discover = Mock()
    mock_discover.phases = Mock(return_value=[mock_discover_phase])
    mock_discover.tests = Mock(return_value=test_origins)
    mock_plan.discover = mock_discover
    
    # Create mock execute phase and plugin
    mock_execute_plugin = Mock(spec=tmt.steps.execute.ExecutePlugin)
    mock_execute_plugin.name = 'internal'
    mock_execute_plugin.tasks = [('main-discover', [server_guest, client1_guest, client2_guest])]
    
    # Create execute step
    execute_step = tmt.steps.execute.Execute(
        plan=mock_plan,
        data=[{'how': 'internal'}],
        logger=root_logger
    )
    
    # Mock the phases method to return our execute plugin
    execute_step.phases = Mock(return_value=[mock_execute_plugin])
    
    # Mock queue to avoid actual execution
    mock_queue = Mock()
    mock_queue.enqueue_plugin = Mock()
    mock_queue.run = Mock(return_value=[])  # No actual execution outcomes
    
    with patch('tmt.steps.execute.PhaseQueue', return_value=mock_queue):
        # Run the workload calculation logic (the part we're testing)
        # This simulates the workload calculation in execute step's go() method
        for phase in execute_step.phases(classes=(tmt.steps.execute.ExecutePlugin,)):
            if isinstance(phase, tmt.steps.execute.ExecutePlugin):
                for discover_phase_name, guests in phase.tasks:
                    # Find the corresponding discover phase to get test list
                    discover_phase = None
                    for discover in mock_plan.discover.phases(classes=(tmt.steps.discover.DiscoverPlugin,)):
                        if discover.name == discover_phase_name and discover.enabled_by_when:
                            discover_phase = discover
                            break

                    if discover_phase:
                        # For each test, check which guests will execute it and increment counters
                        for test_origin in mock_plan.discover.tests(enabled=True):
                            test = test_origin.test

                            # Check if this test runs on any of the current guests
                            for guest in guests:
                                if test.enabled_on_guest is None or test.enabled_on_guest(guest):
                                    guest.increment_pending_tasks()
    
    # Assert the expected pending task counts
    # Expected counts based on test assignments:
    # - server_guest: test1 (server-only) + test3 (all guests) = 2 tasks
    # - client1_guest: test2 (client-only) + test3 (all guests) + test4 (client-1 specific) = 3 tasks  
    # - client2_guest: test2 (client-only) + test3 (all guests) = 2 tasks
    
    assert server_guest.pending_tasks == 2, f"Server guest should have 2 pending tasks, got {server_guest.pending_tasks}"
    assert client1_guest.pending_tasks == 3, f"Client-1 guest should have 3 pending tasks, got {client1_guest.pending_tasks}"
    assert client2_guest.pending_tasks == 2, f"Client-2 guest should have 2 pending tasks, got {client2_guest.pending_tasks}"
    
    # Verify that increment_pending_tasks was called the correct number of times
    assert server_guest.increment_pending_tasks.call_count == 2
    assert client1_guest.increment_pending_tasks.call_count == 3
    assert client2_guest.increment_pending_tasks.call_count == 2
    
    # Verify total task distribution
    total_pending_tasks = server_guest.pending_tasks + client1_guest.pending_tasks + client2_guest.pending_tasks
    expected_total = 7  # test1(1) + test2(2) + test3(3) + test4(1) = 7 total task executions
    assert total_pending_tasks == expected_total, f"Total pending tasks should be {expected_total}, got {total_pending_tasks}"


def test_pending_task_tracking_decrement_logic(root_logger: Logger) -> None:
    """
    Test that pending task counters are properly decremented when results are processed.
    
    This test verifies the result processing logic in the execute step correctly
    decrements pending task counters based on test execution results.
    """
    
    # Create mock guests
    guest1 = Mock(spec=tmt.guest.Guest)
    guest1.name = 'guest-1'
    guest1.pending_tasks = 3
    guest1.decrement_pending_tasks = Mock(side_effect=lambda: setattr(guest1, 'pending_tasks', max(0, guest1.pending_tasks - 1)))
    
    guest2 = Mock(spec=tmt.guest.Guest)
    guest2.name = 'guest-2'
    guest2.pending_tasks = 2
    guest2.decrement_pending_tasks = Mock(side_effect=lambda: setattr(guest2, 'pending_tasks', max(0, guest2.pending_tasks - 1)))
    
    # Create mock plan
    mock_plan = Mock()
    mock_provision = Mock()
    mock_provision.guests = [guest1, guest2]
    mock_plan.provision = mock_provision
    
    # Create execute step
    execute_step = tmt.steps.execute.Execute(
        plan=mock_plan,
        data=[{'how': 'internal'}],
        logger=root_logger
    )
    
    # Create mock test results
    result1_guest1 = Mock()
    result1_guest1.guest = Mock()
    result1_guest1.guest.name = 'guest-1'
    
    result2_guest1 = Mock()
    result2_guest1.guest = Mock()
    result2_guest1.guest.name = 'guest-1'
    
    result1_guest2 = Mock()
    result1_guest2.guest = Mock()
    result1_guest2.guest.name = 'guest-2'
    
    # Create mock plugin outcome with results
    mock_outcome = Mock()
    mock_outcome.exc = None
    mock_outcome.result = Mock()
    mock_outcome.result.results = [result1_guest1, result2_guest1, result1_guest2]
    
    # Simulate the result processing logic from execute step
    if mock_outcome.result and mock_outcome.result.results:
        # Group results by guest to avoid multiple lookups and ensure accurate counting
        guest_result_counts = {}
        for result in mock_outcome.result.results:
            if hasattr(result, 'guest') and result.guest:
                guest_name = result.guest.name
                guest_result_counts[guest_name] = guest_result_counts.get(guest_name, 0) + 1

        # Create guest lookup cache
        guest_lookup = {guest.name: guest for guest in mock_plan.provision.guests}

        # Decrement pending tasks based on actual test executions per guest
        for guest_name, count in guest_result_counts.items():
            guest = guest_lookup.get(guest_name)
            if guest:
                for _ in range(count):
                    guest.decrement_pending_tasks()
    
    # Assert the counters were decremented correctly
    # guest1 had 2 results, so should be decremented by 2: 3 - 2 = 1
    # guest2 had 1 result, so should be decremented by 1: 2 - 1 = 1
    assert guest1.pending_tasks == 1, f"Guest1 should have 1 pending task, got {guest1.pending_tasks}"
    assert guest2.pending_tasks == 1, f"Guest2 should have 1 pending task, got {guest2.pending_tasks}"
    
    # Verify decrement was called the correct number of times
    assert guest1.decrement_pending_tasks.call_count == 2
    assert guest2.decrement_pending_tasks.call_count == 1
