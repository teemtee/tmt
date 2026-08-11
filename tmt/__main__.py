import traceback

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

    except Exception as error:
        # `tmt` may be unbound. In theory, `import tmt.utils` might have
        # raised an exception, and we might end up touching `tmt.utils`
        # that's not fully imported.
        #
        # Yet the reporting tools we have available are very nice, it would
        # be a shame to not use them if we can. Let's try using our tools,
        # and fall back to the very basic tools if anything goes wrong.

        try:
            # If we already succeeded importing `tmt.utils`, this will proceed
            # safely, pretty much a no-op. If we failed to import `tmt.utils`,
            # this will fail, but that's fine, we are ready for double fault.
            from tmt.utils import show_exception

            show_exception(error)

            raise SystemExit(2) from error

        except Exception:
            # No need to capture the exception in a variable: we are still
            # inside an `except` clause, Python will chain exceptions for
            # us. Reporting "the original" exception will include "the
            # current" one as well.
            traceback.print_exc()

            raise SystemExit(2) from error


if __name__ == "__main__":
    run_cli()
