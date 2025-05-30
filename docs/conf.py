#
#  documentation build configuration file, created by
# sphinx-quickstart on Mon Apr 27 17:44:03 2015.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sphinx.application import Sphinx

import tmt.utils

_POSSIBLE_THEMES: list[tuple[Optional[str], str]] = [
    # Use renku as the default theme
    ('renku_sphinx_theme', 'renku'),
    # Fall back to sphinx_rtd_theme if available
    ('sphinx_rtd_theme', 'sphinx_rtd_theme'),
    # The default theme
    (None, 'default'),
]

# NOTE: this one is defined somewhere below, among original Sphinx config fields,
# but we need it as early as possible to be set when loading themes.
# Add any paths that contain custom themes here, relative to this directory.
html_theme_path = []


def _load_theme(theme_package_name: str, theme_name: str) -> bool:
    try:
        theme_package = importlib.import_module(theme_package_name)

    except ModuleNotFoundError:
        return False

    global HTML_THEME

    HTML_THEME = theme_name

    if hasattr(theme_package, 'get_html_theme_path'):
        global html_theme_path

        path = theme_package.get_html_theme_path()

        html_theme_path = path if isinstance(path, list) else [path]

        return True

    return True


if 'TMT_DOCS_THEME' in os.environ:
    theme_package_name: Optional[str]
    theme_name: str

    theme_specs = os.environ['TMT_DOCS_THEME']

    try:
        theme_package_name, theme_name = theme_specs.split(':', 1)

    except ValueError:
        raise tmt.utils.GeneralError(
            f"Cannot split TMT_DOCS_THEME '{theme_specs}' into theme package and theme name."
        )

    if not _load_theme(theme_package_name, theme_name):
        raise tmt.utils.GeneralError(f"Cannot load theme from TMT_DOCS_THEME, '{theme_specs}'.")

else:
    for theme_package_name, theme_name in _POSSIBLE_THEMES:
        if not theme_package_name:
            HTML_THEME = theme_name
            break

        if _load_theme(theme_package_name, theme_name):
            break

    else:
        raise tmt.utils.GeneralError('Cannot find usable theme.')


# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('../'))

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autodoc.typehints',
    'sphinx_rtd_theme',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'

# The encoding of source files.
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = 'index'
master_man = 'man.1'

# General information about the project.
project = 'tmt'
copyright = 'Red Hat'
author = 'Petr Šplíchal'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = ''
# The full version, including alpha/beta/rc tags.
release = ''

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = 'en'

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
# today = ''
# Else, today_fmt is used as the format for a strftime call.
# today_fmt = '%B %d, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build', '**/*.inc.rst', 'plugins/hardware-matrix.rst']

# The reST default role (used for this markup: `text`) to use for all
# documents.
# default_role = None

# If true, '()' will be appended to :func: etc. cross-reference text.
# add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
# add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
# show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

# If true, keep warnings as "system message" paragraphs in the built documents.
# keep_warnings = False

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = False

# Autodocs & type hints
autodoc_default_flags = ['members', 'undoc-members', 'show-inheritance', 'private-members']
autodoc_default_options = {
    # Enable to "ignore" re-imported names in `tmt.__all__`
    'ignore-module-all': True
}
autoclass_content = "both"

autodoc_typehints_format = 'short'
autodoc_typehints_description_target = 'all'
# This one works, but it's a bit uglier than the default value (`signature`).
# autodoc_typehints = 'description'

# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = HTML_THEME

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
# html_theme_options = {}

# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
# html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
# html_short_title = None

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_logo = 'https://raw.githubusercontent.com/teemtee/docs/main/logo/tmt-logo-dark-background.png'

# The name of an image file (within the static path) to use as favicon of the
# docs.
html_favicon = (
    'https://raw.githubusercontent.com/teemtee/docs/main/logo/tmt-logo-dark-background.svg'
)

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Include custom style.
html_style = os.getenv('TMT_DOCS_CUSTOM_HTML_STYLE', 'tmt-custom.css')

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
# html_extra_path = []

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
# html_last_updated_fmt = '%b %d, %Y'

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
# html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
# html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If false, no module index is generated.
# html_domain_indices = True

# If false, no index is generated.
# html_use_index = True

# If true, the index is split into individual pages for each letter.
# html_split_index = False

# If true, links to the reST sources are added to the pages.
# html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
# html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
# html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
# html_use_opensearch = ''

# This is the file name suffix for HTML files (e.g. ".xhtml").
# html_file_suffix = None

# Language to be used for generating the HTML full-text search index.
# Sphinx supports the following languages:
#   'da', 'de', 'en', 'es', 'fi', 'fr', 'hu', 'it', 'ja'
#   'nl', 'no', 'pt', 'ro', 'ru', 'sv', 'tr'
# html_search_language = 'en'

# A dictionary with options for the search language support, empty by default.
# Now only 'ja' uses this config value
# html_search_options = {'type': 'default'}

# The name of a javascript file (relative to the configuration directory) that
# implements a search results scorer. If empty, the default will be used.
# html_search_scorer = 'scorer.js'

# Output file base name for HTML help builder.
htmlhelp_basename = 'doc'

# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [(master_man, '', 'tmt Documentation', [author], 1)]

# If true, show URL addresses after external links.
# man_show_urls = False

# -- Options for linkcheck builder ----------------------------------------
linkcheck_request_headers = {
    r"https://github\.com/.*": {
        "User-Agent": "tmt-docs-linkcheck/1.0 (GitHub Actions)",
    },
}

github_token = os.environ.get('GITHUB_TOKEN')

if github_token:
    linkcheck_request_headers[r"https://github\.com/.*"]["Authorization"] = (
        f"Bearer {github_token}"
    )
    print("INFO: Using GITHUB_TOKEN for linkcheck requests to github.com")
else:
    print("INFO: GITHUB_TOKEN not found. linkcheck requests to github will be unauthenticated.")

linkcheck_retries = 3
linkcheck_ignore = [
    # Github "source code line" anchors are apparently too dynamic for linkcheck
    # to detect correctly. The link exists, a browser can open it, but linkcheck
    # reports a broken link.
    r'https://github.com/packit/packit/blob/main/packit/utils/logging.py#L10',
    # The site repeatedly refuses to serve pages to github
    r'https://www.cpu-world.com.*',
    # Stack Overflow uses captcha and these links are not essential
    r'https://stackoverflow.com.*',
]


def generate_tmt_docs(app: Sphinx, config: Any) -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


def setup(app: Sphinx) -> None:
    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("config-inited", generate_tmt_docs)
