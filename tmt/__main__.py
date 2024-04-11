import sys


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
        import tmt.utils  # noqa: I001
        import tmt.cli
        tmt.cli.main()
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
            print(f"Error: failed while importing tmt package: {nested_error}", file=sys.stderr)
            raise SystemExit(2) from nested_error


if __name__ == "__main__":
    run_cli()
