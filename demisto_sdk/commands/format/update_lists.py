import traceback
from typing import Tuple

import click

from demisto_sdk.commands.format.format_constants import (ERROR_RETURN_CODE,
                                                          SKIP_RETURN_CODE,
                                                          SUCCESS_RETURN_CODE)
from demisto_sdk.commands.format.update_generic_json import BaseUpdateJSON

MIN_FROM_VERSION_LISTS = '6.5.0'


class ListsFormat(BaseUpdateJSON):

    def __init__(self,
                 input: str = '',
                 output: str = '',
                 path: str = 'list',
                 from_version: str = '',
                 no_validate: bool = False,
                 verbose: bool = False,
                 **kwargs):
        super().__init__(input=input, output=output, path=path, from_version=from_version, no_validate=no_validate,
                         verbose=verbose, **kwargs)

    def format_file(self) -> Tuple[int, int]:
        """Manager function for the list JSON updater."""
        format_res = self.run_format()
        if format_res:
            return format_res, SKIP_RETURN_CODE
        else:
            return format_res, self.initiate_file_validator()

    def run_format(self) -> int:
        try:
            click.secho(f'\n======= Updating file: {self.source_file} =======', fg='white')
            self.set_version_to_default()
            self.remove_unnecessary_keys()

            self.set_from_server_version_to_default()

            self.save_json_to_destination_file()
            return SUCCESS_RETURN_CODE
        except Exception as err:
            print(''.join(traceback.format_exception(etype=type(err), value=err, tb=err.__traceback__)))
            if self.verbose:
                click.secho(f'\nFailed to update file {self.source_file}. Error: {err}', fg='red')
            return ERROR_RETURN_CODE

    def set_from_server_version_to_default(self, location=None):
        """Replaces the fromVersion of the YML to default."""
        if self.verbose:
            click.echo(f'Trying to set JSON fromVersion to default: {MIN_FROM_VERSION_LISTS}')
        if location and not location.get('fromVersion'):
            location['fromVersion'] = MIN_FROM_VERSION_LISTS
        else:
            self.data.setdefault('fromVersion', MIN_FROM_VERSION_LISTS)