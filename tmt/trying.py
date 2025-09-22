"""
Easily try tests and experiment with guests
"""

import functools
import os
import re
import shlex
import textwrap
from collections.abc import Iterator
from itertools import groupby
from typing import Any, Callable, ClassVar, Optional, Union, cast

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
from tmt.base import RunData
from tmt.steps.prepare import PreparePlugin
from tmt.utils import Command, GeneralError, MetadataError, Path
from tmt.utils.themes import style

USER_PLAN_NAME = "/user/plan"


ActionHandler = Callable[['Try', Plan], None]
PromptHandler = Callable[['Try'], None]


class ActionMeta(type):
    """Helper meta class to allow enum-like indexing"""

    def __new__(
        cls, name: str, supers: tuple[type, ...], attrdict: dict[str, Any]
    ) -> 'ActionMeta':
        cls._registry: dict[str, Action] = {}
        return super().__new__(cls, name, supers, attrdict)

    def __getattr__(cls, key: str) -> 'Action':
        if key in cls._registry:
            return cls._registry[key]
        raise AttributeError(key)


class Action(metaclass=ActionMeta):
    """Represents an registered action"""

    _registry: ClassVar[dict[str, 'Action']]

    command: str
    help_text: str
    func: ActionHandler
    order: int
    group: int
    exit_loop: bool
    hidden: bool
    prompt_function: Optional[PromptHandler]

    def __init__(
        self,
        command: str,
        shortcut: Optional[str] = None,
        order: int = 0,
        group: int = 0,
        exit_loop: bool = False,
        hidden: bool = False,
        prompt_function: Optional[PromptHandler] = None,
    ) -> None:
        self.command = command.lower()
        self.shortcut = shortcut.lower() if shortcut else None
        self.order = order
        self.group = group
        self.exit_loop = exit_loop
        self.hidden = hidden
        self.prompt_function = prompt_function

        def _add_action(action: str) -> None:
            if action in Action._registry:
                existing_action = Action._registry[action]
                raise ValueError(
                    f"The '{action}' is already registered for action "
                    f"'{existing_action.command}' (function: {existing_action.func.__name__})"
                )
            Action._registry[action] = self

        # Add action for the command
        _add_action(command)

        # Add action for the shortcut if present
        if shortcut:
            _add_action(shortcut)

    def __call__(self, func: ActionHandler) -> ActionHandler:
        self.func = func
        self.help_text = (
            textwrap.dedent(func.__doc__).strip().splitlines()[0] if func.__doc__ else ""
        ).lower()
        return func

    @classmethod
    def find(cls, command: str) -> 'Action':
        action = cls._registry[command]

        # Do not expose hidden actions
        if action.hidden:
            raise KeyError("Hidden action")

        return action

    @classmethod
    def get_sorted_actions(cls) -> list['Action']:
        """Get unique actions sorted by group and order"""
        seen_functions: set[ActionHandler] = set()
        actions: list[Action] = []
        for action in sorted(
            cls._registry.values(), key=lambda x: (x.group, x.order, x.func.__name__)
        ):
            if action.func not in seen_functions:
                actions.append(action)
                seen_functions.add(action.func)
        return actions

    @functools.cached_property
    def command_length(self) -> int:
        """
        Calculate the command length in the menu including possible separate shortcut,
        e.g. 'command [shortcut]' in case the shortcut not matched in the command
        """
        # Count the length of the displayed action command
        # plus the possible shortcut, e.g. 'command [shortcut]'
        if self.shortcut is None or self.command.find(self.shortcut) != -1:
            return len(self.command)

        # Calculate the padding according to menu item being 'command [shortcut]'
        return len(self.command) + len(self.shortcut) + 3

    @functools.cached_property
    def longest_command_length(self) -> int:
        """
        Calculate longest command in the menu including possible
        separate shortcut. Do not count the actions hidden in the menu.
        """
        return max(
            action.command_length for action in Action._registry.values() if not action.hidden
        )

    @functools.cached_property
    def menu_item(self) -> str:
        """
        Show menu with the keyboard shortcut highlighted if present.
        If the shortcut does not match string in the command,
        display it next to the command in square brackets.
        """
        padding = " " * (self.longest_command_length + 3 - self.command_length)

        # No shortcut
        if self.shortcut is None:
            return style(self.command, fg="bright_blue") + padding + self.help_text

        # Find the key in the command and highlight it
        shortcut_index: int = self.command.find(self.shortcut) if self.shortcut else -1

        # If shortcut cannot be found in the command, add it next to the command in brackets
        if shortcut_index == -1:
            return (
                style(self.command + f' [{self.shortcut}]', fg="bright_blue")
                + padding
                + self.help_text
            )

        before = style(self.command[:shortcut_index], fg="bright_blue")
        highlighted_key = style(
            self.command[shortcut_index : shortcut_index + (len(self.shortcut))],
            fg="blue",
            bold=True,
            underline=True,
        )
        after = style(self.command[shortcut_index + len(self.shortcut) :], fg="bright_blue")

        return before + highlighted_key + after + padding + self.help_text


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
        self._previous_test_dir: Optional[Path] = None
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

    def check_tests(self, directory: Optional[Path] = None) -> None:
        """
        Check for available tests
        """

        tmt.Test.cli_invocation = None  # Reset possible previous filtering

        # Determine base directory for test discovery
        directory = directory or Path.cwd()

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
            relative_path = directory.relative_to(self.tree.root)
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

    def choose_action(self) -> 'Action':
        """
        Print menu, get next action
        """

        while True:
            # Get unique actions for menu display, sorted by group and order
            displayed_actions = Action.get_sorted_actions()

            menu_lines = ["", "What do we do next?"]

            # Group actions dynamically by their group attribute
            for _, group_actions in groupby(displayed_actions, key=lambda x: x.group):
                group_list = list(group_actions)
                menu_lines.extend(
                    f"    {action.menu_item}" for action in group_list if not action.hidden
                )
                menu_lines.append("")

            self.print("\n".join(menu_lines))

            try:
                answer = input("> ")
            except EOFError:
                return Action.quit

            try:
                self.print("")
                return Action.find(answer)
            except KeyError:
                self.print(style(f"Invalid action '{answer}'.", fg="red"))

    def action_start(self, plan: Plan) -> None:
        """
        Common start actions
        """

        plan.wake()

    @Action("start_test", hidden=True)
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

    @Action("start_login", hidden=True)
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

    @Action("start_ask", hidden=True)
    def action_start_ask(self, plan: Plan) -> None:
        """
        Ask what to do
        """

        self.action_start(plan)

        plan.provision.go()

    @Action("test", shortcut="t", order=1, group=1)
    def action_test(self, plan: Plan) -> None:
        """
        Rediscover tests and execute them again
        """

        plan.discover.go(force=True)
        plan.execute.go(force=True)

    @Action("login", shortcut="l", order=2, group=1)
    def action_login(self, plan: Plan) -> None:
        """
        Log into the guest for experimenting
        """

        assert plan.login is not None  # Narrow type
        plan.login.go(force=True)

    def prompt_verbose(self) -> None:
        """
        Prompt for verbosity level.
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

    @Action("verbose", shortcut="v", order=4, group=1, prompt_function=prompt_verbose)
    def action_verbose(self, plan: Plan) -> None:
        """
        Set the desired level of verbosity.
        """
        for step in plan.steps(enabled_only=False):
            step.verbosity_level = self.verbosity_level
            for phase in step.phases():
                phase.verbosity_level = self.verbosity_level

    def prompt_debug(self) -> None:
        """
        Prompt for debug level.
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

    @Action("debug", shortcut="b", order=5, group=1, prompt_function=prompt_debug)
    def action_debug(self, plan: Plan) -> None:
        """
        Choose a different debugging level
        """

        for step in plan.steps(enabled_only=False):
            step.debug_level = self.debug_level
            for phase in step.phases():
                phase.debug_level = self.debug_level

    @Action("discover", shortcut="d", order=6, group=2)
    def action_discover(self, plan: Plan) -> None:
        """
        Gather information about tests to be executed
        """

        plan.discover.go(force=True)

    @Action("prepare", shortcut="p", order=7, group=2)
    def action_prepare(self, plan: Plan) -> None:
        """
        Prepare the environment for testing
        """

        try:
            plan.prepare.go(force=True)
        except GeneralError as error:
            self._show_exception(error)

    @Action("execute", shortcut="e", order=8, group=2)
    def action_execute(self, plan: Plan) -> None:
        """
        Run tests using the specified executor
        """

        plan.execute.go(force=True)

    @Action("report", shortcut="r", order=9, group=2)
    def action_report(self, plan: Plan) -> None:
        """
        Provide test results overview and send reports
        """

        plan.report.go(force=True)

    @Action("finish", shortcut="f", order=10, group=2)
    def action_finish(self, plan: Plan) -> None:
        """
        Perform the user defined finishing tasks
        """

        plan.finish.go()

    @Action("cleanup", shortcut="c", order=11, group=2)
    def action_cleanup(self, plan: Plan) -> None:
        """
        Clean up guests and prune the workdir
        """

        plan.cleanup.go()

    @Action("keep", shortcut="k", order=12, group=3, exit_loop=True)
    def action_keep(self, plan: Plan) -> None:
        """
        Exit the session but keep the run for later use
        """

        run_id = style(str(plan.run_workdir), fg="magenta")
        self.print(f"Run {run_id} kept unfinished. See you soon!")

    @Action("quit", shortcut="q", order=13, group=3, exit_loop=True)
    def action_quit(self, plan: Plan) -> None:
        """
        Clean up the run and quit the session
        """

        # Clean up the run unless already done
        if plan.cleanup.status() != "done":
            plan.cleanup.go()

        # Mention the run id and say good bye
        run_id = style(str(plan.run_workdir), fg="magenta")
        self.print(f"Run {run_id} successfully finished. Bye for now!")

    def _handle_interactive_prompt(
        self,
        prompt: str,
        context: str,
        handler: Callable[[str], None],
        error_message: Optional[str] = None,
    ) -> None:
        quit_message = f"Exiting {context} mode."
        quit_action = Action.quit
        while True:
            self.print(
                style(f"Enter {prompt} (or '\\{quit_action.shortcut}' to quit): ", fg="green")
            )
            try:
                user_input = input("> ")
            except (KeyboardInterrupt, EOFError):
                self.print(quit_message)
                break

            if not user_input or user_input == f'\\{quit_action.shortcut}':
                self.print(quit_message)
                break

            try:
                handler(user_input)
            except Exception as error:
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=error_message.format(user_input) if error_message else str(error),
                    include_logfiles=True,
                    logger=self._logger,
                )

    @Action("lcd", order=3, group=1)
    def action_local_change_directory(self, plan: Plan) -> None:
        """
        Change directory on the local host, discover tests there
        Use case(s):
        1. Run the test you're currently in

        :raises tmt.utils.DiscoverError: If no metadata is found in the current directory
        :raises tmt.utils.GeneralError: If the directory is outside the fmf root or
            if the directory does not exist
        """

        def handler(dir_path: Union[str, Path]) -> None:
            if not plan.fmf_root:
                raise tmt.utils.DiscoverError("No metadata found in the current directory.")

            fmf_root = plan.fmf_root.resolve()
            dir_path = Path(dir_path).resolve()

            if not dir_path.exists():
                raise tmt.utils.GeneralError(f"No such file or directory: '{dir_path}'")

            if not dir_path.is_relative_to(fmf_root):
                raise tmt.utils.GeneralError(
                    f"Directory '{dir_path}' is outside the fmf root: {fmf_root}"
                )

            os.chdir(dir_path)
            current_test_dir = Path.cwd()

            # Rediscover tests ONLY if directory changed
            if (
                self._previous_test_dir is None
                or self._previous_test_dir.resolve() != current_test_dir.resolve()
            ):
                self.print(f"Changed directory to: {current_test_dir}")
                self.check_tests(current_test_dir)
                self.print("Matching tests found\n" + tmt.utils.format_value(self.tests))
                self._previous_test_dir = current_test_dir

        self._handle_interactive_prompt(
            prompt="directory path",
            context="local change directory",
            handler=handler,
        )

    @Action("host", shortcut="h", order=3, group=1)
    def action_host(self, plan: Plan) -> None:
        """
        Run command on the host
        """

        def handler(command: str) -> None:
            Command(*shlex.split(command)).run(
                cwd=plan.workdir, logger=self._logger, interactive=True
            )

        self._handle_interactive_prompt(
            prompt="command",
            context="host command",
            handler=handler,
            error_message="'{0}' command failed to run",
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
        self._workdir = run.run_workdir
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
        action = Action.start_ask
        if self.opt("login"):
            action = Action.start_login
        elif self.opt("ask"):
            pass  # already start_ask
        elif self.tests:
            action = Action.start_test

        # Loop over the actions
        try:
            while True:
                # Handle separate prompting for certain actions
                if action.prompt_function:
                    action.prompt_function(self)

                # Handle the individual actions
                for plan in self.plans:
                    plan.header()
                    action.func(self, plan)

                # Finish if action requests loop exit
                if action.exit_loop:
                    break

                action = self.choose_action()

        # Make sure we clean up when interrupted
        except KeyboardInterrupt:
            for plan in self.plans:
                self.action_quit(plan)
