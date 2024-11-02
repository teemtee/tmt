""" Test Metadata Utilities """


import dataclasses
import functools
import os
import re
import subprocess
import urllib.parse
from re import Pattern
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.utils
from tmt.utils import (
    Command,
    CommandOutput,
    Common,
    Environment,
    GeneralError,
    GitUrlError,
    MetadataError,
    Path,
    RunError,
    )

if TYPE_CHECKING:
    import tmt.base


@dataclasses.dataclass
class GitInfo:
    """ Data container for commonly queried git data. """

    #: Path to the git root.
    git_root: Path

    #: Most human-readable git ref.
    ref: str

    #: Git remote linked to the current git ref.
    remote: str

    #: Default branch of the remote.
    default_branch: Optional[str]

    #: Public url of the remote.
    url: Optional[str]

    @classmethod
    @functools.cache
    def from_fmf_root(cls, *, fmf_root: Path, logger: tmt.log.Logger) -> Optional["GitInfo"]:
        """
        Get the current git info of an fmf tree.

        :param fmf_root: Root path of the fmf tree
        :param logger: Current tmt logger
        :return: Git info container or ``None`` if git metadata could not be resolved
        """

        def run(command: Command) -> str:
            """
            Run command, return output.
            We don't need the stderr here, but we need exit status.
            """
            result = command.run(cwd=fmf_root, logger=logger)
            if result.stdout is None:
                return ""
            return result.stdout.strip()

        # Prepare url (for now handle just the most common schemas)
        try:
            # Check if we are a git repo
            run(Command("git", "rev-parse", "--is-inside-work-tree"))

            # Initialize common git facts
            # Get some basic git references for HEAD
            all_refs = run(Command("git", "for-each-ref", "--format=%(refname)", "--points-at=@"))
            logger.debug("git all_refs", all_refs, level=3)
            # curr_ref is either HEAD or fully-qualified (branch) reference
            curr_ref = run(Command("git", "rev-parse", "--symbolic-full-name", "@"))
            logger.debug("git initial curr_ref", curr_ref, level=3)
            # Get the top-level git_root
            _git_root = git_root(fmf_root=fmf_root, logger=logger)
            assert _git_root is not None  # narrow type
        except RunError:
            # Not a git repo, everything should be pointing to None at this point
            return None

        if curr_ref != "HEAD":
            # The reference is fully qualified -> we are on a branch
            # Get the short name
            branch = run(Command("git", "for-each-ref", "--format=%(refname:short)", curr_ref))
            ref = branch
        else:
            # Not on a branch, check if we are on a tag or just a refs
            try:
                tags = run(Command("git", "describe", "--tags"))
                logger.debug("git tags", tags, level=3)
                # Is it possible to find which tag was used to checkout?
                # Now we just assume the first tag is the one we want
                tag_used = tags.splitlines()[0]
                logger.debug("Using tag", tag_used, level=3)
                # Point curr_ref to the fully-qualified ref
                curr_ref = f"refs/tags/{tag_used}"
                ref = tag_used
            except RunError:
                # We are not on a tag, just use the first available reference
                curr_ref = all_refs.splitlines()[0] if all_refs else curr_ref
                # Point the ref to the commit
                commit = run(Command("git", "rev-parse", curr_ref))
                logger.debug("Using commit", commit, level=3)
                ref = commit

        logger.debug("curr_ref used", curr_ref, level=3)
        remote_name = run(
            Command(
                "git",
                "for-each-ref",
                "--format=%(upstream:remotename)",
                curr_ref))
        if not remote_name:
            # If no specific upstream is defined, default to `origin`
            remote_name = "origin"
        try:
            remote = run(Command("git", "config", "--get", f"remote.{remote_name}.url"))
            url = public_git_url(remote)
            _default_branch = default_branch(
                repository=_git_root, remote=remote, logger=logger)
        except RunError:
            url = None
            _default_branch = None

        return GitInfo(
            git_root=_git_root,
            ref=ref,
            remote=remote_name,
            url=url,
            default_branch=_default_branch
            )


# Avoid multiple subprocess calls for the same url
@functools.cache
def check_git_url(url: str, logger: tmt.log.Logger) -> str:
    """ Check that a remote git url is accessible """
    try:
        logger.debug(f"Check git url '{url}'.")
        subprocess.check_call(
            ["git", "ls-remote", "--heads", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={"GIT_ASKPASS": "echo", "GIT_TERMINAL_PROMPT": "0"})
        return url
    except subprocess.CalledProcessError:
        raise GitUrlError(f"Unable to contact remote git via '{url}'.")


PUBLIC_GIT_URL_PATTERNS: list[tuple[str, str]] = [
    # Gitlab on private namespace is synced to pkgs.devel.redhat.com
    # old: https://gitlab.com/redhat/rhel/tests/bash
    # old: git@gitlab.com:redhat/rhel/tests/bash
    # new: https://pkgs.devel.redhat.com/git/tests/bash
    (
        r'(?:git@|https://)gitlab.com[:/]redhat/rhel(/.+)',
        r'https://pkgs.devel.redhat.com/git\1'
        ),

    # GitHub, GitLab
    # old: git@github.com:teemtee/tmt.git
    # new: https://github.com/teemtee/tmt.git
    (
        r'git@(.*):(.*)',
        r'https://\1/\2'
        ),

    # RHEL packages
    # old: git+ssh://psplicha@pkgs.devel.redhat.com/tests/bash
    # old: ssh://psplicha@pkgs.devel.redhat.com/tests/bash
    # old: ssh://pkgs.devel.redhat.com/tests/bash
    # new: https://pkgs.devel.redhat.com/git/tests/bash
    (
        r'(git\+)?ssh://(\w+@)?(pkgs\.devel\.redhat\.com)/(.*)',
        r'https://\3/git/\4'
        ),

    # Fedora packages, Pagure
    # old: git+ssh://psss@pkgs.fedoraproject.org/tests/shell
    # old: ssh://psss@pkgs.fedoraproject.org/tests/shell
    # new: https://pkgs.fedoraproject.org/tests/shell
    (
        r'(git\+)?ssh://(\w+@)?([^/]*)/(.*)',
        r'https://\3/\4'
        )
    ]


def public_git_url(url: str) -> str:
    """
    Convert a git url into a public format.

    :param url: an URL to convert.
    :returns: URL that is publicly accessible without authentication,
        or the original URL if no applicable conversion was found.
    """
    return rewrite_git_url(url, PUBLIC_GIT_URL_PATTERNS)


def rewrite_git_url(url: str, patterns: list[tuple[str, str]]) -> str:
    """
    Rewrite git url based on supplied patterns

    :param url: an URL to modify
    :param patterns: List of patterns to try in order
    :returns: Modified url or the original one if no pattern was be applied.
    """
    for pattern, replacement in patterns:
        public_url = re.sub(pattern, replacement, url)

        # If we got different string, `pattern` matched the URL and
        # `replacement` made its changes - we got our hit!
        if public_url != url:
            return public_url

    # Otherwise return unmodified
    return url


# Environment variable prefixes
INJECT_CREDENTIALS_URL_PREFIX = 'TMT_GIT_CREDENTIALS_URL_'
INJECT_CREDENTIALS_VALUE_PREFIX = 'TMT_GIT_CREDENTIALS_VALUE_'


def inject_auth_git_url(url: str) -> str:
    """
    Inject username or token to the git url

    :param url: original git repo url
    :returns: URL with injected authentication based on pattern from the environment
        or unmodified URL
    """
    # Try all environment variables sorted by their name
    for name, value in sorted(os.environ.items(), key=lambda x: x[0]):
        # First one which matches url is taken into the account
        if name.startswith(INJECT_CREDENTIALS_URL_PREFIX) and re.search(value, url):
            unique_suffix = name[len(INJECT_CREDENTIALS_URL_PREFIX):]
            variable_with_value = f'{INJECT_CREDENTIALS_VALUE_PREFIX}{unique_suffix}'
            # Get credentials value
            try:
                creds = os.environ[variable_with_value]
            except KeyError:
                raise GitUrlError(
                    f'Missing "{variable_with_value}" variable with credentials for "{url}"')
            # Return original url if credentials is an empty value
            if not creds:
                return url
            # Finally inject credentials into the url and return it
            return re.sub(r'([^/]+://)([^/]+)', rf'\1{creds}@\2', url)
    # Otherwise return unmodified
    return url


CLONABLE_GIT_URL_PATTERNS: list[tuple[str, str]] = [
    # git:// protocol is not possible for r/o access
    # old: git://pkgs.devel.redhat.com/tests/bash
    # new: https://pkgs.devel.redhat.com/git/tests/bash
    (
        r'git://(pkgs\.devel\.redhat\.com)/(.*)',
        r'https://\1/git/\2'
        ),
    ]


def clonable_git_url(url: str) -> str:
    """ Modify the git repo url so it can be cloned """
    url = rewrite_git_url(url, CLONABLE_GIT_URL_PATTERNS)
    return inject_auth_git_url(url)


def web_git_url(url: str, ref: str, path: Optional[Path] = None) -> str:
    """
    Convert a public git url into a clickable web url format

    Compose a clickable link from git url, ref and path to file
    for the most common git servers.
    """
    if path:
        path = Path(urllib.parse.quote_plus(str(path), safe="/"))

    # Special handling for pkgs.devel (ref at the end)
    if 'pkgs.devel' in url:
        url = url.replace('git://', 'https://').replace('.com', '.com/cgit')
        url += '/tree'
        if path:
            url += str(path)
        url += f'?h={ref}'
        return url

    # GitHub & GitLab
    if any(server in url for server in ['github', 'gitlab']):
        url = url.replace('.git', '').rstrip('/')
        url += f'/tree/{ref}'

    if path:
        url += str(path)

    return url


def git_hash(*, directory: Path, logger: tmt.log.Logger) -> Optional[str]:
    """
    Return short hash of current HEAD in the git repo in directory.

    :param directory: path to a local git repository.
    :param logger: used for logging.
    :returns: short hash as string
    """
    cmd = Command("git", "rev-parse", "--short", "HEAD")
    result = cmd.run(cwd=directory, logger=logger)

    if result.stdout is None:
        raise RunError(message="No output from 'git' when looking for the hash of HEAD.",
                       command=cmd,
                       returncode=0,
                       stderr=result.stderr)

    return result.stdout.strip()


def git_root(*, fmf_root: Path, logger: tmt.log.Logger) -> Optional[Path]:
    """
    Find a path to the root of git repository containing an fmf root.

    :param fmf_root: path to an fmf root that is supposedly in a git repository.
    :param logger: used for logging.
    :returns: path to the git repository root, if fmf root lies in one,
        or ``None``.
    """

    try:
        result = Command("git", "rev-parse", "--show-toplevel").run(cwd=fmf_root, logger=logger)

        if result.stdout is None:
            return None

        return Path(result.stdout.strip())

    except RunError:
        # Always return an empty string in case 'git' command is run in a non-git repo
        return None


def git_add(*, path: Path, logger: tmt.log.Logger) -> None:
    """
    Add path to the git index.

    :param path: path to add to the git index.
    :param logger: used for logging.
    """
    path = path.resolve()

    try:
        Command("git", "add", path).run(cwd=path.parent, logger=logger)

    except RunError as error:
        raise GeneralError(f"Failed to add path '{path}' to git index.") from error


def git_ignore(*, root: Path, logger: tmt.log.Logger) -> list[Path]:
    """
    Collect effective paths ignored by git.

    :param root: path to the root of git repository.
    :param logger: used for logging.
    :returns: list of actual paths that would be ignored by git based on
        its ``.gitignore`` files. If a whole directory is to be ignored,
        it is listed as a directory path, not listing its content.
    """

    output = Command(
        'git',
        'ls-files',
        # Consider standard git exclusion files
        '--exclude-standard',
        # List untracked files matching exclusion patterns
        '-oi',
        # If a whole directory is to be ignored, list only its name with a trailing slash
        '--directory') \
        .run(cwd=root, logger=logger)

    return [Path(line.strip()) for line in output.stdout.splitlines()] if output.stdout else []


def default_branch(
        *,
        repository: Path,
        remote: str = 'origin',
        logger: tmt.log.Logger) -> Optional[str]:
    """ Detect default branch from given local git repository """
    # Make sure '.git' is present and it is a file or a directory
    dot_git = repository / '.git'
    if not dot_git.exists():
        return None
    if not dot_git.is_file() and not dot_git.is_dir():
        return None

    # Detect the original repository path if worktree is provided
    if dot_git.is_file():
        try:
            result = Command("git", "rev-parse", "--path-format=absolute", "--git-common-dir").run(
                cwd=repository,
                logger=logger)
        except RunError:
            return None
        if result.stdout is None:
            return None
        repository = Path(result.stdout.strip().replace("/.git", ""))

    # Make sure the '.git/refs/remotes/{remote}' directory is present
    git_remotes_dir = repository / f'.git/refs/remotes/{remote}'
    if not git_remotes_dir.exists():
        return None

    # Make sure the HEAD reference is available
    head = git_remotes_dir / 'HEAD'
    if not head.exists():
        try:
            Command('git', 'remote', 'set-head', f'{remote}', '--auto').run(
                cwd=repository,
                logger=logger)
        except BaseException:
            return None

    # The ref format is 'ref: refs/remotes/origin/main'
    return head.read_text().strip().split('/')[-1]


def validate_git_status(test: 'tmt.base.Test') -> tuple[bool, str]:
    """
    Validate that test has current metadata on fmf_id

    Return a tuple (boolean, message) as the result of validation.

    Checks that sources:
    - all local changes are committed
    - up to date on remote repository
    - .fmf/version marking fmf root is committed as well

    When all checks pass returns (True, '').
    """

    # There has to be an fmf tree root defined
    if not test.fmf_root:
        raise MetadataError(f"Test '{test.name}' does not have fmf root defined.")

    sources = [
        *test.fmf_sources,
        test.fmf_root / '.fmf' / 'version'
        ]

    # Use tmt's run instead of subprocess.run
    run = Common(logger=test._logger).run

    # Narrow the type - this should be true, we might need to update
    # this assert once fmf is properly annotated
    assert isinstance(test.node.root, str)
    cwd = Path(test.node.root)

    # Check for not committed metadata changes
    cmd = Command(
        'git',
        'status', '--porcelain',
        '--',
        *[str(source) for source in sources]
        )
    try:
        result = run(cmd, cwd=cwd, join=True)
    except RunError as error:
        return (
            False,
            f"Failed to run git status: {error.stdout}"
            )

    not_committed: list[str] = []
    assert result.stdout is not None
    for line in result.stdout.split('\n'):
        if line:
            # XY PATH or XY ORIG -> PATH. XY and PATH are separated by space
            not_committed.append(line[3:])

    if not_committed:
        return (False, "Uncommitted changes in " + " ".join(not_committed))

    # Check for not pushed changes
    cmd = Command("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    try:
        result = run(cmd, cwd=cwd)
    except RunError as error:
        return (
            False,
            f'Failed to get remote branch, error raised: "{error.stderr}"'
            )

    assert result.stdout is not None
    remote_ref = result.stdout.strip()

    cmd = Command(
        'git',
        'diff',
        f'HEAD..{remote_ref}',
        '--name-status',
        '--',
        *[str(source) for source in sources]
        )
    try:
        result = run(cmd, cwd=cwd)
    except RunError as error:
        return (
            False,
            f'Failed to diff against remote branch, error raised: "{error.stderr}"')

    not_pushed: list[str] = []
    assert result.stdout is not None
    for line in result.stdout.split('\n'):
        if line:
            _, path = line.strip().split('\t', maxsplit=2)
            not_pushed.append(path)
    if not_pushed:
        return (False, "Not pushed changes in " + " ".join(not_pushed))

    return (True, '')


class DistGitHandler:
    """ Common functionality for DistGit handlers """

    sources_file_name = 'sources'
    uri = "/rpms/{name}/{filename}/{hashtype}/{hash}/{filename}"

    usage_name: str  # Name to use for dist-git-type
    re_source: Pattern[str]
    # https://www.gnu.org/software/tar/manual/tar.html#auto_002dcompress
    re_supported_extensions: Pattern[str] = re.compile(
        r'\.((tar\.(gz|Z|bz2|lz|lzma|lzo|xz|zst))|tgz|taz|taZ|tz2|tbz2|tbz|tlz|tzst)$')
    lookaside_server: str
    remote_substring: Pattern[str]

    def url_and_name(self, cwd: Optional[Path] = None) -> list[tuple[str, str]]:
        """
        Return list of urls and basenames of the used source

        The 'cwd' parameter has to be a DistGit directory.
        """
        cwd = cwd or Path.cwd()
        # Assumes <package>.spec
        globbed = list(cwd.glob('*.spec'))
        if len(globbed) != 1:
            raise GeneralError(f"No .spec file is present in '{cwd}'.")
        package = globbed[0].stem
        ret_values: list[tuple[str, str]] = []
        try:
            for line in (cwd / self.sources_file_name).splitlines():
                match = self.re_source.match(line)
                if match is None:
                    raise GeneralError(
                        f"Couldn't match '{self.sources_file_name}' "
                        f"content with '{self.re_source.pattern}'.")
                used_hash, source_name, hash_value = match.groups()
                ret_values.append((self.lookaside_server + self.uri.format(
                    name=package,
                    filename=source_name,
                    hash=hash_value,
                    hashtype=used_hash.lower()
                    ), source_name))
        except Exception as error:
            raise GeneralError(f"Couldn't read '{self.sources_file_name}' file.") from error
        if not ret_values:
            raise GeneralError(
                "No sources found in '{self.sources_file_name}' file.")
        return ret_values

    def its_me(self, remotes: list[str]) -> bool:
        """ True if self can work with remotes """
        return any(self.remote_substring.search(item) for item in remotes)


class FedoraDistGit(DistGitHandler):
    """ Fedora Handler """

    usage_name = "fedora"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    lookaside_server = "https://src.fedoraproject.org/repo/pkgs"
    remote_substring = re.compile(r'fedoraproject\.org')


class CentOSDistGit(DistGitHandler):
    """ CentOS Handler """

    usage_name = "centos"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    lookaside_server = "https://sources.stream.centos.org/sources"
    remote_substring = re.compile(r'redhat/centos')


class RedHatGitlab(DistGitHandler):
    """ Red Hat on Gitlab """

    usage_name = "redhatgitlab"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    # Location already public (standard-test-roles)
    lookaside_server = "http://pkgs.devel.redhat.com/repo"
    remote_substring = re.compile(r'redhat/rhel/')


def get_distgit_handler(
        remotes: Optional[list[str]] = None,
        usage_name: Optional[str] = None) -> DistGitHandler:
    """
    Return the right DistGitHandler

    Pick the DistGitHandler class which understands specified
    remotes or by usage_name.
    """
    for candidate_class in DistGitHandler.__subclasses__():
        if usage_name is not None and usage_name == candidate_class.usage_name:
            return candidate_class()
        if remotes is not None:
            ret_val = candidate_class()
            if ret_val.its_me(remotes):
                return ret_val
    raise GeneralError(f"No known remote in '{remotes}'.")


def get_distgit_handler_names() -> list[str]:
    """ All known distgit handlers """
    return [i.usage_name for i in DistGitHandler.__subclasses__()]


def distgit_download(
        *,
        distgit_dir: Path,
        target_dir: Path,
        handler_name: Optional[str] = None,
        caller: Optional['Common'] = None,
        logger: tmt.log.Logger
        ) -> None:
    """
    Download sources to the target_dir

    distgit_dir is path to the DistGit repository
    """
    # Get the handler unless specified
    if handler_name is None:
        cmd = Command("git", "config", "--get-regexp", '^remote\\..*.url')
        output = cmd.run(cwd=distgit_dir,
                         caller=caller,
                         logger=logger)
        if output.stdout is None:
            raise tmt.utils.GeneralError("Missing remote origin url.")
        remotes = output.stdout.split('\n')
        handler = tmt.utils.get_distgit_handler(remotes=remotes)
    else:
        handler = tmt.utils.get_distgit_handler(usage_name=handler_name)

    for url, source_name in handler.url_and_name(distgit_dir):
        logger.debug(f"Download sources from '{url}'.")
        with tmt.utils.retry_session() as session:
            response = session.get(url)
        response.raise_for_status()
        target_dir.mkdir(exist_ok=True, parents=True)
        (target_dir / source_name).write_bytes(response.content)


def git_clone(
        *,
        url: str,
        destination: Path,
        shallow: bool = False,
        can_change: bool = True,
        env: Optional[Environment] = None,
        attempts: Optional[int] = None,
        interval: Optional[int] = None,
        timeout: Optional[int] = None,
        logger: tmt.log.Logger) -> CommandOutput:
    """
    Clone git repository from provided url to the destination directory

    :param url: Source URL of the git repository.
    :param destination: Full path to the destination directory.
    :param shallow: For ``shallow=True`` first try to clone repository
        using ``--depth=1`` option. If not successful clone repo with
        the whole history.
    :param can_change: URL can be modified with hardcoded rules. Use
        ``can_change=False`` to disable rewrite rules.
    :param env: Environment provided to the ``git clone`` process.
    :param attempts: Number of tries to call the function.
    :param interval: Amount of seconds to wait before a new try.
    :param timeout: Overall maximum time in seconds to clone the repo.
    :param logger: A Logger instance to be used for logging.
    :returns: Command output, bundled in a :py:class:`CommandOutput` tuple.
    """

    def clone_the_repo(
            url: str,
            destination: Path,
            shallow: bool = False,
            env: Optional[Environment] = None,
            timeout: Optional[int] = None) -> CommandOutput:
        """ Clone the repo, handle history depth """

        depth = ['--depth=1'] if shallow else []
        return Command('git', 'clone', *depth, url, destination).run(
            cwd=Path('/'), env=env, timeout=timeout, logger=logger)

    from tmt.utils import GIT_CLONE_ATTEMPTS, GIT_CLONE_INTERVAL, GIT_CLONE_TIMEOUT

    timeout = timeout or GIT_CLONE_TIMEOUT
    attempts = attempts or GIT_CLONE_ATTEMPTS
    interval = interval or GIT_CLONE_INTERVAL

    # Update url only once
    if can_change:
        url = clonable_git_url(url)

    # Do an extra shallow clone first
    if shallow:
        try:
            return clone_the_repo(
                shallow=True,
                url=url,
                destination=destination,
                env=env,
                timeout=timeout)
        except RunError:
            logger.debug(f"Shallow clone of '{url}' failed, let's try with the full history.")

    # Finish with whatever number attempts requested (deep)
    return tmt.utils.retry(
        func=clone_the_repo,
        attempts=attempts,
        interval=interval,
        label=f"git clone {url} {destination}",
        url=url,
        destination=destination,
        shallow=False,
        env=env,
        timeout=timeout,
        logger=logger)
