import email.utils
import re
import traceback
from typing import Any, Optional

import fmf.utils
from click import echo

import tmt.base
import tmt.convert
import tmt.export
import tmt.utils
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import ConvertError, Path
from tmt.utils.themes import style

PolarionException: Any = None
PolarionTestCase: Any = None
PolarionWorkItem: Any = None
PolarionRequirement: Any = None


POLARION_TRACKER_ID = 117  # ID of polarion in RH's bugzilla
RE_POLARION_URL = r'.*/polarion/#/project/.*/workitem\?id=(.*)'

# TODO: why this exists?
log = fmf.utils.Logging('tmt').logger


def get_canonical_url(url: str) -> str:
    """
    Convert a git URL to the canonical upstream repository URL
    
    Handles forks and converts git URLs to canonical upstream.
    For tmt, the canonical repository is teemtee/tmt.
    """
    if not url:
        return url
    
    # Known canonical repositories
    canonical_repos = {
        'tmt': 'https://github.com/teemtee/tmt',
    }
    
    # Detect if this is a tmt repository (any fork)
    if 'tmt.git' in url or '/tmt/' in url or url.endswith('/tmt'):
        return canonical_repos['tmt']
    
    # If no canonical mapping found, return original
    return url


def get_test_script_link(test: tmt.base.Test) -> Optional[str]:
    """
    Generate a web link to the actual test script (not the metadata file)
    
    Returns a URL pointing to the test script (e.g., test.sh) instead of
    the metadata file (main.fmf) which is what test.web_link() returns.
    
    Also normalizes URLs to use canonical upstream repository and default branch.
    """
    if not test.test or not test.fmf_id.url:
        return None
    
    # Get the web link to the metadata file
    metadata_link = test.web_link()
    if not metadata_link:
        return None
    
    # Normalize to canonical repository
    # Convert psss/tmt, jscotka/tmt, etc. to teemtee/tmt
    canonical_link = metadata_link
    
    # Replace fork repositories with canonical upstream
    if 'github.com' in canonical_link:
        # Extract the repository pattern and replace with canonical
        import re
        # Match patterns like: github.com/username/tmt
        canonical_link = re.sub(
            r'github\.com/[^/]+/tmt',
            'github.com/teemtee/tmt',
            canonical_link
        )
        
        # Replace tree/branch_name with blob/main for default branch
        # This handles local feature branches like stories_polarion
        canonical_link = re.sub(
            r'/tree/[^/]+/',
            '/blob/main/',
            canonical_link
        )
    
    # Extract the test script filename from the test field
    # test.test is usually something like "./test.sh" or "test.sh"
    test_script = str(test.test).lstrip('./')
    
    # Replace main.fmf with the actual test script
    if canonical_link.endswith('/main.fmf'):
        return canonical_link.replace('/main.fmf', f'/{test_script}')
    elif '/main.fmf' in canonical_link:
        # Handle case where there might be query params or anchors
        return canonical_link.replace('/main.fmf', f'/{test_script}')
    else:
        # If main.fmf is not in the URL, try to append the test script
        # Remove trailing slash if present
        base_link = canonical_link.rstrip('/')
        return f'{base_link}/{test_script}'


def import_polarion() -> None:
    """
    Import polarion python api - pylero
    """

    try:
        global PolarionException, PolarionTestCase, PolarionWorkItem, PolarionRequirement
        from pylero.exceptions import PyleroLibException as PolarionException
    except ImportError as error:
        raise ConvertError("Install 'tmt+export-polarion' to use Polarion API") from error

    try:
        from pylero.work_item import TestCase as PolarionTestCase
        from pylero.work_item import _WorkItem as PolarionWorkItem
        
        # PolarionRequirement is just an alias for _WorkItem with type='requirement'
        PolarionRequirement = PolarionWorkItem
    except PolarionException as exc:
        log.debug(traceback.format_exc())
        raise ConvertError("Failed to login with pylero") from exc


def get_polarion_ids(
    query_result: list[Any],
    preferred_project: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Return case and project ids from query results
    """

    if not query_result:
        return None, None
    if len(query_result) == 1 and query_result[0].status != 'inactive':
        return query_result[0].work_item_id, query_result[0].project_id

    if preferred_project:
        try:
            return next(
                item.work_item_id
                for item in query_result
                if item.project_id == preferred_project and item.status != 'inactive'
            ), preferred_project
        except StopIteration:
            pass

    # Return first non-inactive result
    for result in query_result:
        if result.status != 'inactive':
            return result.work_item_id, result.project_id

    return None, None


def find_polarion_case_ids(
    data: dict[str, Optional[str]],
    preferred_project: Optional[str] = None,
    polarion_case_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Find IDs for Polarion case from data dictionary
    
    Searches in order:
    1. Direct polarion_case_id parameter (explicit override)
    2. extra-polarion field (Polarion work item ID stored in FMF)
    """

    assert PolarionWorkItem

    case_id = None
    project_id = None
    wanted_fields = ['work_item_id', 'project_id', 'status']

    # Search for Polarion case ID directly (explicit user override)
    if polarion_case_id:
        query_result = PolarionWorkItem.query(f'id:{polarion_case_id}', fields=wanted_fields)
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    # Search by extra-polarion (Polarion work item ID stored in FMF)
    if not project_id:
        extra_polarion = data.get('extra-polarion')
        if extra_polarion:
            query_result = PolarionWorkItem.query(f'id:{extra_polarion}', fields=wanted_fields)
            case_id, project_id = get_polarion_ids(query_result, preferred_project)

    return case_id, project_id


def get_polarion_case(
    data: dict[str, Optional[str]],
    preferred_project: Optional[str] = None,
    polarion_case_id: Optional[str] = None,
) -> Optional[PolarionTestCase]:
    """
    Get Polarion case through couple different methods
    """

    import_polarion()

    assert PolarionTestCase
    assert PolarionException

    case_id, project_id = find_polarion_case_ids(data, preferred_project, polarion_case_id)
    if case_id is None or project_id is None:
        return None

    try:
        polarion_case = PolarionTestCase(project_id=project_id, work_item_id=case_id)
        echo(style(f"Test case '{polarion_case.work_item_id!s}' found.", fg='blue'))
        return polarion_case
    except PolarionException:
        return None


def create_polarion_case(summary: str, project_id: str, path: Path) -> PolarionTestCase:
    """
    Create new polarion case
    """

    import tmt.export.nitrate

    # Create the new test case
    testcase = PolarionTestCase.create(project_id, summary, summary)
    testcase.tcmscategory = tmt.export.nitrate.get_category(path)
    testcase.update()
    echo(style(f"Test case '{testcase.work_item_id}' created.", fg='blue'))
    return testcase


def add_hyperlink(polarion_case: PolarionTestCase, link: str, role: str = 'testscript') -> None:
    """
    Add new hyperlink to a Polarion case and check/remove duplicates
    """

    existing_hyperlinks = [link.uri for link in polarion_case.hyperlinks if link.role == role]
    if link not in existing_hyperlinks:
        polarion_case.add_hyperlink(link, role)
    else:
        for hyperlink in set(existing_hyperlinks):
            for _ in range(existing_hyperlinks.count(hyperlink) - 1):
                # Remove all but one occurrence of the same hyperlink
                polarion_case.remove_hyperlink(hyperlink)


def export_to_polarion(
    test: tmt.base.Test,
    options: Optional[dict[str, Any]] = None
) -> Optional[PolarionTestCase]:
    """
    Export fmf metadata to a Polarion test case
    
    Args:
        test: The test object to export
        options: Optional dictionary of options to override CLI options
                 (useful when calling from other export functions)
    
    Returns:
        The Polarion test case object, or None if in dry mode or export failed
    """

    import tmt.export.nitrate

    import_polarion()

    # Check command line options (with optional overrides)
    if options is None:
        options = {}
    create = options.get('create', test.opt('create'))
    link_bugzilla = options.get('bugzilla', test.opt('bugzilla'))
    project_id = options.get('project_id', test.opt('project_id'))
    dry_mode = options.get('dry_mode', test.is_dry_run)
    duplicate = options.get('duplicate', test.opt('duplicate'))
    link_polarion = options.get('link_polarion', test.opt('link_polarion'))
    append_summary = options.get('append-summary', test.opt('append-summary'))
    ignore_git_validation = options.get('ignore_git_validation', test.opt('ignore_git_validation'))

    # Check git is already correct
    valid, error_msg = tmt.utils.git.validate_git_status(test)
    if not valid:
        if ignore_git_validation:
            echo(style(f"Exporting regardless '{error_msg}'.", fg='red'))
        else:
            raise ConvertError(
                f"Can't export due '{error_msg}'.\n"
                "Use --ignore-git-validation on your own risk to export regardless."
            )

    polarion_case = None
    if not duplicate:
        polarion_case = get_polarion_case(test.node, project_id)
    summary = tmt.export.nitrate.prepare_extra_summary(test, append_summary, ignore_git_validation)
    assert test.path is not None  # narrow type
    test_path = test.node.root / test.path.unrooted()

    if not polarion_case:
        if create:
            if not project_id:
                raise ConvertError(
                    "Please provide project_id so tmt knows which "
                    "Polarion project to use for this test case."
                )
            if not dry_mode:
                polarion_case = create_polarion_case(
                    summary, project_id=project_id, path=test_path
                )
            else:
                echo(style(f"Test case '{summary}' created.", fg='blue'))
            test._metadata['extra-summary'] = summary
        else:
            raise ConvertError(
                f"Polarion test case id not found for '{test}'. "
                f"(You can use --create option to enforce creating testcases.)"
            )

    # Title
    if not dry_mode:
        assert polarion_case  # Narrow type
        if test.summary is not None and polarion_case.title != test.summary:
            polarion_case.title = test.summary
    # TODO: test.summary may be left unset, i.e. `None` is a possibility here. Shall we print
    # new title then? It may also be `None`...
    if test.summary is not None:
        echo(style('title: ', fg='green') + test.summary)

    # Add id to test
    uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    if not uuid:
        uuid = test.node.get(ID_KEY)
    echo(style(f"Append the ID {uuid}.", fg='green'))
    
    # Store Polarion work item ID in extra-polarion for future lookups
    if not dry_mode and polarion_case:
        assert polarion_case  # Narrow type
        polarion_work_item_id = str(polarion_case.work_item_id)
        with test.node as data:
            data['extra-polarion'] = polarion_work_item_id
        echo(style(f"Stored Polarion work item ID: {polarion_work_item_id}", fg='green'))

    # Description
    description = summary
    if test.description:
        description += ' - ' + test.description
    if test.environment:
        description += '<br/>Environment variables:'
        for key, value in test.environment.items():
            description += f'<br/>{key}={value}'
    if not dry_mode:
        assert polarion_case  # Narrow type
        polarion_case.description = description
    echo(style('description: ', fg='green') + description)

    # Automation
    if test.node.get('extra-task'):
        automation_script = test.node.get('extra-task')
        if not ignore_git_validation and test.fmf_id.url is not None:
            automation_script += f'<br/>{test.fmf_id.url}'
    elif ignore_git_validation:
        automation_script = "local"
    else:
        assert test.fmf_id.url is not None  # narrow type
        automation_script = test.fmf_id.url
    if not dry_mode:
        assert polarion_case  # Narrow type
        polarion_case.caseautomation = 'automated'
        if test.link:
            for link in test.link.get(relation='test-script'):
                if isinstance(link.target, str):
                    automation_script += f'<br/>{link.target}'
                    add_hyperlink(polarion_case, link.target)
        polarion_case.automation_script = automation_script
        # Add hyperlink to the actual test script, not the metadata file
        test_script_link = get_test_script_link(test)
        if test_script_link:
            add_hyperlink(polarion_case, test_script_link)
    echo(style('script: ', fg='green') + automation_script)

    # Components
    if not dry_mode:
        assert polarion_case  # Narrow type
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
        assert polarion_case  # Narrow type
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
        assert polarion_case  # Narrow type
        polarion_case.tags = ' '.join(test.tag)
    echo(style('tags: ', fg='green') + ' '.join(set(test.tag)))

    # Default tester
    if test.contact:
        # Need to pick one value, so picking the first contact
        email_address = email.utils.parseaddr(test.contact[0])[1]
        login_name = email_address[: email_address.find('@')]
        try:
            if not dry_mode:
                assert polarion_case  # Narrow type
                polarion_case.add_assignee(login_name)
            echo(style('default tester: ', fg='green') + login_name)
        except PolarionException as err:
            log.debug(err)

    # Status
    if not dry_mode:
        assert polarion_case  # Narrow type
        if test.enabled:
            polarion_case.status = 'approved'
        else:
            polarion_case.status = 'inactive'
    echo(style('enabled: ', fg='green') + str(test.enabled))

    echo(style("Append the Polarion test case link.", fg='green'))
    if not dry_mode and link_polarion:
        assert polarion_case  # Narrow type
        with test.node as data:
            server_url = str(polarion_case._session._server.url)
            tmt.convert.add_link(
                f'{server_url}{"" if server_url.endswith("/") else "/"}'
                f'#/project/{polarion_case.project_id}/workitem?id='
                f'{polarion_case.work_item_id!s}',
                data,
                system=tmt.convert.SYSTEM_OTHER,
                type_='implements',
            )

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
        assert polarion_case  # Narrow type
        polarion_case.tcmsbug = ', '.join(str(bug_ids))

    # Add TCMS Case ID to Polarion case
    if test.node.get('extra-nitrate') and not dry_mode:
        assert polarion_case  # Narrow type
        tcms_case_id_search = re.search(r'\d+', test.node.get("extra-nitrate"))
        if tcms_case_id_search:
            polarion_case.tcmscaseid = str(int(tcms_case_id_search.group()))

    # Add Requirements to Polarion case
    if not dry_mode:
        assert polarion_case  # Narrow type
        for req in requirements:
            polarion_case.add_linked_item(req, 'verifies')

    # Custom Polarion fields from extra-polarion-* metadata
    if not dry_mode and polarion_case:
        set_polarion_custom_fields(polarion_case, test.node, dry_mode=False)

    # Update Polarion test case
    if not dry_mode:
        assert polarion_case  # Narrow type
        polarion_case.update()
    echo(style(f"Test case '{summary}' successfully exported to Polarion.", fg='magenta'))

    # Optionally link Bugzilla to Polarion case
    if link_bugzilla and bug_ids and not dry_mode:
        assert polarion_case  # Narrow type
        case_id = f"{polarion_case.project_id}/workitem?id={polarion_case.work_item_id!s}"
        tmt.export.bz_set_coverage(bug_ids, case_id, POLARION_TRACKER_ID)
    
    return polarion_case


def get_polarion_feature(
    data: dict[str, Optional[str]],
    preferred_project: Optional[str] = None,
    polarion_feature_id: Optional[str] = None,
) -> Optional[PolarionWorkItem]:
    """
    Get Polarion feature/requirement through couple different methods
    """

    import_polarion()

    assert PolarionWorkItem
    assert PolarionException

    case_id, project_id = find_polarion_case_ids(data, preferred_project, polarion_feature_id)
    if case_id is None or project_id is None:
        return None

    try:
        polarion_feature = PolarionWorkItem(project_id=project_id, work_item_id=case_id)
        echo(style(f"Feature '{polarion_feature.work_item_id!s}' found.", fg='blue'))
        return polarion_feature
    except PolarionException:
        return None


def set_polarion_custom_fields(
    polarion_item: Any,
    node: Any,
    dry_mode: bool = False
) -> None:
    """
    Set custom Polarion fields from FMF metadata
    
    Processes 'extra-polarion-*' fields and maps them to Polarion custom fields.
    Uses the proper CustomField API to set values.
    
    Custom fields discovered in RHELCockpit project:
      - subsystemteam (text)
      - component (text)
      - jiraassignee (text)
      - jirafixversion (text)
    
    For example:
      extra-polarion-subsystemteam: rhel-cockpit
      extra-polarion-component: cockpit
    
    Args:
        polarion_item: Polarion work item (feature or test case)
        node: FMF Tree node
        dry_mode: Whether in dry-run mode
    """
    if dry_mode:
        return
    
    # Get the node data as dictionary
    node_data = node.get()
    
    # Find all extra-polarion-* fields (excluding extra-polarion itself)
    custom_fields = {}
    for key, value in node_data.items():
        if key.startswith('extra-polarion-'):
            # Extract the field name after 'extra-polarion-'
            field_name = key[len('extra-polarion-'):]
            
            # Custom fields in Polarion may use different naming conventions
            # Try both original and snake_case versions
            # Example: 'subsystem-team' could be 'subsystemteam' or 'subsystem_team'
            field_name_clean = field_name.replace('-', '')  # Remove hyphens: subsystem-team -> subsystemteam
            
            custom_fields[field_name_clean] = value
    
    if not custom_fields:
        return
    
    # Import CustomField class
    try:
        from pylero.custom_field import CustomField
    except ImportError:
        log.warning("Could not import CustomField from pylero")
        return
    
    # Set each custom field using the CustomField API
    fields_updated = []
    fields_failed = []
    
    for field_name, value in custom_fields.items():
        try:
            # Set as text/string value (most custom fields are text)
            polarion_item._set_custom_field(field_name, str(value))
            fields_updated.append(field_name)
        except (AttributeError, PolarionException) as exc:
            # Field doesn't exist or permission error
            log.debug(f"Failed to set custom field '{field_name}': {exc}")
            fields_failed.append((field_name, str(exc)))
    
    # Log summary
    if fields_updated:
        log.info(f'Set {len(fields_updated)} custom field(s): {", ".join(fields_updated)}')
    if fields_failed:
        log.warning(f'{len(fields_failed)} field(s) could not be set: {", ".join(f[0] for f in fields_failed)}')


def create_polarion_feature(summary: str, project_id: str, story_text: str) -> PolarionWorkItem:
    """
    Create new polarion feature
    """

    import_polarion()
    
    assert PolarionWorkItem

    # Create the new feature work item
    # In Polarion, features are typically "requirement" work items
    # The create method signature is: create(project_id, wi_type, title, desc, status, **kwargs)
    feature = PolarionWorkItem.create(
        project_id,
        'requirement',  # wi_type: work item type
        summary,        # title
        story_text or summary,  # desc: description
        'open'          # status: initial status
    )
    
    echo(style(f"Feature '{feature.work_item_id}' created.", fg='blue'))
    return feature


def export_story_to_polarion(story: tmt.base.Story) -> None:
    """
    Export fmf story metadata to a Polarion feature/requirement
    """

    import tmt.export.nitrate

    import_polarion()
    
    logger = story._logger

    # Check command line options
    create = story.opt('create')
    project_id = story.opt('project_id')
    polarion_feature_id = story.opt('polarion_feature_id')
    duplicate = story.opt('duplicate')
    export_linked_tests = story.opt('export_linked_tests')
    dry_mode = story.is_dry_run
    link_polarion = story.opt('link_polarion')
    append_summary = story.opt('append-summary')

    polarion_feature = None
    if not duplicate:
        polarion_feature = get_polarion_feature(story.node, project_id, polarion_feature_id)
    
    # Prepare summary
    summary = tmt.export.nitrate.prepare_extra_summary(story, append_summary)

    if not polarion_feature:
        if create:
            if not project_id:
                raise ConvertError(
                    "Please provide project_id so tmt knows which "
                    "Polarion project to use for this feature."
                )
            if not dry_mode:
                polarion_feature = create_polarion_feature(
                    summary, project_id=project_id, story_text=story.story or ""
                )
            else:
                echo(style(f"Feature '{summary}' created.", fg='blue'))
            story._metadata['extra-summary'] = summary
        else:
            raise ConvertError(
                f"Polarion feature id not found for '{story}'. "
                f"(You can use --create option to enforce creating features.)"
            )

    # Title
    if not dry_mode:
        assert polarion_feature  # Narrow type
        if story.title is not None and polarion_feature.title != story.title:
            polarion_feature.title = story.title
        elif story.summary is not None and polarion_feature.title != story.summary:
            polarion_feature.title = story.summary
    title = story.title or story.summary
    if title:
        logger.debug(f"title: {title}")

    # Add id to story
    uuid = add_uuid_if_not_defined(story.node, dry_mode, story._logger)
    if not uuid:
        uuid = story.node.get(ID_KEY)
    logger.debug(f"Appended ID: {uuid}")
    
    # Store Polarion work item ID in extra-polarion for future lookups
    if not dry_mode and polarion_feature:
        assert polarion_feature  # Narrow type
        polarion_work_item_id = str(polarion_feature.work_item_id)
        with story.node as data:
            data['extra-polarion'] = polarion_work_item_id
        logger.info(f"Stored Polarion work item ID: {polarion_work_item_id}")

    # Description (story text + description)
    description = ""
    if story.story:
        description = story.story
    if story.description:
        if description:
            description += '<br/><br/>'
        description += story.description
    if story.example:
        description += '<br/><br/>Examples:<br/>'
        for example in story.example:
            description += f'<br/>- {example}'
    if not dry_mode:
        assert polarion_feature  # Narrow type
        polarion_feature.description = description
    logger.debug(f"description: {description[:100]}{'...' if len(description) > 100 else ''}")

    # Priority
    if story.priority:
        priority_map = {
            'must have': 'high',
            'should have': 'medium',
            'could have': 'low',
            'will not have': 'low'
        }
        if not dry_mode:
            assert polarion_feature  # Narrow type
            try:
                polarion_feature.priority = priority_map.get(str(story.priority), 'medium')
            except (AttributeError, PolarionException) as exc:
                logger.debug(f"Failed to set priority: {exc}")
        logger.debug(f"priority: {story.priority}")

    # Tags
    if story.tag:
        story.tag.append('fmf-export')
        if not dry_mode:
            assert polarion_feature  # Narrow type
            try:
                polarion_feature.tags = ' '.join(story.tag)
            except (AttributeError, PolarionException) as exc:
                logger.debug(f"Failed to set tags: {exc}")
        logger.debug(f"tags: {' '.join(set(story.tag))}")

    # Contact
    if story.contact:
        email_address = email.utils.parseaddr(story.contact[0])[1]
        login_name = email_address[: email_address.find('@')]
        try:
            if not dry_mode:
                assert polarion_feature  # Narrow type
                polarion_feature.add_assignee(login_name)
            logger.debug(f"assignee: {login_name}")
        except (AttributeError, PolarionException) as err:
            logger.debug(f"Failed to set assignee: {err}")

    # Status
    if not dry_mode:
        assert polarion_feature  # Narrow type
        try:
            if story.enabled:
                polarion_feature.status = 'approved'
            else:
                polarion_feature.status = 'inactive'
        except (AttributeError, PolarionException) as exc:
            logger.debug(f"Failed to set status: {exc}")
    logger.debug(f"enabled: {story.enabled}")

    # Custom Polarion fields from extra-polarion-* metadata
    if not dry_mode and polarion_feature:
        logger.info('Setting custom Polarion fields')
        set_polarion_custom_fields(polarion_feature, story.node, dry_mode=False)

    # Step 1: Export linked test cases first (if enabled)
    # This ensures all test cases exist in Polarion before we link them
    test_case_map = {}  # Map: test path -> Polarion work item ID
    
    if story.verified and export_linked_tests:
        logger.info('Exporting linked test cases to Polarion')
        
        for link in story.verified:
            # Check if the link is a Polarion URL
            if isinstance(link.target, str):
                polarion_url_search = re.search(RE_POLARION_URL, link.target)
                if polarion_url_search:
                    # Already a Polarion work item ID, save it
                    test_case_map[link.target] = polarion_url_search.group(1)
                    continue  # Skip FMF lookup for Polarion URLs
                
                # Not a Polarion URL, treat as FMF test path
                if story.tree:
                    try:
                        tests = story.tree.tests(names=[link.target])
                        if tests:
                            test = tests[0]
                            # Try to find the Polarion test case
                            polarion_test_case = get_polarion_case(test.node, project_id)
                            
                            # If test case not found in Polarion, export it first
                            if not polarion_test_case:
                                logger.debug(f'Test {link.target} not found in Polarion')
                                if create:
                                    logger.info(f'Creating test case {link.target} in Polarion')
                                    try:
                                        # Reuse existing export_to_polarion() function with options
                                        test_options = {
                                            'create': True,
                                            'project_id': project_id,
                                            'dry_mode': dry_mode,
                                            'duplicate': False,
                                            'link_polarion': False,
                                            'append-summary': append_summary,
                                        }
                                        polarion_test_case = export_to_polarion(test, options=test_options)
                                        if polarion_test_case:
                                            logger.info(f'Test case exported: {polarion_test_case.work_item_id}')
                                    except Exception as export_err:
                                        logger.debug(f"Failed to export test case {link.target}: {export_err}")
                                        logger.warning(f'Failed to export test case: {export_err}')
                            else:
                                logger.debug(f'Test case found: {polarion_test_case.work_item_id}')
                            
                            # Save the mapping if we have a Polarion test case
                            if polarion_test_case:
                                test_case_map[link.target] = str(polarion_test_case.work_item_id)
                        else:
                            logger.warning(f'Test {link.target} not found in fmf tree')
                    except Exception as err:
                        logger.debug(f"Failed to process test {link.target}: {err}")
                        logger.warning(f'Failed to process test {link.target}: {err}')
            
            # Handle FmfId objects
            elif isinstance(link.target, tmt.base.FmfId):
                if story.tree:
                    try:
                        tests = story.tree.tests(names=[link.target.name])
                        if tests:
                            test = tests[0]
                            polarion_test_case = get_polarion_case(test.node, project_id)
                            
                            if not polarion_test_case and create:
                                logger.info(f'Creating test case {link.target.name} in Polarion')
                                try:
                                    # Reuse existing export_to_polarion() function with options
                                    test_options = {
                                        'create': True,
                                        'project_id': project_id,
                                        'dry_mode': dry_mode,
                                        'duplicate': False,
                                        'link_polarion': False,
                                        'append-summary': append_summary,
                                    }
                                    polarion_test_case = export_to_polarion(test, options=test_options)
                                    if polarion_test_case:
                                        logger.info(f'Test case exported: {polarion_test_case.work_item_id}')
                                except Exception as export_err:
                                    logger.debug(f"Failed to export test case: {export_err}")
                                    logger.warning(f'Failed to export test case: {export_err}')
                            
                            if polarion_test_case:
                                test_case_map[link.target.name] = str(polarion_test_case.work_item_id)
                    except Exception as err:
                        logger.debug(f"Failed to process test: {err}")
    
    # Step 2: Link test cases to story
    # Now that all test cases are exported, we can link them
    if story.verified:
        logger.info('Linking test cases to feature')
        
        for link in story.verified:
            # Get the Polarion work item ID from our map
            polarion_id = None
            test_path = None
            
            if isinstance(link.target, str):
                test_path = link.target
                polarion_id = test_case_map.get(link.target)
            elif isinstance(link.target, tmt.base.FmfId):
                test_path = link.target.name
                polarion_id = test_case_map.get(link.target.name)
            
            if polarion_id:
                try:
                    if not dry_mode:
                        assert polarion_feature  # Narrow type
                        # Use "verifies" role - the test case verifies the requirement
                        polarion_feature.add_linked_item(polarion_id, 'verifies')
                    logger.info(f'Linked: {polarion_id} (verifies)')
                except (AttributeError, PolarionException) as err:
                    logger.debug(f"Failed to link test case {polarion_id}: {err}")
                    logger.warning(f'Failed to link: {polarion_id}')
                except Exception as err:
                    logger.debug(f"Unexpected error linking test case {polarion_id}: {err}")
                    logger.warning(f'Failed to link: {polarion_id}')
            elif export_linked_tests:
                # We tried to export but failed
                logger.warning(f'Skipping link for {test_path} (test case not available)')

    # Add web link
    if not dry_mode and polarion_feature:
        web_link = story.web_link()
        if web_link:
            try:
                add_hyperlink(polarion_feature, web_link)
            except (AttributeError, PolarionException) as err:
                logger.debug(f"Failed to add hyperlink: {err}")

    if not dry_mode and link_polarion:
        assert polarion_feature  # Narrow type
        with story.node as data:
            server_url = str(polarion_feature._session._server.url)
            tmt.convert.add_link(
                f'{server_url}{"" if server_url.endswith("/") else "/"}'
                f'#/project/{polarion_feature.project_id}/workitem?id='
                f'{polarion_feature.work_item_id!s}',
                data,
                system=tmt.convert.SYSTEM_OTHER,
                type_='implements',
            )
        logger.debug("Added Polarion feature link to fmf metadata")

    # Update Polarion feature
    if not dry_mode:
        assert polarion_feature  # Narrow type
        try:
            polarion_feature.update()
        except (AttributeError, PolarionException) as exc:
            logger.debug(f"Failed to update feature: {exc}")
            raise ConvertError(f"Failed to update Polarion feature: {exc}") from exc
    
    # Final success message - keep this as user-facing output
    echo(style(f"Story '{summary}' successfully exported to Polarion.", fg='magenta'))


@tmt.base.Test.provides_export('polarion')
@tmt.base.Story.provides_export('polarion')
class PolarionExporter(tmt.export.ExportPlugin):
    @classmethod
    def export_test_collection(
        cls,
        tests: list[tmt.base.Test],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        for test in tests:
            export_to_polarion(test)

        return ''

    @classmethod
    def export_story_collection(
        cls,
        stories: list[tmt.base.Story],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        for story in stories:
            export_story_to_polarion(story)

        return ''

    @classmethod
    def export_fmfid_collection(cls, fmf_ids: list['tmt.base.FmfId'], **kwargs: Any) -> str:
        raise NotImplementedError

    @classmethod
    def export_plan_collection(
        cls,
        plans: list['tmt.base.Plan'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError
