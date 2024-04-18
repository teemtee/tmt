import re
import sys

from tmt.__main__ import run_cli


def _run_precommit() -> None:  # pyright: ignore[reportUnusedFunction] (used by project.scripts)
    """
    A simple wrapper that re-orders cli arguments before :py:func:`run_cli`.

    This utility is needed in order to move arguments like ``--root`` before
    the ``lint`` keyword when run by ``pre-commit``.

    Only a limited number of arguments are reordered.
    """

    # Only re-ordering a few known/necessary cli arguments of `main` command
    # Could be improved if the click commands can be introspected like with
    # `attrs.fields`
    # https://github.com/pallets/click/issues/2709

    argv = sys.argv
    # Get the last argument that starts with `-`. Other inputs after that are
    # assumed to be filenames (which can be thousands of them)
    for last_arg in reversed(range(len(argv))):
        if argv[last_arg].startswith("-"):
            break
    else:
        # If there were no args passed, then just `run_cli`
        run_cli()
        return

    # At this point we need to check and re-order the arguments if needed
    for pattern, nargs in [
            (r"(--root$|-r)", 1),
            (r"(--root=.*)", 0),
            (r"(--verbose$|-v+)", 0),
            (r"(--debug$|-d+)", 0),
            (r"(--pre-check$)", 0),
            ]:
        if any(match := re.match(pattern, arg) for arg in argv[1:last_arg + 1]):
            assert match
            # Actual argument matched
            actual_arg = match.group(1)
            indx = argv.index(actual_arg)
            # Example of reorder args:
            # ["tmt", "tests", "lint", "--fix", "--root", "/some/path", "some_file"]
            # - argv[0]: name of the program is always first
            #   ["tmt"]
            # - argv[indx:indx+1+nargs]: args to move (pass to `tmt.cli.main`)
            #   ["--root", "/some/path"]
            # - argv[1:indx]: all other keywords (`lint` keyword is in here)
            #   ["tests", "lint", "--fix"]
            # - argv[indx+1+nargs:]: All remaining keywords
            #   ["some_file"]
            # After reorder:
            # ["tmt", "--root", "/some/path", "tests", "lint", "--fix", "some_file"]
            argv = (
                argv[0:1] + argv[indx: indx + 1 + nargs] + argv[1:indx] + argv[indx + 1 + nargs:]
                )
    # Finally move the reordered args to sys.argv and run the cli
    sys.argv = argv
    run_cli()


if __name__ == "__main__":
    _run_precommit()
