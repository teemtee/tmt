import urllib.parse
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import fmf.utils

import tmt.base
import tmt.log
import tmt.utils
from tmt._compat.pathlib import Path
from tmt.plugins import ModuleImporter

if TYPE_CHECKING:
    import jira


import_jira: ModuleImporter['jira'] = ModuleImporter(  # type: ignore[valid-type]
    'jira',
    tmt.utils.ReportError,
    "Install 'tmt+link-jira' to use the Jira linking.")


def jira_link(
        nodes: Sequence[Union['tmt.base.Test', 'tmt.base.Plan', 'tmt.base.Story']],
        links: 'tmt.base.Links',
        logger: tmt.log.Logger,
        separate: bool = False) -> None:
    """ Link the object to Jira issue and create the URL to tmt web service """
    jira_module = import_jira(logger)

    def create_url_params(tmt_object: tmt.base.Core) -> dict[str, Any]:
        tmt_type = tmt_object.__class__.__name__.lower()
        fmf_id = tmt_object.fmf_id

        url_params: dict[str, Any] = {
            'format': 'html',
            f'{tmt_type}-url': fmf_id.url,
            f'{tmt_type}-name': fmf_id.name
            }

        if fmf_id.path and isinstance(fmf_id.git_root, Path):
            fmf_path = fmf_id.path.relative_to(fmf_id.git_root).resolve().as_posix()
            fmf_path = fmf_path.removeprefix(fmf_id.git_root.as_posix())
            url_params[f'{tmt_type}-path'] = fmf_path.lstrip('/')

        if fmf_id.ref:
            url_params[f'{tmt_type}-ref'] = fmf_id.ref

        return url_params

    def create_url(baseurl: str, url_params: dict[str, str]) -> str:
        return urllib.parse.urljoin(baseurl, '?' + urllib.parse.urlencode(url_params))

    # Setup config tree, exit if config is missing
    try:
        config_tree = tmt.utils.Config()
        linking_node = cast(Optional[fmf.Tree], config_tree.fmf_tree.find('/user/linking'))
    except tmt.utils.MetadataError:
        return

    if not linking_node:
        # Linking is not setup in config, therefore user does not want to use linking
        return

    logger.print(
        f'Linking {fmf.utils.listed([type(node).__name__.lower() for node in nodes])}'
        f' to Jira issue.')

    issue_trackers: Any = linking_node.data.get('issue-tracker')

    if not issue_trackers:
        # Incorrectly setup config - wrong keyword
        raise tmt.utils.GeneralError("Invalid config!")

    if not isinstance(issue_trackers[0], dict):
        # Incorrectly setup config - configuration empty
        raise tmt.utils.GeneralError("Invalid config!")

    linking_config = cast(list[dict[str, Any]], issue_trackers)[0]

    verifies = links.get('verifies')[0]
    target = verifies.to_dict()['target']
    # Parse the target url
    issue_id = target.split('/')[-1]
    # ignore[attr-defined]: it is defined, but mypy seems to fail
    # detecting it correctly.
    jira = jira_module.JIRA(  # type: ignore[attr-defined]
        server=linking_config['url'],
        token_auth=linking_config['token'])
    link_object: dict[str, str] = {}
    service_url: dict[str, str] = {}
    for node in nodes:
        # Try to add the link relation to object's data if it is not already there
        #
        # cast & ignore: _data is basically a container with test/plan/story
        # metadata. As such, it has a lot of keys and values of
        # various data types.
        with node.node as _data:  # type: ignore[reportUnknownVariableType,unused-ignore]
            data = cast(dict[str, Any], _data)

            link_relation = {"verifies": target}
            if 'link' in data:
                if link_relation not in data['link']:
                    logger.print('Adding linking to the metadata.')
                    data['link'].append(link_relation)
                else:
                    logger.print('Linking already exists in the object data, skipping this step.')
            else:
                logger.print('Adding linking to the metadata.')
                data['link'] = [link_relation]
        # Single object in list of nodes = creating new object
        # or linking multiple existing separately
        if len(nodes) == 1 or (len(nodes) > 1 and separate):
            service_url = create_url_params(tmt_object=node)
            link_object = {
                "url": create_url(linking_config["tmt-web-url"], service_url),
                "title": f'[tmt_web] Metadata of the {type(node).__name__.lower()}'
                f' covering this issue'}
            jira.add_simple_link(issue_id, link_object)
            logger.print(f'Link added to issue {target}.')
        if len(nodes) > 1 and not separate:
            url_part = create_url_params(tmt_object=node)
            service_url.update(url_part)
            link_object = {
                "url": create_url(linking_config["tmt-web-url"], service_url),
                "title": f'[tmt_web] Metadata of the'
                f' {fmf.utils.listed([type(node).__name__.lower() for node in nodes])}'
                f' covering this issue'}
    if len(nodes) > 1 and not separate:
        # Send request to JIRA when len(nodes) > 1 and not separate, after all nodes were processed
        jira.add_simple_link(issue_id, link_object)
        logger.print(f'Link added to issue {target}.')
