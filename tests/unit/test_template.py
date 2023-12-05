import tmt
import tmt.log
import tmt.plugins
import tmt.steps.discover
import tmt.templates
import tmt.utils
from tmt.utils import Path


def test_init_custom_templates_folder(tmppath: Path) -> None:
    templates_dir = tmppath / 'templates'
    template_manager = tmt.templates.TemplateManager(templates_dir)

    story_dir = templates_dir / 'story'
    plan_dir = templates_dir / 'plan'
    test_metadata_dir = templates_dir / 'test'
    test_script_dir = templates_dir / 'script'

    assert template_manager.custom_template_path == templates_dir
    assert templates_dir.exists()
    assert story_dir.exists()
    assert plan_dir.exists()
    assert test_script_dir.exists()
    assert test_metadata_dir.exists()


def test_get_default_templates(tmppath: Path) -> None:
    template_manager = tmt.templates.TemplateManager(tmppath)

    default_templates = template_manager.default_templates['default']
    story_templates = template_manager.default_templates['story']
    plan_templates = template_manager.default_templates['plan']
    test_metadata_templates = template_manager.default_templates['test']
    test_script_templates = template_manager.default_templates['script']

    assert default_templates['plan'] is not None
    assert story_templates['full'] is not None
    assert plan_templates['full'] is not None
    assert test_script_templates['shell'] is not None
    assert test_metadata_templates['shell'] is not None


def test_get_custom_templates(tmppath: Path) -> None:
    def create_template_file(template_path: Path, content: str) -> None:
        template_path.write_text(content)

    template_manager = tmt.templates.TemplateManager(tmppath)

    create_template_file(
        template_manager.custom_template_path / 'story' / 'tmp_story.j2',
        'Story template content.'
        )
    create_template_file(
        template_manager.custom_template_path / 'plan' / 'tmp_plan.j2',
        'Plan template content.'
        )
    create_template_file(
        template_manager.custom_template_path / 'test' / 'tmp_test_metadata.j2',
        'Test metadata template content.'
        )
    create_template_file(
        template_manager.custom_template_path / 'script' / 'tmp_test_script.j2',
        'Test script template content.'
        )

    assert (template_manager.custom_templates['story']['tmp_story'].read_text()
            == 'Story template content.')
    assert (template_manager.custom_templates['plan']['tmp_plan'].read_text()
            == 'Plan template content.')
    assert (template_manager.custom_templates['test']['tmp_test_metadata'].read_text()
            == 'Test metadata template content.')
    assert (template_manager.custom_templates['script']['tmp_test_script'].read_text()
            == 'Test script template content.')


def test_get_combined_templates(tmppath: Path) -> None:
    def create_template_file(template_path: Path, content: str) -> None:
        template_path.write_text(content)

    template_manager = tmt.templates.TemplateManager(tmppath)

    create_template_file(
        template_manager.custom_template_path / 'story' / 'full.j2',
        'Overriden story template content.'
        )
    create_template_file(
        template_manager.custom_template_path / 'plan' / 'custom_plan.j2',
        'Plan template content.'
        )

    assert template_manager.templates['story']['base'] is not None
    assert template_manager.templates['story']['full'] is not None
    assert (template_manager.templates['story']['full'].read_text()
            == 'Overriden story template content.')

    assert template_manager.templates['plan']['base'] is not None
    assert template_manager.templates['plan']['custom_plan'] is not None
    assert (template_manager.templates['plan']['custom_plan'].read_text()
            == 'Plan template content.')


def test_render_template_file(tmppath: Path) -> None:
    template_manager = tmt.templates.TemplateManager(tmppath)

    static_story_path = template_manager.custom_template_path / 'story' / 'static.j2'
    variable_story_path = template_manager.custom_template_path / 'story' / 'with_variable.j2'

    static_story_path.write_text('Story template content.')
    variable_story_path.write_text('Plan template content with variable: {{ variable }}.')

    variables = {
        'variable': 'value'
        }
    static_content = template_manager.render_file(static_story_path)
    variable_content = template_manager.render_file(variable_story_path, **variables)

    assert static_content == 'Story template content.\n'
    assert variable_content == 'Plan template content with variable: value.\n'
