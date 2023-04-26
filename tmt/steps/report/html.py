import dataclasses
import webbrowser

import jinja2
import pkg_resources

import tmt
import tmt.options
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.utils import Path, field

HTML_TEMPLATE_PATH = pkg_resources.resource_filename(
    'tmt', 'steps/report/html/template.html.j2')


@dataclasses.dataclass
class ReportHtmlData(tmt.steps.report.ReportStepData):
    open: bool = field(
        default=False,
        option=('-o', '--open'),
        is_flag=True,
        help='Open results in your preferred web browser.'
        )

    absolute_paths: bool = field(
        default=False,
        option='--absolute-paths',
        is_flag=True,
        help='Make paths absolute rather than relative to working directory.'
        )

    display_guest: str = field(
        default='auto',
        option='--display-guest',
        metavar='auto|always|never',
        choices=['auto', 'always', 'never'],
        help="When to display full guest name in report:"
             " when more than a single guest was involved (default), always, or never."
        )


@tmt.steps.provides_method('html')
class ReportHtml(tmt.steps.report.ReportPlugin):
    """
    Format test results into an html report

    Example config:

        report:
            how: html
            open: true
    """

    _data_class = ReportHtmlData

    def prune(self, logger: tmt.log.Logger) -> None:
        """ Do not prune generated html report """
        pass

    def go(self) -> None:
        """ Process results """
        super().go()

        # Prepare the template
        environment = jinja2.Environment()
        environment.filters["basename"] = lambda x: Path(x).name

        if self.get('absolute-paths'):
            environment.filters["linkable_path"] = lambda x: str(Path(x).absolute())
        else:
            # Links used in html should be relative to a workdir
            assert self.workdir is not None  # narrow type
            environment.filters["linkable_path"] = lambda x: str(Path(x).relative_to(self.workdir))

        environment.trim_blocks = True
        environment.lstrip_blocks = True
        with open(HTML_TEMPLATE_PATH) as file:
            template = environment.from_string(file.read())

        if self.get('display-guest') == 'always':
            display_guest = True

        elif self.get('display-guest') == 'never':
            display_guest = False

        else:
            seen_guests = {
                result.guest.name
                for result in self.step.plan.execute.results() if result.guest.name is not None
                }

            display_guest = len(seen_guests) > 1

        # Write the report
        filename = Path('index.html')
        self.write(
            filename,
            data=template.render(
                results=self.step.plan.execute.results(),
                base_dir=self.step.plan.execute.workdir,
                plan=self.step.plan,
                display_guest=display_guest))

        # Nothing more to do in dry mode
        if self.opt('dry'):
            return

        # Show output file path
        assert self.workdir is not None
        target = self.workdir / filename
        self.info("output", str(target), color='yellow')
        if not self.get('open'):
            return

        # Open target in webbrowser
        try:
            if webbrowser.open(f"file://{target}", new=0):
                self.info(
                    'open', 'Successfully opened in the web browser.',
                    color='green')
                return
            self.fail("Failed to open the web browser.")
        except Exception as error:
            self.fail(f"Failed to open the web browser: {error}")

        raise tmt.utils.ReportError("Unable to open the web browser.")
