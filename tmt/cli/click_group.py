""" Implementation of a custom click group """

from typing import List, Optional

import click
from fmf.utils import listed


class CustomGroup(click.Group):
    """ Custom Click Group """

    def list_commands(self, context: click.core.Context) -> List[str]:
        """ Prevent alphabetical sorting """
        return list(self.commands.keys())

    def get_command(self, context: click.core.Context, cmd_name: str) -> Optional[click.Command]:
        """ Allow command shortening """
        # Backward-compatible 'test convert' (just temporary for now FIXME)
        cmd_name = cmd_name.replace('convert', 'import')
        # Support both story & stories
        cmd_name = cmd_name.replace('story', 'stories')
        found = click.Group.get_command(self, context, cmd_name)
        if found is not None:
            return found
        matches = [command for command in self.list_commands(context)
                   if command.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, context, matches[0])
        context.fail('Did you mean {}?'.format(
            listed(sorted(matches), join='or')))
        return None
