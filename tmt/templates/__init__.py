from typing import Any, Optional

import tmt
import tmt.utils
from tmt.utils import Path, cached_property

DEFAULT_CUSTOM_TEMPLATES_PATH = tmt.utils.Config().path / 'templates'
DEFAULT_PLAN_NAME = "/default/plan"
INIT_TEMPLATES = ['mini', 'base', 'full']
TEMPLATE_FILE_SUFFIX = '.j2'
TEMPLATE_TYPES = ['default', 'story', 'plan', 'test', 'script']

# TemplatesType is a dictionary of template types and their paths.
# It follows the following structure: {template_type: {template_name: template_path}}
# e.g. {'story': {'mini': Path('templates/story/mini.j2')}, ...}
TemplatesType = dict[str, dict[str, Path]]


def _combine(default: TemplatesType, custom: TemplatesType) -> TemplatesType:
    """
    Combines default templates and custom templates.
    Custom templates have priority and potentially override default templates.
    """
    result: TemplatesType = {}
    for key in default:
        result[key] = {**default[key], **custom.get(key, {})}
    return result


def _get_template_file_paths(path: Path) -> dict[str, Path]:
    """
    Get a dictionary of template names and their file paths.
    :param path: Path to the directory to search for templates.
    """
    return {
        file.name.removesuffix(TEMPLATE_FILE_SUFFIX): file for file in path.iterdir()
        if file.is_file() and file.suffix == TEMPLATE_FILE_SUFFIX
        }


def _get_templates(root_dir: Path) -> TemplatesType:
    """
    Get all templates in given root directory.
    :param root_dir: Path to the directory to search for templates.
    """
    templates: TemplatesType = {}
    for template_type in TEMPLATE_TYPES:
        templates_dir = root_dir / template_type
        if templates_dir.exists() and templates_dir.is_dir():
            template_files = _get_template_file_paths(templates_dir)
            if template_files:
                templates[template_type] = template_files
    return templates


def _append_newline_if_missing(input: str) -> str:
    """ Append newline to the input if it doesn't end with one. """
    return input if input.endswith('\n') else input + '\n'


class TemplateManager:
    """
    Template manager class.

    It provides methods for rendering templates during story, plan or test creation.
    """

    def __init__(self, custom_template_path: Optional[Path] = None):
        self.custom_template_path = custom_template_path or DEFAULT_CUSTOM_TEMPLATES_PATH
        self._init_custom_templates_folder()
        self._environment = tmt.utils.default_template_environment()

    @cached_property
    def templates(self) -> TemplatesType:
        """ Return all available templates (default and optional). """
        return _combine(self.default_templates, self.custom_templates)

    @cached_property
    def default_templates(self) -> TemplatesType:
        """ Return all default templates. """
        templates_dir = tmt.utils.resource_files('templates/')
        templates = _get_templates(templates_dir)
        if not templates:
            raise tmt.utils.GeneralError(f"Could not find default templates in '{templates_dir}'.")
        return templates

    @cached_property
    def custom_templates(self) -> TemplatesType:
        """ Return all custom templates. """
        return _get_templates(self.custom_template_path)

    def render_default_plan(self) -> str:
        """ Return default plan template. """
        try:
            path = self.default_templates['default']['plan']
        except KeyError:
            raise tmt.utils.GeneralError("Default plan template not found.")

        return _append_newline_if_missing(self.render_file(path, plan_name=DEFAULT_PLAN_NAME))

    def render_from_url(self, url: str, **variables: Any) -> str:
        """
        Render template from given URL.
        :param url: URL to the template file.
        :param variables: variables to be passed to the template.
        """
        template = tmt.utils.get_url_content(url)
        template = tmt.utils.render_template(
            template, None, self._environment, **variables)
        return _append_newline_if_missing(template)

    def render_file(self, path: Path, **variables: Any) -> str:
        """
        Render template from given file path.
        :param path: path to the template file.
        :param variables: variables to be passed to the template.
        """
        template = tmt.utils.render_template_file(path, self._environment, **variables)
        return _append_newline_if_missing(template)

    def _init_custom_templates_folder(self) -> None:
        """ Create custom template folders if they don't exist. """
        for key in TEMPLATE_TYPES:
            path = self.custom_template_path / key
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise tmt.utils.GeneralError(
                    f"Failed to create template folder '{path}'.\n{error}") from error


# Global TemplateManager object
MANAGER = TemplateManager()
