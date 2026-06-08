import sys
import traceback
from typing import NoReturn, Optional


def import_cli_commands() -> None:
    """
    Import CLI commands from their packages
    """

    # TODO: some kind of `import tmt.cli.*` would be nice
    import tmt.cli.about  # noqa: F401,I001,RUF100  # type: ignore[reportUnusedImport]
    import tmt.cli.init  # noqa: F401,I001,RUF100  # type: ignore[reportUnusedImport]
    import tmt.cli.lint  # noqa: F401,I001,RUF100 # type: ignore[reportUnusedImport]
    import tmt.cli.status  # noqa: F401,I001,RUF100 # type: ignore[reportUnusedImport]
    import tmt.cli.trying  # noqa: F401,I001,RUF100 # type: ignore[reportUnusedImport]


def report_exception(
    exception: Exception, exit_code: int = 2, message: Optional[str] = None
) -> NoReturn:
    # `tmt` may be unbound. In theory, `import tmt.utils` might have
    # raised an exception, and we might end up touching `tmt.utils`
    # that's not fully imported.
    #
    # Yet the reporting tools we have available are very nice, it would
    # be a shame to not use them if we can. Let's try using our tools,
    # and fall back to the very basic tools if anything goes wrong.

    if message:
        print(message, file=sys.stderr)

    try:
        # If we already succeeded importing `tmt.utils`, this will proceed
        # safely, pretty much a no-op. If we failed to import `tmt.utils`,
        # this will fail, but that's fine, we are ready for double fault.
        from tmt.utils import show_exception

        show_exception(exception)

        raise SystemExit(exit_code) from exception

    except Exception:
        # No need to capture the exception in a variable: we are still
        # inside an `except` clause, Python will chain exceptions for
        # us. Reporting "the current" exception will include the nested
        # one as well.
        traceback.print_exc()

        raise SystemExit(exit_code) from exception


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
        report_exception(
            error, exit_code=1, message="Error: tmt package does not seem to be installed"
        )

    except Exception as error:
        report_exception(error)


if __name__ == "__main__":
    run_cli()
