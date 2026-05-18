import re
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, Union, cast

import fmf.utils
from click import echo

import tmt.utils
from tmt._compat.typing import Self
from tmt.container import SpecBasedContainer, container

if TYPE_CHECKING:
    from tmt.base.core import FmfId, _RawFmfId

#
# A type describing the raw form of the core `link` attribute. See
# https://tmt.readthedocs.io/en/stable/spec/core.html#link for its
# formal specification. Internally, a link is represented by a `Link`
# class instance, and types below describe the raw data coming from Fmf
# nodes and CLI options.


# Link relations.
_RawLinkRelationName = Literal[
    'verifies',
    'verified-by',
    'implements',
    'implemented-by',
    'documents',
    'documented-by',
    'blocks',
    'blocked-by',
    'duplicates',
    'duplicated-by',
    'parent',
    'child',
    'relates',
    'test-script',
    # Special case: not a relation, but it can appear where relations appear in
    # link data structures.
    'note',
]

# Link target - can be either a string (like test case name or URL), or an fmf id.
_RawLinkTarget = Union[str, '_RawFmfId']

# Basic "relation-aware" link - essentially a mapping with one key/value pair.
_RawLinkRelation = dict[_RawLinkRelationName, _RawLinkTarget]

# A single link can be represented as a string or FMF ID (meaning only target is specified),
# or a "relation-aware" link aka mapping defined above.
_RawLink = Union[str, '_RawFmfId', _RawLinkRelation]

# Collection of links - can be either a single link, or a list of links, and all
# link forms may be used together.
_RawLinks = Union[_RawLink, list[_RawLink]]


@container
class LinkNeedle:
    """
    A container to use for searching links.

    ``relation`` and ``target`` fields hold regular expressions that
    are to be searched for in the corresponding fields of :py:class:`Link`
    instances.
    """

    relation: str = r'.*'
    target: str = r'.*'

    @classmethod
    def from_spec(cls, value: str) -> 'LinkNeedle':
        """
        Convert from a specification file or from a CLI option

        Specification is described in [1], this constructor takes care
        of parsing it into a corresponding ``LinkNeedle`` instance.

        [1] https://tmt.readthedocs.io/en/stable/plugins/discover.html#fmf
        """

        parts = value.split(':', maxsplit=1)

        if len(parts) == 1:
            return LinkNeedle(target=parts[0])

        return LinkNeedle(relation=parts[0], target=parts[1])

    def __str__(self) -> str:
        return f'{self.relation}:{self.target}'

    def matches(self, link: 'Link') -> bool:
        """
        Find out whether a given link matches this needle
        """

        # Rule out the simple case, mismatching relation.
        if not re.search(self.relation, link.relation):
            return False

        # If the target is a string, the test is trivial.
        if isinstance(link.target, str):
            return re.search(self.target, link.target) is not None

        # If the target is an fmf id, the current basic implementation will
        # check just the `name` key, if it's defined. More fields may come
        # later, pending support for more sophisticated parsing of link
        # needle on a command line.
        if link.target.name:
            return re.search(self.target, link.target.name) is not None

        return False


@container
class Link(SpecBasedContainer[Any, _RawLinkRelation]):
    """
    An internal "link" as defined by tmt specification.

    All links, after entering tmt internals, are converted from their raw
    representation into instances of this class.

    [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
    """

    DEFAULT_RELATIONSHIP: ClassVar[_RawLinkRelationName] = 'relates'

    relation: _RawLinkRelationName
    target: Union[str, 'FmfId']
    note: Optional[str] = None

    @classmethod
    def from_spec(cls, spec: _RawLink) -> 'Link':
        """
        Convert from a specification file or from a CLI option

        Specification is described in [1], this constructor takes care
        of parsing it into a corresponding ``Link`` instance.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        from tmt.base.core import FmfId

        # `spec` can be either a string, fmf id, or relation:target mapping with
        # a single key (modulo `note` key, of course).

        # String is simple: if `spec` is a string, it represents a [relation:]target,
        # and we use the default relationship if relation is not specified.
        if isinstance(spec, str):
            pattern = rf'(?:(?P<relation>{"|".join(Links._relations)}):)?(?P<target>.+)'
            result = re.match(pattern, spec)
            if result is None:
                raise tmt.utils.SpecificationError(
                    f"Invalid spec '{spec}' (should be [relation:]<target>)."
                )

            relation_target_pair = result.groupdict()
            assert relation_target_pair['target'] is not None
            relation = cast(
                _RawLinkRelationName, relation_target_pair['relation'] or Link.DEFAULT_RELATIONSHIP
            )
            target = relation_target_pair['target']
            return Link(relation=relation, target=target)

        # From now on, `spec` is a mapping, and may contain the optional
        # `note` key. Extract the key for later.
        # FIXME: cast() - typeless "dispatcher" method
        note = cast(Optional[str], spec.get('note', None))

        # Count how many relations are stored in spec.
        relations = [
            cast(_RawLinkRelationName, key)
            for key in spec
            if key not in ([*FmfId.VALID_KEYS, 'note'])
        ]

        # If there are no relations, spec must be an fmf id, representing
        # a target.
        if len(relations) == 0:
            return Link(
                relation=Link.DEFAULT_RELATIONSHIP,
                target=FmfId.from_spec(cast('_RawFmfId', spec)),
                note=note,
            )

        # More relations than 1 are a hard error, only 1 is allowed.
        if len(relations) > 1:
            raise tmt.utils.SpecificationError(
                f"Multiple relations specified for the link ({fmf.utils.listed(relations)})."
            )

        # At this point, we know there's just a single relation, its value is the target,
        # and note we already put aside.
        #
        # ignore[typeddict-item]: as far as mypy knows, we did not narrow the type of `spec`,
        # _RawFmfId is still in play - but we do know it's no longer possible because such a
        # value we ruled out thanks to `"no relations" check above. At this point,
        # the right side of relation must be _RawLinkTarget and nothing else. Helping
        # mypy to realize that.
        relation = relations[0]
        raw_target = cast(_RawLinkTarget, spec[relation])  # type: ignore[typeddict-item]

        # TODO: this should not happen with mandatory validation
        if relation not in Links._relations:
            raise tmt.utils.SpecificationError(
                f"Invalid link relation '{relation}' (should be "
                f"{fmf.utils.listed(Links._relations, join='or')})."
            )

        if isinstance(raw_target, str):
            return Link(relation=relation, target=raw_target, note=note)

        return Link(relation=relation, target=FmfId.from_spec(raw_target), note=note)

    def to_spec(self) -> _RawLinkRelation:
        """
        Convert to a form suitable for saving in a specification file

        No matter what the original specification was, every link will
        generate the very same type of specification, the ``relation: target``
        one.

        Output of this method is fully compatible with specification, and when
        given to :py:meth:`from_spec`, it shall create a ``Link`` instance
        with the same properties as the original one.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        spec: _RawLinkRelation = {
            self.relation: self.target.to_spec() if isinstance(self.target, FmfId) else self.target
        }

        if self.note is not None:
            spec['note'] = self.note

        return spec


class Links(SpecBasedContainer[Any, list[_RawLinkRelation]]):
    """
    Collection of links in tests, plans and stories.

    Provides abstraction over the whole collection of object's links.

    [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
    """

    # The list of all supported link relations
    _relations: list[_RawLinkRelationName] = [
        'verifies',
        'verified-by',
        'implements',
        'implemented-by',
        'documents',
        'documented-by',
        'blocks',
        'blocked-by',
        'duplicates',
        'duplicated-by',
        'parent',
        'child',
        'relates',
        'test-script',
    ]

    _links: list[Link]

    def __init__(self, *, data: Optional[_RawLinks] = None):
        """
        Create a collection from raw link data
        """

        # TODO: this should not happen with mandatory validation
        if data is not None and not isinstance(data, (str, dict, list)):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
            # TODO: deliver better key address, needs to know the parent
            raise tmt.utils.NormalizationError(
                'link', data, 'a string, a fmf id or a list of their combinations'
            )

        # Nothing to do if no data provided
        if data is None:
            self._links = []

            return

        specs = data if isinstance(data, list) else [data]

        # Ensure that each link is in the canonical form
        self._links = [Link.from_spec(spec) for spec in specs]

    @classmethod
    def from_spec(cls, spec: Union[_RawLink, list[_RawLink]]) -> Self:
        return cls(data=spec)

    def to_spec(self) -> list[_RawLinkRelation]:
        """
        Convert to a form suitable for saving in a specification file

        No matter what the original specification was, every link will
        generate the very same type of specification, the ``relation: target``
        one.

        Output of this method is fully compatible with specification, and when
        used to instantiate :py:meth:`Link` object, it shall create a collection
        of links with the same properties as the original one.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        return [link.to_spec() for link in self._links]

    def get(self, relation: Optional[_RawLinkRelationName] = None) -> list[Link]:
        """
        Get links with given relation, all by default
        """
        return [link for link in self._links if relation is None or link.relation == relation]

    def show(self) -> None:
        """
        Format a list of links with their relations
        """
        for link in self._links:
            # TODO: needs a format for fmf id target
            echo(
                tmt.utils.format(
                    link.relation.rstrip('-by'), f"{link.target}", key_color='cyan', wrap=False
                )
            )

    def has_link(self, needle: Optional[LinkNeedle] = None) -> bool:
        """
        Check whether this set of links contains a matching link.

        If ``needle`` is left unspecified, method would take all links into
        account, as if the ``needle`` was match all possible links (``.*:.*``).
        Method would then answer the question "are there *any* links at all?"

        :param needle: if set, only links matching ``needle`` are considered. If
            not set, method considers all present links.
        :returns: ``True`` if there are matching links, ``False`` otherwise.
        """

        if needle is None:
            return bool(self._links)

        return any(needle.matches(link) for link in self._links)

    def __bool__(self) -> bool:
        return self.has_link()
