import sys

#: An entry point to which subcommands should be attached.
ENTRY_POINT_NAME = 'tmt.subcommand'


def import_cli_commands() -> None:
    """
    Import CLI commands from their packages
    """

    # TODO: the whole import compat needs some type annotation polishing,
    # the amount of waivers needed below is stunning.

    # Cannot import on module-level - early import might trigger various
    # side-effects, raise exceptions, and that must happen under the
    # tight control of whoever invoked this function.
    from tmt._compat.importlib.metadata import (
        entry_points,  # type: ignore[reportUnknownVariableType,unused-ignore]
    )

    try:
        eps = entry_points()

        if hasattr(eps, "select"):
            entry_point_group = eps.select(  # type: ignore[reportUnknownVariable,unused-ignore]
                group=ENTRY_POINT_NAME
            )

        else:
            entry_point_group = eps[ENTRY_POINT_NAME]  # type: ignore[assignment]

        for found in entry_point_group:  # type: ignore[reportUnkownVariable,unused-ignore]
            found.load()

    except Exception as exc:
        raise Exception('Failed to discover and import tmt subcommands.') from exc


def run_cli() -> None:
    """
    Entry point to tmt command.

    Cover imports with try/except, to handle errors raised while importing
    tmt packages. Some may perform actions in import-time, and may raise
    exceptions.

    Import utils first, before CLI gets a chance to spawn a logger. Without
    tmt.utils, we would not be able to intercept the exception below.
    """

    try:
        import tmt.utils  # noqa: F401,I001,RUF100

        import_cli_commands()

        import tmt.cli._root
        import tmt.utils.signals

        tmt.utils.signals.install_handlers()

        tmt.cli._root.main()

    except ImportError as error:
        print("Error: tmt package does not seem to be installed")
        raise SystemExit(1) from error
    except Exception as error:
        # ignore[reportUnboundVariable]: linter is right here, `tmt` may be
        # unbound. In theory, `import tmt.utils` might have raised an exception
        # that is not `ImportError`, and we might end up touching `tmt.utils`
        # that's not fully imported. And we cannot `except tmt.utils` either,
        # as the module does not exist in the global scope yet.
        #
        # Silence the linter, but be careful and make sure to report the
        # possible - although very unlikely - secondary exception. Sounds
        # pointless, but let's make investigation easier for us.
        #
        # ignore[unused-ignore]: mypy does not recognize this issue, and therefore
        # the waiver seems pointless to it...
        try:
            tmt.utils.show_exception(error)  # type: ignore[reportUnboundVariable,unused-ignore]
            raise SystemExit(2) from error

        except Exception as nested_error:
            import traceback

            print(f"Error: failed while reporting exception: {nested_error}", file=sys.stderr)
            traceback.print_exc()

            raise SystemExit(2) from nested_error


if __name__ == "__main__":
    run_cli()
