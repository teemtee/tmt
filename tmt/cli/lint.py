""" ``tmt lint`` and ``tmt * lint`` implementation """

from typing import Any, Optional, Union

from click import echo

import tmt.base
import tmt.lint
import tmt.utils
from tmt.cli import Context, pass_context
from tmt.cli._root import (
    filtering_options,
    fix_options,
    fmf_source_options,
    lint_options,
    main,
    plans,
    stories,
    tests,
    verbosity_options,
    )


def _apply_linters(
        lintable: Union[tmt.lint.Lintable[tmt.base.Test],
                        tmt.lint.Lintable[tmt.base.Plan],
                        tmt.lint.Lintable[tmt.base.Story],
                        tmt.lint.Lintable[tmt.base.LintableCollection]],
        linters: list[tmt.lint.Linter],
        failed_only: bool,
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome]) -> tuple[
            bool, Optional[list[tmt.lint.LinterRuling]]]:
    """Apply linters on a lintable and filter out disallowed outcomes."""

    valid, rulings = lintable.lint(
        linters=linters,
        enforce_checks=enforce_checks or None)

    # If the object pass the checks, and we're asked to show only the failed
    # ones, display nothing.
    if valid and failed_only:
        return valid, None

    # Find out what rulings were allowed by user. By default, it's all, but
    # user might be interested in "warn" only, for example. Reduce the list
    # of rulings, and if we end up with an empty list *and* user constrained
    # us to just a subset of rulings, display nothing.
    allowed_rulings = list(tmt.lint.filter_allowed_checks(rulings, outcomes=outcomes))

    if not allowed_rulings and outcomes:
        return valid, None

    return valid, allowed_rulings


def _lint_class(
        context: Context,
        klass: Union[type[tmt.base.Test], type[tmt.base.Plan], type[tmt.base.Story]],
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome],
        **kwargs: Any) -> int:
    """ Lint a single class of objects """

    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)
    klass.store_cli_invocation(context)

    exit_code = 0

    linters = klass.resolve_enabled_linters(
        enable_checks=enable_checks or None,
        disable_checks=disable_checks or None)

    for lintable in klass.from_tree(context.obj.tree):
        valid, allowed_rulings = _apply_linters(
            lintable, linters, failed_only, enforce_checks, outcomes)
        if allowed_rulings is None:
            continue

        lintable.ls()

        echo('\n'.join(tmt.lint.format_rulings(allowed_rulings)))

        if not valid:
            exit_code = 1

        echo()

    return exit_code


def _lint_collection(
        context: Context,
        klasses: list[Union[type[tmt.base.Test], type[tmt.base.Plan], type[tmt.base.Story]]],
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome],
        **kwargs: Any) -> int:
    """ Lint a collection of objects """

    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)

    exit_code = 0

    linters = tmt.base.LintableCollection.resolve_enabled_linters(
        enable_checks=enable_checks or None,
        disable_checks=disable_checks or None)

    objs: list[tmt.base.Core] = [
        obj for cls in klasses
        for obj in cls.from_tree(context.obj.tree)]
    lintable = tmt.base.LintableCollection(objs)

    valid, allowed_rulings = _apply_linters(
        lintable,
        linters,
        failed_only,
        enforce_checks,
        outcomes)
    if allowed_rulings is None:
        return exit_code

    lintable.print_header()

    echo('\n'.join(tmt.lint.format_rulings(allowed_rulings)))

    if not valid:
        exit_code = 1

    echo()

    return exit_code


def do_lint(
        context: Context,
        klasses: list[Union[type[tmt.base.Test], type[tmt.base.Plan], type[tmt.base.Story]]],
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome],
        **kwargs: Any) -> int:
    """ Core of all ``lint`` commands """

    if list_checks:
        for klass in klasses:
            klass_label = 'stories' if klass is tmt.base.Story else f'{klass.__name__.lower()}s'
            echo(f'Linters available for {klass_label}')
            echo(klass.format_linters())
            echo()

        return 0

    res_single = max(_lint_class(
        context,
        klass,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        outcomes,
        **kwargs)
        for klass in klasses)

    res_collection = _lint_collection(
        context,
        klasses,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        outcomes,
        **kwargs)

    return max(res_single, res_collection)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@tests.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def tests_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check tests against the L1 metadata specification.

    Regular expression can be used to filter tests for linting.
    Use '.' to select tests under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Test],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@plans.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def plans_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check plans against the L2 metadata specification.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Plan],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@stories.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def stories_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check stories against the L3 metadata specification.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Story],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def lint(
        context: Context,
        list_checks: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        failed_only: bool,
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check all the present metadata against the specification.

    Combines all the partial linting (tests, plans and stories)
    into one command. Options are applied to all parts of the lint.

    Regular expression can be used to filter metadata by name.
    Use '.' to select tests, plans and stories under the current
    working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Test, tmt.base.Plan, tmt.base.Story],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs
        )

    raise SystemExit(exit_code)
