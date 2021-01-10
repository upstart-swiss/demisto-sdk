import atexit
import json
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from threading import Lock
from typing import Optional, Union

import click
import requests
from demisto_sdk.commands.common.content.objects.abstract_objects import \
    TextObject
from demisto_sdk.commands.common.errors import Errors
from demisto_sdk.commands.common.hook_validations.base_validator import \
    BaseValidator
from demisto_sdk.commands.common.tools import get_content_path, run_command_os
from wcmatch.pathlib import Path

NO_HTML = '<!-- NOT_HTML_DOC -->'
YES_HTML = '<!-- HTML_DOC -->'

SECTIONS = [
    'Troubleshooting',
    'Use Cases',
    'Known Limitations',
    'Additional Information'
]

USER_FILL_SECTIONS = [
    'FILL IN REQUIRED PERMISSIONS HERE',
    'version xx'
]


class Readme(TextObject):
    # Static var to hold the mdx server process
    _MDX_SERVER_PROCESS: Optional[subprocess.Popen] = None
    _MDX_SERVER_LOCK = Lock()

    def __init__(self, path: Union[Path, str], base: BaseValidator = None):
        super().__init__(path)
        self.base = base if base else BaseValidator()
        self.content_path = get_content_path()
        self.node_modules_path = self.content_path / Path('node_modules')

    def validate(self):
        return self.is_valid_file()

    def is_valid_file(self) -> bool:
        """Check whether the readme file is valid or not
        Returns:
            bool: True if env configured else Fale.
        """
        return all([
            self.is_image_path_valid(),
            self.is_mdx_file(),
            self.verify_no_empty_sections(),
            self.verify_no_default_sections_left()
        ])

    def is_image_path_valid(self) -> bool:
        with open(str(self.path)) as f:
            readme_content = f.read()
        invalid_paths = re.findall(
            r'(\!\[.*?\]|src\=)(\(|\")(https://github.com/demisto/content/(?!raw).*?)(\)|\")', readme_content,
            re.IGNORECASE)
        if invalid_paths:
            for path in invalid_paths:
                path = path[2]
                alternative_path = path.replace('blob', 'raw')
                error_message, error_code = Errors.image_path_error(path, alternative_path)
                self.base.handle_error(error_message, error_code, file_path=self.path)
            return False
        return True

    def is_html_doc(self) -> bool:
        txt = ''
        with open(str(self.path), 'r') as f:
            txt = f.read(4096).strip()
        if txt.startswith(NO_HTML):
            return False
        if txt.startswith(YES_HTML):
            return True
        # use some heuristics to try to figure out if this is html
        return txt.startswith('<p>') or txt.startswith('<!DOCTYPE html>') or ('<thead>' in txt and '<tbody>' in txt)

    def is_mdx_file(self) -> bool:
        html = self.is_html_doc()
        valid = os.environ.get('DEMISTO_README_VALIDATION') or os.environ.get('CI') or \
            self.are_modules_installed_for_verify(self.content_path)
        if valid and not html:
            # add to env var the directory of node modules
            os.environ['NODE_PATH'] = str(self.node_modules_path) + os.pathsep + os.getenv("NODE_PATH", "")
            if os.getenv('DEMISTO_MDX_CMD_VERIFY'):
                return self.mdx_verify()
            else:
                return self.mdx_verify_server()
        return True

    @staticmethod
    @lru_cache(None)
    def are_modules_installed_for_verify(content_path: str) -> bool:
        """ Check the following:
            1. npm packages installed - see packs var for specific pack details.
            2. node interperter exists.
        Returns:
            bool: True If all req ok else False
        """
        missing_module = []
        valid = True
        # Check node exist
        stdout, stderr, exit_code = run_command_os('node -v', cwd=content_path)
        if exit_code:
            click.secho(f'There is no node installed on the machine, Test Skipped, error - {stderr}, {stdout}',
                        fg='yellow')
            valid = False
        else:
            # Check npm modules exsits
            packs = ['@mdx-js/mdx', 'fs-extra', 'commander']
            stdout, stderr, exit_code = run_command_os(f'npm ls --json {" ".join(packs)}', cwd=content_path)
            if exit_code:  # all are missinig
                missing_module.extend(packs)
            else:
                deps = json.loads(stdout).get('dependencies', {})
                for pack in packs:
                    if pack not in deps:
                        missing_module.append(pack)
        if missing_module:
            valid = False
            click.secho(f"The npm modules: {missing_module} are not installed, Readme mdx validation skipped. Use "
                        f"'npm install' to install all required node dependencies", fg='yellow')
        return valid

    def mdx_verify(self) -> bool:
        mdx_parse = Path(__file__).parent.parent / 'mdx-parse.js'
        with open(str(self.path), 'r') as f:
            readme_content = f.read()
        readme_content = self.fix_mdx(readme_content)
        with tempfile.NamedTemporaryFile('w+t') as fp:
            fp.write(readme_content)
            fp.flush()
            # run the javascript mdx parse validator
            _, stderr, is_not_valid = run_command_os(f'node {mdx_parse} -f {fp.name}', cwd=self.content_path,
                                                     env=os.environ)
        if is_not_valid:
            error_message, error_code = Errors.readme_error(stderr)
            if self.base.handle_error(error_message, error_code, file_path=self.path):
                return False
        return True

    @staticmethod
    def fix_mdx(txt: str) -> str:
        # copied from: https://github.com/demisto/content-docs/blob/2402bd1ab1a71f5bf1a23e1028df6ce3b2729cbb/content-repo/mdx_utils.py#L11
        # to use the same logic as we have in the content-docs build
        replace_tuples = [
            ('<br>(?!</br>)', '<br/>'),
            ('<hr>(?!</hr>)', '<hr/>'),
            ('<pre>', '<pre>{`'),
            ('</pre>', '`}</pre>'),
        ]
        for old, new in replace_tuples:
            txt = re.sub(old, new, txt, flags=re.IGNORECASE)
        # remove html comments
        txt = re.sub(r'<\!--.*?-->', '', txt, flags=re.DOTALL)
        return txt

    def verify_no_empty_sections(self) -> bool:
        """ Check that if the following headlines exists, they are not empty:
            1. Troubleshooting
            2. Use Cases
            3. Known Limitations
            4. Additional Information
        Returns:
            bool: True If all req ok else False
        """
        is_valid = True
        errors = ""
        with open(str(self.path)) as f:
            readme_content = f.read()
        for section in SECTIONS:
            found_section = re.findall(rf'(## {section}\n*)(-*\s*\n\n?)?(\s*.*)', readme_content, re.IGNORECASE)
            if found_section:
                line_after_headline = str(found_section[0][2])
                # checks if the line after the section's headline is another headline or empty
                if not line_after_headline or line_after_headline.startswith("##"):
                    # assuming that a sub headline is part of the section
                    if not line_after_headline.startswith("###"):
                        errors += f'{section} is empty, please elaborate or delete the section.\n'
                        is_valid = False

        if not is_valid:
            error_message, error_code = Errors.readme_error(errors)
            self.base.handle_error(error_message, error_code, file_path=self.path)

        return is_valid

    def verify_no_default_sections_left(self) -> bool:
        """ Check that there are no default leftovers such as:
            1. 'FILL IN REQUIRED PERMISSIONS HERE'.
            2. unexplicit version number - such as "version xx of".
        Returns:
            bool: True If all req ok else False
        """
        is_valid = True
        errors = ""
        with open(str(self.path)) as f:
            readme_content = f.read()
        for section in USER_FILL_SECTIONS:
            required_section = re.findall(rf'{section}', readme_content, re.IGNORECASE)
            if required_section:
                errors += f'Replace "{section}" with a suitable info.\n'
                is_valid = False

        if not is_valid:
            error_message, error_code = Errors.readme_error(errors)
            self.base.handle_error(error_message, error_code, file_path=self.path)

        return is_valid

    def mdx_verify_server(self) -> bool:
        if not Readme._MDX_SERVER_PROCESS:
            Readme.start_mdx_server()
        with open(str(self.path), 'r') as f:
            readme_content = f.read()
        readme_content = self.fix_mdx(readme_content)
        response = requests.post('http://localhost:6161', data=readme_content.encode('utf-8'), timeout=10)
        if response.status_code != 200:
            error_message, error_code = Errors.readme_error(response.text)
            if self.base.handle_error(error_message, error_code, file_path=self.path):
                return False
        return True

    @staticmethod
    def start_mdx_server():
        with Readme._MDX_SERVER_LOCK:
            if not Readme._MDX_SERVER_PROCESS:
                mdx_parse_server = Path(__file__).parent.parent / 'mdx-parse-server.js'
                Readme._MDX_SERVER_PROCESS = subprocess.Popen(['node', str(mdx_parse_server)],
                                                              stdout=subprocess.PIPE, text=True)
                line = Readme._MDX_SERVER_PROCESS.stdout.readline()  # type: ignore
                if 'MDX server is listening on port' not in line:
                    Readme.stop_mdx_server()
                    raise Exception(f'Failed starting mdx server. stdout: {line}.')

    @staticmethod
    def stop_mdx_server():
        if Readme._MDX_SERVER_PROCESS:
            Readme._MDX_SERVER_PROCESS.terminate()
            Readme._MDX_SERVER_PROCESS = None


atexit.register(Readme.stop_mdx_server)
