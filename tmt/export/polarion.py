import email.utils
import re
import traceback
from typing import Any, Optional

import fmf.utils
from click import echo, style

import tmt.base
import tmt.convert
import tmt.export
import tmt.utils
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import ConvertError, Path

PolarionException: Any = None
PolarionTestCase: Any = None
PolarionWorkItem: Any = None


POLARION_TRACKER_ID = 117  # ID of polarion in RH's bugzilla
RE_POLARION_URL = r'.*/polarion/#/project/.*/workitem\?id=(.*)'
LEGACY_POLARION_PROJECTS = {'RedHatEnterpriseLinux7'}

# TODO: why this exists?
log = fmf.utils.Logging('tmt').logger


def import_polarion() -> None:
    """ Import polarion python api - pylero """
    try:
        global PolarionException, PolarionTestCase, PolarionWorkItem
        from pylero.exceptions import PyleroLibException as PolarionException
    except ImportError:
        raise ConvertError(
            "Install 'tmt+export-polarion' to use Polarion API")

    try:
        from pylero.work_item import TestCase as PolarionTestCase
        from pylero.work_item import _WorkItem as PolarionWorkItem
    except PolarionException as exc:
        log.debug(traceback.format_exc())
        raise ConvertError("Failed to login with pylero") from exc


def get_polarion_ids(
        query_result: list[Any],
        preferred_project: Optional[str] = None) -> tuple[str, Optional[str]]:
    """ Return case and project ids from query results """
    if not query_result:
        return 'None', None
    if len(query_result) == 1:
        return query_result[0].work_item_id, query_result[0].project_id

    if preferred_project:
        try:
            return next(
                item.work_item_id for item in query_result
                if item.project_id == preferred_project), preferred_project
        except StopIteration:
            pass

    for result in query_result:
        # If multiple cases are found prefer cases from other projects
        # than these legacy ones
        if str(result.project_id) not in LEGACY_POLARION_PROJECTS:
            return result.work_item_id, result.project_id

    return query_result[0].work_item_id, query_result[0].project_id


def find_polarion_case_ids(
        data: dict[str, Optional[str]],
        preferred_project: Optional[str] = None,
        polarion_case_id: Optional[str] = None) -> tuple[str, Optional[str]]:
    """ Find IDs for Polarion case from data dictionary """
    assert PolarionWorkItem

    case_id = 'None'
    project_id = None

    # Search for Polarion case ID directly
    if polarion_case_id:
        query_result = PolarionWorkItem.query(
            f'id:{polarion_case_id}', fields=['work_item_id', 'project_id'])
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    # Search by UUID
    if not project_id and data.get(ID_KEY):
        query_result = PolarionWorkItem.query(
            data.get(ID_KEY), fields=['work_item_id', 'project_id'])
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    # Search by TCMS Case ID
    extra_nitrate = data.get('extra-nitrate')
    if not project_id and extra_nitrate:
        nitrate_case_id_search = re.search(r'\d+', extra_nitrate)
        if not nitrate_case_id_search:
            raise ConvertError(
                "Could not find a valid nitrate testcase ID in 'extra-nitrate' attribute")
        nitrate_case_id = str(int(nitrate_case_id_search.group()))
        query_result = PolarionWorkItem.query(
            f"tcmscaseid:{nitrate_case_id}", fields=['work_item_id', 'project_id'])
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    # Search by extra task
    if not project_id and data.get('extra-task'):
        query_result = PolarionWorkItem.query(
            data.get('extra-task'), fields=['work_item_id', 'project_id'])
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    return case_id, project_id


def get_polarion_case(
        data: dict[str, Optional[str]],
        preferred_project: Optional[str] = None,
        polarion_case_id: Optional[str] = None) -> Optional[PolarionTestCase]:
    """ Get Polarion case through couple different methods """
    import_polarion()

    assert PolarionTestCase
    assert PolarionException

    case_id, project_id = find_polarion_case_ids(data, preferred_project, polarion_case_id)

    try:
        polarion_case = PolarionTestCase(
            project_id=project_id, work_item_id=case_id)
        echo(style(
            f"Test case '{polarion_case.work_item_id!s}' found.",
            fg='blue'))
        return polarion_case
    except PolarionException:
        return None


def create_polarion_case(summary: str, project_id: str, path: Path) -> PolarionTestCase:
    """ Create new polarion case """
    import tmt.export.nitrate

    # Create the new test case
    testcase = PolarionTestCase.create(project_id, summary, summary)
    testcase.tcmscategory = tmt.export.nitrate.get_category(path)
    testcase.update()
    echo(style(f"Test case '{testcase.work_item_id}' created.", fg='blue'))
    return testcase


def add_hyperlink(polarion_case: PolarionTestCase, link: str, role: str = 'testscript') -> None:
    """ Add new hyperlink to a Polarion case and check/remove duplicates """
    existing_hyperlinks = [link.uri for link in polarion_case.hyperlinks if link.role == role]
    if link not in existing_hyperlinks:
        polarion_case.add_hyperlink(link, role)
    else:
        for hyperlink in set(existing_hyperlinks):
            for _ in range(existing_hyperlinks.count(hyperlink) - 1):
                # Remove all but one occurrence of the same hyperlink
                polarion_case.remove_hyperlink(hyperlink)


def export_to_polarion(test: tmt.base.Test) -> None:
    """ Export fmf metadata to a Polarion test case """
    import tmt.export.nitrate
    import_polarion()

    # Check command line options
    create = test.opt('create')
    link_bugzilla = test.opt('bugzilla')
    project_id = test.opt('project_id')
    dry_mode = test.is_dry_run
    duplicate = test.opt('duplicate')
    link_polarion = test.opt('link_polarion')
    append_summary = test.opt('append-summary')

    polarion_case = None
    if not duplicate:
        polarion_case = get_polarion_case(test.node, project_id)
    summary = tmt.export.nitrate.prepare_extra_summary(test, append_summary)
    assert test.path is not None  # narrow type
    test_path = test.node.root / test.path.unrooted()

    if not polarion_case:
        if create:
            if not project_id:
                raise ConvertError(
                    "Please provide project_id so tmt knows which "
                    "Polarion project to use for this test case.")
            if not dry_mode:
                polarion_case = create_polarion_case(
                    summary, project_id=project_id, path=test_path)
            else:
                echo(style(
                    f"Test case '{summary}' created.", fg='blue'))
            test._metadata['extra-summary'] = summary
        else:
            raise ConvertError(
                f"Polarion test case id not found for '{test}'. "
                f"(You can use --create option to enforce creating testcases.)")

    # Title
    if not dry_mode and test.summary is not None and polarion_case.title != test.summary:
        polarion_case.title = test.summary
    # TODO: test.summary may be left unset, i.e. `None` is a possibility here. Shall we print
    # new title then? It may also be `None`...
    if test.summary is not None:
        echo(style('title: ', fg='green') + test.summary)

    # Add id to Polarion case
    uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    if not uuid:
        uuid = test.node.get(ID_KEY)
    if not dry_mode:
        polarion_case.tmtid = uuid
        polarion_case.update()  # upload the ID first so the case can be found in case of errors
        # Check if it was really uploaded
        polarion_case.tmtid = ''
        polarion_case.reload()
        if not polarion_case.tmtid:
            echo(style(
                f"Can't add ID because {polarion_case.project_id} project "
                "doesn't have the 'tmtid' field defined.",
                fg='yellow'))
    if dry_mode or polarion_case.tmtid:
        echo(style(f"Append the ID {uuid}.", fg='green'))

    # Description
    description = summary
    if test.description:
        description += ' - ' + test.description
    if test.environment:
        description += '<br/>Environment variables:'
        for key, value in test.environment.items():
            description += f'<br/>{key}={value}'
    if not dry_mode:
        polarion_case.description = description
    echo(style('description: ', fg='green') + description)

    # Automation
    assert test.fmf_id.url is not None  # narrow type
    if test.node.get('extra-task'):
        automation_script = test.node.get('extra-task')
        automation_script += f'<br/>{test.fmf_id.url}'
    else:
        automation_script = test.fmf_id.url
    if not dry_mode:
        polarion_case.caseautomation = 'automated'
        if test.link:
            for link in test.link.get(relation='test-script'):
                if isinstance(link.target, str):
                    automation_script += f'<br/>{link.target}'
                    add_hyperlink(polarion_case, link.target)
        polarion_case.automation_script = automation_script
        web_link = test.web_link()
        if web_link:
            add_hyperlink(polarion_case, web_link)
    echo(style('script: ', fg='green') + automation_script)

    # Components
    if not dry_mode:
        polarion_case.caselevel = 'component'
        polarion_case.testtype = 'functional'
        if test.component:
            # Depending on project this can require either single item or list,
            # however we are always taking the first component only for consistency
            try:
                polarion_case.casecomponent = test.component[0]
            except PolarionException:
                polarion_case.casecomponent = [test.component[0]]
    echo(style('components: ', fg='green') + ' '.join(test.component))

    # Tags and Importance
    if not dry_mode:
        if test.tier is not None:
            if int(test.tier) <= 1:
                polarion_case.caseimportance = 'high'
            elif int(test.tier) == 2:
                polarion_case.caseimportance = 'medium'
            else:
                polarion_case.caseimportance = 'low'
            test.tag.append(f"Tier{test.tier}")
        else:
            polarion_case.caseimportance = 'medium'

    test.tag.append('fmf-export')
    if not dry_mode:
        polarion_case.tags = ' '.join(test.tag)
    echo(style('tags: ', fg='green') + ' '.join(set(test.tag)))

    # Default tester
    if test.contact:
        # Need to pick one value, so picking the first contact
        email_address = email.utils.parseaddr(test.contact[0])[1]
        login_name = email_address[:email_address.find('@')]
        try:
            if not dry_mode:
                polarion_case.add_assignee(login_name)
            echo(style('default tester: ', fg='green') + login_name)
        except PolarionException as err:
            log.debug(err)

    # Status
    if not dry_mode:
        if test.enabled:
            polarion_case.status = 'approved'
        else:
            polarion_case.status = 'inactive'
    echo(style('enabled: ', fg='green') + str(test.enabled))

    echo(style("Append the Polarion test case link.", fg='green'))
    if not dry_mode and link_polarion:
        with test.node as data:
            server_url = str(polarion_case._session._server.url)
            tmt.convert.add_link(
                f'{server_url}{"" if server_url.endswith("/") else "/"}'
                f'#/project/{polarion_case.project_id}/workitem?id='
                f'{polarion_case.work_item_id!s}',
                data, system=tmt.convert.SYSTEM_OTHER, type_='implements')

    # List of bugs test verifies
    bug_ids = []
    requirements = []
    if test.link:
        for link in test.link.get('verifies'):
            if isinstance(link.target, tmt.base.FmfId):
                log.debug(f"Will not look for bugzila URL in fmf id '{link.target}'.")
                continue

            try:
                bug_ids_search = re.search(tmt.export.RE_BUGZILLA_URL, link.target)
                if bug_ids_search:
                    bug_ids.append(int(bug_ids_search.group(1)))
                else:
                    log.debug("Failed to find bug ID in the 'verifies' link.")
                polarion_url_search = re.search(RE_POLARION_URL, link.target)
                if polarion_url_search:
                    requirements.append(polarion_url_search.group(1))
                else:
                    log.debug("Failed to find Polarion URL in the 'verifies' link.")
            except Exception as err:
                log.debug(err)

    # Add bugs to the Polarion case
    if not dry_mode:
        polarion_case.tcmsbug = ', '.join(str(bug_ids))

    # Add TCMS Case ID to Polarion case
    if test.node.get('extra-nitrate') and not dry_mode:
        tcms_case_id_search = re.search(r'\d+', test.node.get("extra-nitrate"))
        if tcms_case_id_search:
            polarion_case.tcmscaseid = str(int(tcms_case_id_search.group()))

    # Add Requirements to Polarion case
    if not dry_mode:
        for req in requirements:
            polarion_case.add_linked_item(req, 'verifies')

    # Update Polarion test case
    if not dry_mode:
        polarion_case.update()
    echo(style(
        f"Test case '{summary}' successfully exported to Polarion.",
        fg='magenta'))

    # Optionally link Bugzilla to Polarion case
    if link_bugzilla and bug_ids and not dry_mode:
        case_id = (f"{polarion_case.project_id}/workitem?id="
                   f"{polarion_case.work_item_id!s}")
        tmt.export.bz_set_coverage(bug_ids, case_id, POLARION_TRACKER_ID)


@tmt.base.Test.provides_export('polarion')
class PolarionExporter(tmt.export.ExportPlugin):
    @classmethod
    def export_test_collection(cls,
                               tests: list[tmt.base.Test],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        for test in tests:
            export_to_polarion(test)

        return ''
