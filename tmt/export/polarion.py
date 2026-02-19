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


def get_test_script_link(test: tmt.base.Test) -> Optional[str]:
    """
    Generate a web link to the actual test script (not the metadata file)
    
    Returns a URL pointing to the test script (e.g., test.sh) instead of
    the metadata file (e.g., main.fmf) which is what test.web_link() returns.
    
    Properly handles relative paths like:
    - ./test.sh → same directory as FMF file
    - ../test.sh → one directory up
    - ../../runtest.sh → two directories up
    """
    if not test.test or not test.fmf_id.url:
        return None
    
    # Get the actual metadata file path from node.sources (last source is most specific)
    if not test.node.sources:
        return None
    
    metadata_file_path = Path(test.node.sources[-1])
    
    # Ensure metadata_file_path is absolute by resolving it relative to FMF root
    # node.sources can contain relative paths, so we need to make them absolute
    if not metadata_file_path.is_absolute():
        fmf_root = Path(test.node.root)
        metadata_file_path = (fmf_root / metadata_file_path).resolve()
    else:
        metadata_file_path = metadata_file_path.resolve()
    
    # Extract the test script filename from the test field
    # test.test can be a command with arguments like "./test.sh a b c --abc"
    # We need just the command name, not the arguments
    test_command = str(test.test).split(maxsplit=1)[0]  # Get first part (command)
    
    # Resolve the test script path relative to the metadata file directory
    # This handles ./, ../, ../../, etc. properly
    # Now metadata_file_path is guaranteed to be absolute, so this resolution is safe
    metadata_dir = metadata_file_path.parent
    test_script_path = (metadata_dir / test_command).resolve()
    
    # Check if the resolved test script exists locally
    if not test_script_path.exists():
        # If file doesn't exist, fall back to original web_link behavior
        return test.web_link()
    
    # Get the actual git repository root (not FMF root, which may be nested)
    # FMF root is where .fmf/ directory is, git root is where .git/ directory is
    git_root_path = tmt.utils.git.git_root(fmf_root=Path(test.node.root), logger=test._logger)
    if not git_root_path:
        # Not in a git repository
        return test.web_link()
    
    # Calculate the relative path from git root to the test script
    try:
        relative_test_path = test_script_path.relative_to(git_root_path)
    except ValueError:
        # Test script is outside the git repository
        return test.web_link()
    
    # Add fmf path if the tree is nested deeper in the git repo
    if test.fmf_id.path:
        relative_test_path = test.fmf_id.path / relative_test_path
    
    # Construct the web URL using the git utilities
    return tmt.utils.git.web_git_url(test.fmf_id.url, test.fmf_id.ref, Path('/') / relative_test_path)


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
    2. TMT ID mapped to Polarion's tmtid field
    3. Legacy extra-polarion field (for backward compatibility)
    """

    assert PolarionWorkItem

    case_id = None
    project_id = None
    wanted_fields = ['work_item_id', 'project_id', 'status']

    # Search for Polarion case ID directly (explicit user override)
    if polarion_case_id:
        query_result = PolarionWorkItem.query(f'id:{polarion_case_id}', fields=wanted_fields)
        case_id, project_id = get_polarion_ids(query_result, preferred_project)

    # Search by TMT ID (mapped to Polarion's tmtid custom field)
    if not project_id:
        tmt_id = data.get(ID_KEY)
        if tmt_id:
            # Try multiple query formats for custom field - format varies by Polarion version
            log.debug(f"Searching for work item with tmtid={tmt_id}")
            for query_format in [f'tmtid:{tmt_id}', f'customFields.tmtid:{tmt_id}']:
                try:
                    query_result = PolarionWorkItem.query(query_format, fields=wanted_fields)
                    case_id, project_id = get_polarion_ids(query_result, preferred_project)
                    if case_id:
                        log.debug(f"Found work item via query '{query_format}': {case_id}")
                        break
                except PolarionException as err:
                    log.debug(f"Query '{query_format}' failed: {err}")
                    continue

    # Fallback: Search by legacy extra-polarion field (backward compatibility)
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

    # Add TMT ID to test and set it in Polarion's tmtid field
    uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    if not uuid:
        uuid = test.node.get(ID_KEY)
    log.debug(f"Appended TMT ID: {uuid}")

    # Set TMT ID in Polarion's tmtid custom field for future lookups
    if not dry_mode and polarion_case and uuid:
        assert polarion_case  # Narrow type
        tmtid_set = False
        try:
            polarion_case._set_custom_field('tmtid', uuid)
            log.debug(f"Set tmtid: {uuid}")
            tmtid_set = True
        except (AttributeError, PolarionException) as err:
            log.debug(f"tmtid field error: {err}")

        # Fallback: Store Polarion work item ID in extra-polarion if tmtid failed
        if not tmtid_set:
            polarion_work_item_id = str(polarion_case.work_item_id)
            with test.node as data:
                data['extra-polarion'] = polarion_work_item_id
            echo(style(f"tmtid field not available, stored {polarion_work_item_id} in extra-polarion", fg='yellow'))

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

    # If data is a Tree node, convert to dictionary
    if hasattr(data, 'get'):
        data = data.get()
    
    # Log what we're searching for
    tmt_id = data.get(ID_KEY)
    extra_polarion = data.get('extra-polarion')
    log.debug(f"Searching for feature - TMT ID: {tmt_id}, extra-polarion: {extra_polarion}, explicit ID: {polarion_feature_id}")
    
    case_id, project_id = find_polarion_case_ids(data, preferred_project, polarion_feature_id)
    if case_id is None or project_id is None:
        log.debug("No existing feature found in Polarion")
        return None

    try:
        polarion_feature = PolarionWorkItem(project_id=project_id, work_item_id=case_id)
        echo(style(f"Feature '{polarion_feature.work_item_id!s}' found.", fg='blue'))
        return polarion_feature
    except PolarionException as err:
        log.debug(f"Failed to load feature {case_id}: {err}")
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


def _generate_story_description_html(story: tmt.base.Story) -> str:
    """
    Generate HTML description for a Polarion story/feature
    
    Creates a formatted HTML description including:
    - TMT autogeneration header with link to metadata
    - Story text converted from Markdown
    - Description converted from Markdown
    - Examples list
    
    Args:
        story: The story object to generate description for
        
    Returns:
        HTML-formatted description string
    """
    description = ""
    web_link = story.web_link()
    
    # Add header indicating TMT autogeneration with link to metadata
    if web_link:
        # Use the actual origin repository URL without any hardcoded modifications
        description = (
            f'<p><em>ℹ️ This feature is autogenerated by TMT from metadata: '
            f'<a href="{web_link}">{story.name}</a></em></p>'
            f'<hr/>'
        )
    
    # Markdown extensions for better formatting in Polarion
    markdown_extensions = [
        'extra',           # Adds tables, fenced code blocks, etc.
        'nl2br',           # Converts newlines to <br/>
        'sane_lists',      # Better list handling
    ]
    
    # Add story text
    if story.story:
        description += tmt.utils.markdown_to_html(story.story, extensions=markdown_extensions)
    
    # Add description
    if story.description:
        if description:
            description += '<br/><br/>'
        description += tmt.utils.markdown_to_html(story.description, extensions=markdown_extensions)
    
    # Add examples
    if story.example:
        description += '<br/><br/><strong>Examples:</strong><br/>'
        for example in story.example:
            # Examples can also contain markdown
            example_html = tmt.utils.markdown_to_html(example, extensions=markdown_extensions)
            description += f'<br/>• {example_html}'
    
    return description


def _set_polarion_feature_fields(
    polarion_feature: PolarionWorkItem,
    story: tmt.base.Story,
    dry_mode: bool,
    logger: tmt.log.Logger
) -> None:
    """
    Set all Polarion feature/requirement fields from story metadata
    
    Updates the Polarion work item with metadata from the TMT story including:
    - Title
    - Description (HTML formatted)
    - Priority
    - Tags
    - Contact/Assignee
    - Status
    - Custom fields
    
    Args:
        polarion_feature: The Polarion work item to update
        story: The TMT story object containing metadata
        dry_mode: Whether in dry-run mode (don't actually update Polarion)
        logger: Logger instance for debugging
    """
    # Prepare all values for logging/dry-run display
    title = story.title or story.summary
    description = _generate_story_description_html(story)
    priority_map = {
        'must have': 'high',
        'should have': 'medium',
        'could have': 'low',
        'will not have': 'low'
    }
    priority_value = priority_map.get(str(story.priority), 'medium') if story.priority else None
    
    # Prepare tags
    if story.tag:
        story.tag.append('fmf-export')
    tags_value = ' '.join(story.tag) if story.tag else None
    
    # Prepare contact/assignee
    login_name = None
    if story.contact:
        email_address = email.utils.parseaddr(story.contact[0])[1]
        login_name = email_address[: email_address.find('@')]
    
    # Prepare status
    status_value = 'approved' if story.enabled else 'inactive'
    
    # Log what would be set
    if title:
        logger.debug(f"title: {title}")
    logger.debug(f"description: {description[:100]}{'...' if len(description) > 100 else ''}")
    if priority_value:
        logger.debug(f"priority: {story.priority}")
    if tags_value:
        logger.debug(f"tags: {' '.join(set(story.tag))}")
    if login_name:
        logger.debug(f"assignee: {login_name}")
    logger.debug(f"enabled: {story.enabled}")
    
    # Early return if dry mode - don't actually update Polarion
    if dry_mode:
        return
    
    # Apply all changes to Polarion (only if not dry mode)
    try:
        # Title
        if story.title is not None and polarion_feature.title != story.title:
            polarion_feature.title = story.title
        elif story.summary is not None and polarion_feature.title != story.summary:
            polarion_feature.title = story.summary
        
        # Description
        polarion_feature.description = description
        
        # Priority
        if priority_value:
            try:
                polarion_feature.priority = priority_value
            except (AttributeError, PolarionException) as exc:
                logger.debug(f"Failed to set priority: {exc}")
        
        # Tags
        if tags_value:
            try:
                polarion_feature.tags = tags_value
            except (AttributeError, PolarionException) as exc:
                logger.debug(f"Failed to set tags: {exc}")
        
        # Contact/Assignee
        if login_name:
            try:
                polarion_feature.add_assignee(login_name)
            except (AttributeError, PolarionException) as err:
                logger.debug(f"Failed to set assignee: {err}")
        
        # Status
        try:
            polarion_feature.status = status_value
        except (AttributeError, PolarionException) as exc:
            logger.debug(f"Failed to set status: {exc}")
        
        # Custom Polarion fields from extra-polarion-* metadata
        logger.debug('Setting custom Polarion fields')
        set_polarion_custom_fields(polarion_feature, story.node, dry_mode=False)
        
    except Exception as exc:
        logger.debug(f"Failed to set some Polarion fields: {exc}")


def _export_single_test_case_for_story(
    test_name: str,
    story: tmt.base.Story,
    project_id: str,
    create: bool,
    dry_mode: bool,
    append_summary: Optional[str],
    logger: tmt.log.Logger
) -> Optional[str]:
    """
    Helper function to export a single test case to Polarion.
    
    Returns the Polarion work item ID if successful, None otherwise.
    
    Note: Git validation is skipped for auto-exported tests since they are
    being exported as part of story export, not as a standalone operation.
    """
    if not story.tree:
        return None
    
    try:
        tests = story.tree.tests(names=[test_name])
        if not tests:
            logger.warning(f'Test {test_name} not found in fmf tree')
            return None
        
        test = tests[0]
        polarion_test_case = get_polarion_case(test.node, project_id)
        
        # If test case not found in Polarion, export it first
        if not polarion_test_case:
            logger.debug(f'Test {test_name} not found in Polarion')
            if create:
                logger.debug(f'Creating test case {test_name} in Polarion')
                try:
                    # Skip git validation for auto-exported tests from story context
                    # This is a convenience feature, so we don't want to fail on git issues
                    test_options = {
                        'create': True,
                        'project_id': project_id,
                        'dry_mode': dry_mode,
                        'duplicate': False,
                        'link_polarion': False,
                        'append-summary': append_summary,
                        'ignore_git_validation': True,
                    }
                    polarion_test_case = export_to_polarion(test, options=test_options)
                    if polarion_test_case:
                        logger.debug(f'Test case exported: {polarion_test_case.work_item_id}')
                except Exception as export_err:
                    logger.warning(f'Failed to export test case {test_name}: {export_err}')
        else:
            logger.debug(f'Test case found: {polarion_test_case.work_item_id}')
        
        # Return the Polarion work item ID if we have one
        return str(polarion_test_case.work_item_id) if polarion_test_case else None
        
    except Exception as err:
        logger.warning(f'Failed to process test {test_name}: {err}')
        return None


def _export_and_link_story_tests(
    story: tmt.base.Story,
    polarion_feature: Optional[PolarionWorkItem],
    project_id: Optional[str],
    create: bool,
    export_linked_tests: bool,
    dry_mode: bool,
    append_summary: Optional[str],
    logger: tmt.log.Logger
) -> None:
    """
    Export linked test cases to Polarion and link them to the story feature
    
    Two-step process:
    1. Export all linked tests to Polarion (creating them if needed)
    2. Link the exported test cases to the Polarion feature
    
    Args:
        story: The TMT story object containing test links
        polarion_feature: The Polarion feature to link tests to
        project_id: Polarion project ID
        create: Whether to create missing test cases
        export_linked_tests: Whether to export linked tests at all
        dry_mode: Whether in dry-run mode
        append_summary: Text to append to test summaries
        logger: Logger instance for debugging
    """
    if not story.verified:
        return
    
    # Step 1: Export linked test cases first (if enabled)
    # This ensures all test cases exist in Polarion before we link them
    test_case_map = {}  # Map: test path -> Polarion work item ID
    
    if export_linked_tests:
        logger.debug('Exporting linked test cases to Polarion')
        
        for link in story.verified:
            # Check if the link is a Polarion URL
            if isinstance(link.target, str):
                polarion_url_search = re.search(RE_POLARION_URL, link.target)
                if polarion_url_search:
                    # Already a Polarion work item ID, save it
                    test_case_map[link.target] = polarion_url_search.group(1)
                    continue  # Skip FMF lookup for Polarion URLs
                
                # Not a Polarion URL, treat as FMF test path
                polarion_id = _export_single_test_case_for_story(
                    link.target, story, project_id, create, dry_mode, append_summary, logger
                )
                if polarion_id:
                    test_case_map[link.target] = polarion_id
            
            # Handle FmfId objects
            elif isinstance(link.target, tmt.base.FmfId):
                polarion_id = _export_single_test_case_for_story(
                    link.target.name, story, project_id, create, dry_mode, append_summary, logger
                )
                if polarion_id:
                    test_case_map[link.target.name] = polarion_id
    
    # Step 2: Link test cases to story
    # Now that all test cases are exported, we can link them
    logger.debug('Linking test cases to feature')
    
    # Collect all links to be made (test case ID + test path for logging)
    links_to_create = []
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
            links_to_create.append((polarion_id, test_path))
        elif export_linked_tests:
            # We tried to export but failed
            logger.warning(f'Skipping link for {test_path} (test case not available)')
    
    # Apply all links FROM test cases TO the feature (only if not dry mode)
    # Per pylero documentation: links are added to the "child" object (test case)
    # with the 'verifies' role pointing to the requirement/feature
    if not dry_mode and polarion_feature and links_to_create:
        feature_id = str(polarion_feature.work_item_id)
        for polarion_test_id, test_path in links_to_create:
            try:
                # Load test case and add 'verifies' link to the feature
                test_case = PolarionTestCase(
                    project_id=polarion_feature.project_id,
                    work_item_id=polarion_test_id
                )
                test_case.add_linked_item(feature_id, 'verifies')
                logger.debug(f'Linked: test {polarion_test_id} verifies feature {feature_id}')
            except Exception as err:
                logger.warning(f'Failed to link test {polarion_test_id}: {err}')


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

    # Add TMT ID to story and set it in Polarion's tmtid field
    uuid = add_uuid_if_not_defined(story.node, dry_mode, story._logger)
    if not uuid:
        uuid = story.node.get(ID_KEY)
    logger.debug(f"Appended ID: {uuid}")

    # Store Polarion work item ID in extra-polarion (features don't have tmtid field)
    if not dry_mode and polarion_feature:
        polarion_work_item_id = str(polarion_feature.work_item_id)
        with story.node as data:
            data['extra-polarion'] = polarion_work_item_id
        logger.debug(f"Stored Polarion work item ID in extra-polarion: {polarion_work_item_id}")

    # Set all Polarion feature fields (title, description, priority, tags, etc.)
    if polarion_feature:
        _set_polarion_feature_fields(polarion_feature, story, dry_mode, logger)

    # Export and link test cases to the story
    _export_and_link_story_tests(
        story, polarion_feature, project_id, create,
        export_linked_tests, dry_mode, append_summary, logger
    )

    # Early return if dry mode - remaining operations modify metadata and Polarion
    if dry_mode:
        echo(style(f"Story '{summary}' would be exported to Polarion (dry mode).", fg='magenta'))
        return
    
    # All operations below only execute when not in dry mode
    assert polarion_feature is not None  # Should exist if not dry mode

    # Add web link to Polarion feature
    web_link = story.web_link()
    if web_link:
        try:
            add_hyperlink(polarion_feature, web_link)
        except (AttributeError, PolarionException) as err:
            logger.debug(f"Failed to add hyperlink: {err}")

    # Add Polarion link back to FMF metadata
    if link_polarion:
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

    # Update Polarion feature with all changes
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
