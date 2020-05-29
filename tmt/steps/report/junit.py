import os

from junit_xml import TestSuite, TestCase
import click
import tmt

class ReportJUnit(tmt.steps.report.ReportPlugin):
    """
    Write test results in JUnit xml format

    """

    # Supported methods
    _methods = [tmt.steps.Method(name='junit', doc=__doc__, order=50)]

    _keys =  ['file']

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options for connect """
        return [
            click.option(
                '--file', metavar='PATH',
                help='Path where to store junit to'),
            ] + super().options(how)

    def go(self):
        """ Discover available tests """
        super().go()

        suite = TestSuite(self.step.plan.name)
        for result in self.step.plan.execute.results():
            jux_result = result.result
            jux_logs = {}
            for log_path in result.log:
                jux_logs[os.path.basename(log_path)] = self.step.plan.execute.read(log_path)
                case = TestCase(result.name, None, 0.0, jux_logs.get('out.log',None), jux_logs.get('err.log', None))
                if jux_result == 'error':
                    case.add_error_info("error")
                elif jux_result == "fail":
                    case.add_failure_info("fail")
                suite.test_cases.append(case)
        f_path = self.opt("file", self.workdir + '/junit.xml')
        with open (f_path, 'w') as fw:
            TestSuite.to_file(fw, [suite])
        self.info("xunit", f_path, 'green')

