import urllib.parse
from collections.abc import Sequence
from typing import Any, Union

import fmf.utils

import tmt.base
import tmt.log
import tmt.utils
from tmt._compat.pathlib import Path
from tmt.plugins import ModuleImporter

import_jira: ModuleImporter['jira'] = ModuleImporter(  # type: ignore[unused-ignore]
    'jira',
    tmt.utils.ReportError,
    "Install 'tmt+link-jira' to use the Jira linking.",
    tmt.log.Logger.get_bootstrap_logger())


def jira_link(
        nodes: Sequence[Union['tmt.base.Test', 'tmt.base.Plan', 'tmt.base.Story']],
        links: 'tmt.base.Links',
        logger: tmt.log.Logger,
        separate: bool = False) -> None:
    """ Link the object to Jira issue and create the URL to tmt web service """
    jira_module = import_jira()

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

    logger.print(
        f'Linking {fmf.utils.listed([type(node).__name__.lower() for node in nodes])}'
        f' to Jira issue.')

    # Setup config tree
    config_tree = tmt.utils.Config()
    # Linking is not setup in config, therefore user does not want to use linking
    linking_node = config_tree.fmf_tree.find('/user/linking')
    if not linking_node and linking_node.data.get('linking') is None:
        return
    linking_config = linking_node.data.get('issue-tracker')[0]
    verifies = links.get('verifies')[0]
    target = verifies.to_dict()['target']
    # Parse the target url
    issue_id = target.split('/')[-1]
    jira = jira_module.JIRA(server=linking_config['url'], token_auth=linking_config['token'])
    link_object: dict[str, str] = {}
    service_url: dict[str, str] = {}
    for node in nodes:
        # Try to add the link relation to object's data if it is not already there
        with node.node as data:
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
