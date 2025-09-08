"""
Easily try tests and experiment with guests
"""

import functools
import re
import shlex
from collections.abc import Callable, Iterator
from typing import Any, cast

import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.config
import tmt.container
import tmt.log
import tmt.steps
import tmt.steps.execute
import tmt.steps.prepare
import tmt.steps.prepare.feature
import tmt.templates
import tmt.utils
from tmt import Plan
from tmt._compat.typing import TypeAlias
from tmt.base import RunData
from tmt.container import container
from tmt.steps.prepare import PreparePlugin
from tmt.utils import Command, GeneralError, MetadataError, Path
from tmt.utils.themes import style

USER_PLAN_NAME = "/user/plan"

ActionHandler: TypeAlias = Callable[[Callable[..., Any]], Callable[..., Any]]


@container
class ActionInfo:
    """Information about a registered action"""

    commands: set[str]
    help_text: str
    func: Callable[..., Any]

    @functools.cached_property
    def primary_command(self) -> str:
        """Return the primary (first) command"""
        return min(self.commands)

    @functools.cached_property
    def key(self) -> str:
        """Return the keyboard shortcut (first character of first command)"""
        return self.primary_command[0]

    @functools.cached_property
    def full_name(self) -> str:
        """Return the full command name (longest command)"""
        return max(self.commands, key=len)

    @functools.cached_property
    def menu_item(self) -> str:
        """Show menu with the keyboard shortcut highlighted"""
        full_name = self.full_name
        key = self.key

        # Find the key in the full name and highlight it
        key_index = full_name.lower().find(key.lower())
        if key_index == -1:
            # Fallback: highlight first character
            key_index = 0

        before = style(full_name[:key_index], fg="bright_blue")
        highlighted_key = style(full_name[key_index], fg="blue", bold=True, underline=True)
        after = style(full_name[key_index + 1 :], fg="bright_blue")

        # Calculate padding based on longest action name
        longest = 0
        if ACTION_REGISTRY:
            longest = max(len(action.full_name) for action in ACTION_REGISTRY.values())
        padding = " " * (longest + 3 - len(full_name))

        return before + highlighted_key + after + padding + self.help_text


ACTION_REGISTRY: dict[str, ActionInfo] = {}


def action(*commands: str) -> ActionHandler:
    """
    Decorator to register an action with given command names.

    The help text is extracted from the function's docstring.
    Multiple command names can be provided (e.g., 'q', 'quit').
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        help_text = func.__doc__ or ""
        # Extract first line of docstring as help text
        help_text = help_text.strip().split('\n')[0] if help_text else ""

        action_info = ActionInfo(commands=set(commands), help_text=help_text, func=func)

        # Register all commands for this action
        for command in commands:
            ACTION_REGISTRY[command.lower()] = action_info

        return func

    return decorator


def find_action(answer: str) -> ActionInfo:
    """Find action by command name (shortcut or full name)"""
    answer = answer.lower()
    if answer in ACTION_REGISTRY:
        return ACTION_REGISTRY[answer]
    raise KeyError(f"Unknown action: {answer}")


class Try(tmt.utils.Common):
    def __init__(
        self,
        *,
        tree: tmt.Tree,
        logger: tmt.log.Logger,
        **kwargs: Any,
    ) -> None:
        """
        Just store the tree
        """

        super().__init__(logger=logger, **kwargs)

        self.tree = tree
        self.tests: list[tmt.Test] = []
        self.plans: list[Plan] = []
        self.image_and_how = self.opt("image_and_how")
        self.cli_options = ["epel", "fips", "install"]

        # Use the verbosity level 3 unless user explicitly requested
        # a different level on the command line
        if self.verbosity_level == 0:
            self.verbosity_level: int = 3

        # Use the interactive mode during test execution
        tmt.steps.execute.Execute.store_cli_invocation(
            context=None,
            options={"interactive": True},
        )

    def _show_exception(self, exc: Exception) -> None:
        """
        A little helper for consistent exception reporting.
        """

        tmt.utils.show_exception(
            exc,
            traceback_verbosity=tmt.utils.TracebackVerbosity.DEFAULT,
            include_logfiles=True,
        )

    def check_tree(self) -> None:
        """
        Make sure there is a sane metadata tree
        """

        # Both tree and root should be defined
        try:
            if self.tree and self.tree.root:
                return

        # Create a dumb fmf Tree if no metadata around
        except MetadataError:
            self.tree.tree = fmf.Tree({"nothing": "here"})

    def check_tests(self) -> None:
        """
        Check for available tests
        """

        # Search for tests according to provided names
        test_names = list(self.opt("test"))
        if test_names:
            self.tests = self.tree.tests(names=test_names)
            if not self.tests:
                raise tmt.utils.GeneralError(
                    f"No test matching '{fmf.utils.listed(test_names)}' found."
                )

        # Default to tests under the current working directory
        else:
            if not self.tree.root:
                self.debug("No fmf tree root, no tests.")
                return
            relative_path = Path(".").relative_to(self.tree.root)
            test_names = [f"^/{relative_path}"]
            self.tests = self.tree.tests(names=test_names)
            if not self.tests:
                self.warn(f"No tests found under the '{relative_path}' directory.")

        # Short debug info about what was found
        self.debug("Test name filter", fmf.utils.listed(test_names, quote="'"))
        self.debug("Matching tests found\n" + tmt.utils.format_value(self.tests))

        # Inject the test filtering options into the Test class
        options = {"names": [f"^{re.escape(test.name)}$" for test in self.tests]}
        tmt.Test.store_cli_invocation(context=None, options=options)

    def get_default_plans(self, run: tmt.base.Run) -> list[Plan]:
        """
        Get default plan from user config or the standard template
        """

        # Check user config for custom default plans. Search for all
        # plans starting with the default user plan name (there might be
        # more than just one).
        config_tree = tmt.config.Config(self._logger).fmf_tree
        if config_tree is not None:
            plan_name = re.escape(USER_PLAN_NAME)
            # cast: once fmf is properly annotated, cast() would not be needed.
            # pyright isn't able to infer the type.
            user_plans = list(cast(Iterator[fmf.Tree], config_tree.prune(names=[f"^{plan_name}"])))
            if user_plans:
                for user_plan in user_plans:
                    plan_dict: dict[str, Any] = {user_plan.name: user_plan.data}
                    self.tree.tree.update(plan_dict)
                self.debug("Use the default user plan config.")
                return self.tree.plans(names=[f"^{plan_name}"], run=run)

        # Use the default plan template otherwise
        plan_name = re.escape(tmt.templates.DEFAULT_PLAN_NAME)
        plan_dict = tmt.utils.yaml_to_dict(tmt.templates.MANAGER.render_default_plan())
        self.tree.tree.update(plan_dict)
        self.debug("Use the default plan template.")
        return self.tree.plans(names=[f"^{plan_name}"], run=run)

    def check_plans(self, run: tmt.base.Run) -> None:
        """
        Check for plans to be used for testing
        """

        # Search for matching plans if plan names provided
        plan_names = list(self.opt("plan"))
        if plan_names:
            self.debug("Plan names filter", fmf.utils.listed(plan_names, quote="'"))
            self.plans = self.tree.plans(names=plan_names, run=run)
            if not self.plans:
                raise tmt.utils.GeneralError(
                    f"No plan matching '{fmf.utils.listed(plan_names)}' found."
                )

        # Use default plans if no plan names requested
        else:
            self.plans = self.get_default_plans(run)

        self.debug("Matching plans found\n" + tmt.utils.format_value(self.plans))

        # Attach a login instance to each plan
        for plan in self.plans:
            plan.login = tmt.steps.Login(
                logger=plan.provision._logger.descend(),
                step=plan.provision,
                order=tmt.steps.PHASE_END,
            )

    def welcome(self) -> None:
        """
        Welcome message with summary of what we're going to try
        """

        parts = ["Let's try"]

        # Test names, login, or something
        test_names = [style(test.name, fg="red") for test in self.tests]
        if self.opt("login"):
            parts += [style("login", fg="red")]
        elif test_names and not self.opt("ask"):
            parts += [fmf.utils.listed(test_names, 'test', max=3)]
        else:
            parts += ["something"]
        parts += ["with"]

        # Plan names
        plan_names = [style(plan.name, fg="magenta") for plan in self.plans]
        parts += [fmf.utils.listed(plan_names, 'plan', max=3)]

        # Image names
        if self.image_and_how:
            parts += ["on"]
            image_names = [style(image, fg="blue") for image in self.image_and_how]
            parts += [fmf.utils.listed(image_names)]

        self.print(" ".join(parts) + ".")

    def save(self) -> None:
        """
        Save list of selected plans and enabled steps
        """
        assert self.tree is not None  # narrow type
        assert self._cli_context_object is not None  # narrow type
        data = RunData(
            root=str(self.tree.root) if self.tree.root else None,
            plans=[plan.name for plan in self.plans],
            steps=list(self._cli_context_object.steps),
            environment=self.environment,
            remove=self.opt('remove'),
        )
        self.write(Path('run.yaml'), tmt.utils.dict_to_yaml(data.to_serialized()))

    def choose_action(self) -> ActionInfo:
        """
        Print menu, get next action
        """

        while True:
            # Get unique actions for menu display
            displayed_actions: list[ActionInfo] = []
            seen_functions: set[Callable[..., Any]] = set()

            # Define the order we want to display actions
            action_order = [
                "test",
                "login",
                "host",
                "verbose",
                "debug",
                "discover",
                "prepare",
                "execute",
                "report",
                "finish",
                "cleanup",
                "keep",
                "quit",
            ]

            for action_name in action_order:
                if action_name in ACTION_REGISTRY:
                    action_info = ACTION_REGISTRY[action_name]
                    if action_info.func not in seen_functions:
                        displayed_actions.append(action_info)
                        seen_functions.add(action_info.func)

            menu_lines = ["What do we do next?", ""]

            # Group actions for better readability
            groups: list[list[ActionInfo]] = [
                displayed_actions[0:5],  # test, login, host, verbose, debug
                displayed_actions[5:11],  # discover, prepare, execute, report, finish, cleanup
                displayed_actions[11:13],  # keep, quit
            ]

            for group in groups:
                menu_lines.extend(f"    {action_info.menu_item}" for action_info in group)
                menu_lines.append("")

            self.print("\n".join(menu_lines))

            try:
                answer = input("> ")
            except EOFError:
                return find_action("quit")

            try:
                self.print("")
                return find_action(answer)
            except KeyError:
                self.print(style(f"Invalid action '{answer}'.", fg="red"))

    def action_start(self, plan: Plan) -> None:
        """
        Common start actions
        """

        plan.wake()

    @action("start_test")
    def action_start_test(self, plan: Plan) -> None:
        """
        Start with testing
        """

        self.action_start(plan)

        plan.discover.go()
        plan.provision.go()
        try:
            plan.prepare.go()
        except GeneralError as error:
            self._show_exception(error)
            return
        plan.execute.go()

    @action("start_login")
    def action_start_login(self, plan: Plan) -> None:
        """
        Start with login
        """

        self.action_start(plan)

        plan.provision.go()
        try:
            plan.prepare.go()
        except GeneralError as error:
            self._show_exception(error)
            return
        assert plan.login is not None  # Narrow type
        plan.login.go(force=True)

    @action("start_ask")
    def action_start_ask(self, plan: Plan) -> None:
        """
        Ask what to do
        """

        self.action_start(plan)

        plan.provision.go()

    @action("t", "test")
    def action_test(self, plan: Plan) -> None:
        """
        Test again
        """

        plan.discover.go(force=True)
        plan.execute.go(force=True)

    @action("l", "login")
    def action_login(self, plan: Plan) -> None:
        """
        Log into the guest
        """

        assert plan.login is not None  # Narrow type
        plan.login.go(force=True)

    def prompt_verbose(self) -> None:
        """
        Ask for the desired verbosity level
        """

        self.print("What verbose level do you need?")
        answer = input(f"Choose 0-3, hit Enter to keep {self.verbosity_level}> ")

        if answer == "":
            self.print(f"Keeping verbose level {self.verbosity_level}.")
            return

        try:
            self.verbosity_level = int(answer)
            self.print(f"Switched to verbose level {self.verbosity_level}.")
        except ValueError:
            self.print(f"Invalid level '{answer}'.")

    @action("v", "verbose")
    def action_verbose(self, plan: Plan) -> None:
        """
        Set verbosity level of all loggers in given plan
        """

        for step in plan.steps(enabled_only=False):
            step.verbosity_level = self.verbosity_level
            for phase in step.phases():
                phase.verbosity_level = self.verbosity_level

    def prompt_debug(self) -> None:
        """
        Choose the right debug level
        """

        self.print("Which debug level would you like?")
        answer = input(f"Choose 0-3, hit Enter to keep {self.debug_level}> ")

        if answer == "":
            self.print(f"Keeping debug level {self.debug_level}.")
            return

        try:
            self.debug_level = int(answer)
            self.print(f"Switched to debug level {self.debug_level}.")
        except ValueError:
            self.print(f"Invalid level '{answer}'.")

    @action("b", "debug")
    def action_debug(self, plan: Plan) -> None:
        """
        Set verbosity level of all loggers in given plan
        """

        for step in plan.steps(enabled_only=False):
            step.debug_level = self.debug_level
            for phase in step.phases():
                phase.debug_level = self.debug_level

    @action("d", "discover")
    def action_discover(self, plan: Plan) -> None:
        """
        Discover tests
        """

        plan.discover.go(force=True)

    @action("p", "prepare")
    def action_prepare(self, plan: Plan) -> None:
        """
        Prepare the guest
        """

        try:
            plan.prepare.go(force=True)
        except GeneralError as error:
            self._show_exception(error)

    @action("e", "execute")
    def action_execute(self, plan: Plan) -> None:
        """
        Execute tests
        """

        plan.execute.go(force=True)

    @action("r", "report")
    def action_report(self, plan: Plan) -> None:
        """
        Report results
        """

        plan.report.go(force=True)

    @action("f", "finish")
    def action_finish(self, plan: Plan) -> None:
        """
        Perform the user defined finishing tasks
        """

        plan.finish.go()

    @action("c", "cleanup")
    def action_cleanup(self, plan: Plan) -> None:
        """
        Clean up guests and prune the workdir
        """

        plan.cleanup.go()

    @action("k", "keep")
    def action_keep(self, plan: Plan) -> None:
        """
        Keep run and exit the session
        """

        assert plan.my_run is not None  # Narrow type
        run_id = style(str(plan.my_run.workdir), fg="magenta")
        self.print(f"Run {run_id} kept unfinished. See you soon!")

    @action("q", "quit")
    def action_quit(self, plan: Plan) -> None:
        """
        Clean up the run and quit the session
        """

        # Clean up the run unless already done
        if plan.cleanup.status() != "done":
            plan.cleanup.go()

        # Mention the run id and say good bye
        assert plan.my_run is not None  # Narrow type
        run_id = style(str(plan.my_run.workdir), fg="magenta")
        self.print(f"Run {run_id} successfully finished. Bye for now!")

    @action("h", "host")
    def action_host(self, plan: Plan) -> None:
        """
        Run command on the host
        """

        while True:
            quit_action = find_action("quit")
            self.print(style(f"Enter command (or '\\{quit_action.key}' to quit): ", fg="green"))
            try:
                raw_command = input("> ")
            except (KeyboardInterrupt, EOFError):
                self.print("Exiting host command mode. Bye for now!")
                break

            if not raw_command or raw_command == f'\\{quit_action.key}':
                self.print("Exiting host command mode. Bye for now!")
                break

            # Execute the command on the host
            try:
                Command(*shlex.split(raw_command)).run(
                    cwd=plan.workdir, logger=self._logger, interactive=True
                )
            except tmt.utils.RunError as error:
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"'{raw_command}' command failed to run.",
                    include_logfiles=True,
                    logger=self._logger,
                )

    def handle_options(self, plan: Plan) -> None:
        """
        Choose requested cli option
        """

        for option in self.cli_options:
            if self.opt(option):
                getattr(self, f"handle_{option}")(plan)

    def handle_epel(self, plan: Plan) -> None:
        """
        Enable EPEL repository
        """

        # tmt run prepare --how feature --epel enabled
        # cast: linters do not detect the class `get_class_data()`
        # returns, it's reported as `type[Unknown]`. mypy does not care,
        # pyright does.
        prepare_data_class = cast(  # type: ignore[redundant-cast]
            type[tmt.steps.prepare.feature.PrepareFeatureData],
            tmt.steps.prepare.feature.PrepareFeature.get_data_class(),
        )

        if not tmt.container.container_has_field(prepare_data_class, 'epel'):
            raise GeneralError("Feature 'epel' is not available.")

        # ignore[reportCallIssue,call-arg,unused-ignore]: thanks to
        # dynamic nature of the data class, the field is indeed unknown
        # to type checkers.
        data = prepare_data_class(
            name="tmt-try-epel",
            how='feature',
            epel="enabled",  # type: ignore[reportCallIssue,call-arg,unused-ignore]
        )

        phase: PreparePlugin[Any] = cast(
            PreparePlugin[Any],
            PreparePlugin.delegate(plan.prepare, data=data),
        )

        plan.prepare._phases.append(phase)

    def handle_fips(self, plan: Plan) -> None:
        """
        Enable FIPS mode
        """

        # tmt run prepare --how feature --fips enabled
        # cast: linters do not detect the class `get_class_data()`
        # returns, it's reported as `type[Unknown]`. mypy does not care,
        # pyright does.
        prepare_data_class = cast(  # type: ignore[redundant-cast]
            type[tmt.steps.prepare.feature.PrepareFeatureData],
            tmt.steps.prepare.feature.PrepareFeature.get_data_class(),
        )

        if not tmt.container.container_has_field(prepare_data_class, 'fips'):
            raise GeneralError("Feature 'fips' is not available.")

        # ignore[reportCallIssue,call-arg,unused-ignore]: thanks to
        # dynamic nature of the data class, the field is indeed unknown
        # to type checkers.
        data = prepare_data_class(
            name="tmt-try-fips",
            how='feature',
            fips="enabled",  # type: ignore[reportCallIssue,call-arg,unused-ignore]
        )

        phase: PreparePlugin[Any] = cast(
            PreparePlugin[Any],
            PreparePlugin.delegate(plan.prepare, data=data),
        )

        plan.prepare._phases.append(phase)

    def handle_install(self, plan: Plan) -> None:
        """
        Install local rpm package on the guest.
        """

        # tmt run prepare --how install --package PACKAGE
        from tmt.steps.prepare.install import PrepareInstallData

        data = PrepareInstallData(
            name="tmt-try-install",
            how='install',
            package=list(self.opt("install")),
        )

        phase: PreparePlugin[Any] = cast(
            PreparePlugin[Any],
            PreparePlugin.delegate(plan.prepare, data=data),
        )

        plan.prepare._phases.append(phase)

    def go(self) -> None:
        """
        Run the interactive session
        """

        # Create run, prepare it for testing
        run = tmt.base.Run(tree=self.tree, logger=self._logger, parent=self)
        run.prepare_for_try(self.tree)
        self._workdir = run.workdir
        self.environment = run.environment

        # Check tree, plans and tests, welcome summary
        self.check_tree()
        self.check_plans(run=run)
        self.check_tests()
        self.welcome()
        self.save()

        # Set the default verbosity level, handle options
        for plan in self.plans:
            self.handle_options(plan)
            self.action_verbose(plan)

        # Choose the initial action
        action = find_action("start_ask")
        if self.opt("login"):
            action = find_action("start_login")
        elif self.opt("ask"):
            pass  # already start_ask
        elif self.tests:
            action = find_action("start_test")

        # Loop over the actions
        try:
            while True:
                # Choose the verbose and debug level
                action_name = action.full_name
                if action_name in ["verbose", "debug"]:
                    getattr(self, f"prompt_{action_name}")()

                # Handle the individual actions
                for plan in self.plans:
                    plan.header()
                    action.func(self, plan)

                # Finish for keep and quit
                if action_name in ["keep", "quit"]:
                    break

                action = self.choose_action()

        # Make sure we clean up when interrupted
        except KeyboardInterrupt:
            for plan in self.plans:
                self.action_quit(plan)
