import os
import copy
import pytest
from mock import patch
import base64
import shutil
import yaml
import yamlordereddictloader

from demisto_sdk.common.tools import get_yaml

TEST_DIR_PATH = os.path.join('tests', 'tests_files', 'Unifier')

TEST_VALID_CODE = '''import demistomock as demisto
from CommonServerPython import *

def main():
    return_error('Not implemented.')
​
if __name__ in ('builtins', '__builtin__', '__main__'):
    main()
'''

TEST_VALID_DETAILED_DESCRIPTION = '''first line
second line

## header1
do the following:
1. say hello
2. say goodbye
'''

DUMMY_SCRIPT = '''
    def main():
    """ COMMANDS MANAGER / SWITCH PANEL """
        command = demisto.command()
        args = demisto.args()
        LOG(f'Command being called is {command}')

        params = demisto.params()
    

    try:
        if command == 'test-module':
            demisto.results('ok')
    except Exception as e:
        return_error(str(e))


    from MicrosoftApiModule import *  # noqa: E402

    if __name__ in ["builtins", "__main__"]:
        main()
    '''

DUMMY_MODULE = '''
import requests
import base64
from typing import Dict, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OPROXY_AUTH_TYPE = 'oproxy'
SELF_DEPLOYED_AUTH_TYPE = 'self_deployed'


class MicrosoftClient(BaseClient):

    def __init__(self, tenant_id: str = '', auth_id: str = '', enc_key: str = '',
                 token_retrieval_url: str = '', app_name: str = '', refresh_token: str = '',
                 client_id: str = '', client_secret: str = '', scope: str = '', resource: str = '', app_url: str = '',
                 verify: bool = True, auth_type: str = OPROXY_AUTH_TYPE, *args, **kwargs):
 
'''


def test_clean_python_code():
    from demisto_sdk.yaml_tools.unifier import Unifier
    unifier = Unifier("path")
    script_code = "import demistomock as demistofrom CommonServerPython import *" \
                  "from CommonServerUserPython import *from __future__ import print_function"
    # Test remove_print_future is False
    script_code = unifier.clean_python_code(script_code, remove_print_future=False)
    assert script_code == "from __future__ import print_function"
    # Test remove_print_future is True
    script_code = unifier.clean_python_code(script_code)
    assert script_code == ""


def test_get_code_file():
    from demisto_sdk.yaml_tools.unifier import Unifier
    # Test integration case
    unifier = Unifier("tests/test_files/VulnDB/")
    assert unifier.get_code_file(".py") == "tests/test_files/VulnDB/VulnDB.py"
    unifier = Unifier("tests/test_files")
    with pytest.raises(Exception):
        unifier.get_code_file(".py")
    # Test script case
    unifier = Unifier("tests/test_files/CalculateGeoDistance/")
    assert unifier.get_code_file(".py") == "tests/test_files/CalculateGeoDistance/CalculateGeoDistance.py"


def test_get_script_package_data():
    from demisto_sdk.yaml_tools.unifier import Unifier
    unifier = Unifier("tests/")
    with pytest.raises(Exception):
        unifier.get_script_package_data()
    unifier = Unifier("tests/test_files/CalculateGeoDistance")
    with open("tests/test_files/CalculateGeoDistance/CalculateGeoDistance.py", "r") as code_file:
        code = code_file.read()
    yml_path, code_data = unifier.get_script_package_data()
    assert yml_path == "tests/test_files/CalculateGeoDistance/CalculateGeoDistance.yml"
    assert code_data == code


def test_get_data():
    from demisto_sdk.yaml_tools.unifier import Unifier
    with patch.object(Unifier, "__init__", lambda a, b, c, d, e: None):
        unifier = Unifier('', None, None, None)
        unifier.package_path = "tests/test_files/VulnDB/"
        unifier.dir_name = "Integrations"
        with open("tests/test_files/VulnDB/VulnDB_image.png", "rb") as image_file:
            image = image_file.read()
        data, found_data_path = unifier.get_data("*png")
        assert data == image
        assert found_data_path == "tests/test_files/VulnDB/VulnDB_image.png"
        unifier.dir_name = "Scripts"
        data, found_data_path = unifier.get_data("*png")
        assert data is None
        assert found_data_path is None


def test_insert_description_to_yml():
    from demisto_sdk.yaml_tools.unifier import Unifier
    with patch.object(Unifier, "__init__", lambda a, b, c, d, e: None):
        unifier = Unifier('', None, None, None)
        unifier.package_path = "tests/test_files/VulnDB/"
        unifier.dir_name = "Integrations"
        with open("tests/test_files/VulnDB/VulnDB_description.md", "rb") as desc_file:
            desc_data = desc_file.read().decode("utf-8")
        yml_unified, found_data_path = unifier.insert_description_to_yml({}, {})

        assert found_data_path == "tests/test_files/VulnDB/VulnDB_description.md"
        assert desc_data == yml_unified['detaileddescription']


def test_insert_image_to_yml():
    from demisto_sdk.yaml_tools.unifier import Unifier
    with patch.object(Unifier, "__init__", lambda a, b, c, d, e: None):
        unifier = Unifier('', None, None, None)
        unifier.package_path = "tests/test_files/VulnDB/"
        unifier.dir_name = "Integrations"
        unifier.image_prefix = "data:image/png;base64,"
        with open("tests/test_files/VulnDB/VulnDB_image.png", "rb") as image_file:
            image_data = image_file.read()
            image_data = unifier.image_prefix + base64.b64encode(image_data).decode('utf-8')
        with open("tests/test_files/VulnDB/VulnDB.yml", mode="r", encoding="utf-8") as yml_file:
            yml_unified_test = yaml.load(yml_file, Loader=yamlordereddictloader.SafeLoader)
        with open("tests/test_files/VulnDB/VulnDB.yml", "r") as yml:
            yml_data = yaml.safe_load(yml)
        yml_unified, found_img_path = unifier.insert_image_to_yml(yml_data, yml_unified_test)
        yml_unified_test['image'] = image_data
        assert found_img_path == "tests/test_files/VulnDB/VulnDB_image.png"
        assert yml_unified == yml_unified_test


def test_check_api_module_imports():
    from demisto_sdk.yaml_tools.unifier import Unifier
    module_import, module_name = Unifier.check_api_module_imports(DUMMY_SCRIPT)

    assert module_import == 'from MicrosoftApiModule import *  # noqa: E402'
    assert module_name == 'MicrosoftApiModule'


@pytest.mark.parametrize('import_name', ['from MicrosoftApiModule import *  # noqa: E402',
                                         'from MicrosoftApiModule import *'])
def test_insert_module_code(mocker, import_name):
    from demisto_sdk.yaml_tools.unifier import Unifier
    mocker.patch.object(Unifier, '_get_api_module_code', return_value=DUMMY_MODULE)
    module_name = 'MicrosoftApiModule'
    new_code = DUMMY_SCRIPT.replace(import_name, '\n### GENERATED CODE ###\n# This code was inserted in place of an API'
                                                 ' module.{}\n'.format(DUMMY_MODULE))

    code = Unifier.insert_module_code(DUMMY_SCRIPT, import_name, module_name)

    assert code == new_code


@pytest.mark.parametrize('package_path, dir_name, file_path', [
    ("tests/test_files/VulnDB/", "Integrations", "tests/test_files/VulnDB/VulnDB"),
    ("tests/test_files/CalculateGeoDistance/", "Scripts",
     "tests/test_files/CalculateGeoDistance/CalculateGeoDistance")])
def test_insert_script_to_yml(package_path, dir_name, file_path):
    from demisto_sdk.yaml_tools.unifier import Unifier
    with patch.object(Unifier, "__init__", lambda a, b, c, d, e: None):
        unifier = Unifier("", None, None, None)
        unifier.package_path = package_path
        unifier.dir_name = dir_name
        with open(file_path + ".yml", "r") as yml:
            test_yml_data = yaml.safe_load(yml)

        test_yml_unified = copy.deepcopy(test_yml_data)

        yml_unified, script_path = unifier.insert_script_to_yml(".py", test_yml_unified, test_yml_data)

        with open(file_path + ".py", mode="r", encoding="utf-8") as script_file:
            script_code = script_file.read()
        clean_code = unifier.clean_python_code(script_code)

        if isinstance(test_yml_unified.get('script', {}), str):
            test_yml_unified['script'] = clean_code
        else:
            test_yml_unified['script']['script'] = clean_code

        assert yml_unified == test_yml_unified
        assert script_path == file_path + ".py"


@pytest.mark.parametrize('package_path, dir_name, file_path', [
    ("tests/test_files/VulnDB/", "Integrations", "tests/test_files/VulnDB/VulnDB"),
    ("tests/test_files/CalculateGeoDistance/", "Scripts",
     "tests/test_files/CalculateGeoDistance/CalculateGeoDistance"),
    ("tests/test_files/VulnDB/", "fake_directory", "tests/test_files/VulnDB/VulnDB")])
def test_insert_script_to_yml_exceptions(package_path, dir_name, file_path):
    from demisto_sdk.yaml_tools.unifier import Unifier
    with patch.object(Unifier, "__init__", lambda a, b, c, d, e: None):
        unifier = Unifier("", None, None, None)
        unifier.package_path = package_path
        unifier.dir_name = dir_name
        with open(file_path + ".yml", "r") as yml:
            test_yml_data = yaml.safe_load(yml)
        if dir_name == "Scripts":
            test_yml_data['script'] = 'blah'
        elif dir_name == "Integrations":
            test_yml_data['script']['script'] = 'blah'

        with pytest.raises(ValueError):
            unifier.insert_script_to_yml(".py", {}, test_yml_data)


def create_test_package(package_name, base_yml, script_code, detailed_description='', image_file=''):
    package_path = os.path.join(TEST_DIR_PATH, package_name)

    os.makedirs(package_path)
    shutil.copy(base_yml, os.path.join(package_path, f'{package_name}.yml'))

    with open(os.path.join(TEST_DIR_PATH, f'{package_name}.py')) as file_:
        file_.write(script_code)

    if detailed_description:
        with open(os.path.join(TEST_DIR_PATH, f'{package_name}_description.md')) as file_:
            file_.write(detailed_description)

    if image_file:
        shutil.copy(image_file, os.path.join(package_path, f'{package_name}_image.png'))

    pass


def test_unify_integration():
    """
    sanity test of merge_script_package_to_yml of integration
    """
    from demisto_sdk.yaml_tools.unifier import Unifier

    package_name = 'TestIntegPackage'
    export_dir_path = os.path.join(TEST_DIR_PATH, package_name)
    expected_yml_path = os.path.join(TEST_DIR_PATH, 'TestIntegPackage_unified.yml')

    create_test_package(
        package_name=package_name,
        base_yml='TestIntegPackage.yml',
        script_code=TEST_VALID_CODE,
        detailed_description=TEST_VALID_DETAILED_DESCRIPTION,
        image_file='/test_data',
    )

    unifier = Unifier(indir=export_dir_path)
    results = unifier.merge_script_package_to_yml()
    export_yml_path = results.keys()[0]

    assert export_yml_path == f'{export_dir_path}/integration-{package_name}.yml'
    actual_yml = get_yaml(export_yml_path)

    expected_yml = get_yaml(expected_yml_path)

    assert expected_yml == actual_yml


def test_unify_integration__detailed_description_with_special_char():
    """
    -
    """
    from demisto_sdk.yaml_tools.unifier import Unifier

    package_name = 'TestIntegPackage'
    export_dir_path = os.path.join(TEST_DIR_PATH, package_name)
    expected_yml_path = os.path.join(TEST_DIR_PATH, 'TestIntegPackage_unified.yml')

    create_test_package(
        package_name=package_name,
        base_yml='TestIntegPackage.yml',
        script_code=TEST_VALID_CODE,
        image_file='/test_data',
        detailed_description='''
    some test with special chars
    שלום
    hello
    你好
    ''',
    )

    unifier = Unifier(export_dir_path)
    results = unifier.merge_script_package_to_yml()
    export_yml_path = results.keys()[0]

    assert export_yml_path == f'{export_dir_path}/script-Test.yml'
    actual_yml = get_yaml(export_yml_path)

    expected_yml = get_yaml(expected_yml_path)

    assert expected_yml == actual_yml