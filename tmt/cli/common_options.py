""" Options commonly used inside tmt commands """

import tmt.options
from tmt.options import create_options_decorator

verbosity_options = create_options_decorator(tmt.options.VERBOSITY_OPTIONS)
dry_options = create_options_decorator(tmt.options.DRY_OPTIONS)
force_dry_options = create_options_decorator(tmt.options.FORCE_DRY_OPTIONS)
fix_options = create_options_decorator(tmt.options.FIX_OPTIONS)
workdir_root_options = create_options_decorator(tmt.options.WORKDIR_ROOT_OPTIONS)
filter_options = create_options_decorator(tmt.options.FILTER_OPTIONS)
filter_options_long = create_options_decorator(tmt.options.FILTER_OPTIONS_LONG)
fmf_source_options = create_options_decorator(tmt.options.FMF_SOURCE_OPTIONS)
story_flags_filter_options = create_options_decorator(tmt.options.STORY_FLAGS_FILTER_OPTIONS)
remote_plan_options = create_options_decorator(tmt.options.REMOTE_PLAN_OPTIONS)
