import functools
import textwrap

import pytest

from tmt.utils import GeneralError, render_exception
from tmt.utils.themes import style

R = functools.partial(style, fg='red')


def test_causes() -> None:
    """
    Verify :py:func:`render_exception` includes all kinds of exception causes.
    """

    try:
        try:
            # Generate two exceptions we would then pass to a `GeneralError`
            # as causes.
            causes = []

            try:
                raise ValueError('Level 3.1 - first cause')

            except Exception as exc:
                causes.append(exc)

            try:
                raise ValueError('Level 3.2 - second cause')

            except Exception as exc:
                causes.append(exc)

            # Generate third "cause" - first two would be passed via `cause`
            # parameter, which is tmt extension to allow multiple causes,
            # and the third would be added by the interpreter thanks to
            # the `raise ... from` construct.
            try:
                raise ValueError('Level 3.3 - third cause')

            except Exception as exc:
                raise GeneralError('Level 2', causes=causes) from exc

        # Except the `Level 2` exception, and attach it to yet another
        # exception. We create multiple levels of causes...
        except Exception as exc:
            raise GeneralError('Level 1 - except') from exc

        # ... but we also can test whether exception context is rendered.
        # Raising an exception from `finally` should attach the `Level 1`
        # exception to the newly raised one.
        finally:
            raise Exception('Level 1 - finally')

    except Exception as exc:
        actual = '\n'.join(render_exception(exc))

    assert (
        actual
        == textwrap.dedent(f"""
        {R("Level 1 - finally")}

        The exception was caused by 1 earlier exceptions

        Cause number 1:

            {R("Level 1 - except")}

            The exception was caused by 1 earlier exceptions

            Cause number 1:

                {R("Level 2")}

                The exception was caused by 3 earlier exceptions

                Cause number 1:

                    {R("Level 3.1 - first cause")}

                Cause number 2:

                    {R("Level 3.2 - second cause")}

                Cause number 3:

                    {R("Level 3.3 - third cause")}
    """).strip()
    )
