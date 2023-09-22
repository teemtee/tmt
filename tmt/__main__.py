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
        import tmt.utils  # noqaI001
        import tmt.cli
        tmt.cli.main()
    except ImportError as error:
        print("Error: tmt package does not seem to be installed")
        raise SystemExit(1) from error
    # Basic error message for general errors
    except tmt.utils.GeneralError as error:
        tmt.utils.show_exception(error)
        raise SystemExit(2) from error


if __name__ == "__main__":
    run_cli()
