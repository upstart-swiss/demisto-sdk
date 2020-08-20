import json
import os
import shutil
from tempfile import mkdtemp

from demisto_sdk.commands.common.constants import (
    ENTITY_NAME_SEPARATORS, LAYOUTS_DIR, FileType)
from demisto_sdk.commands.common.tools import (LOG_COLORS, get_child_files,
                                               get_depth, get_json, get_yaml,
                                               print_color, find_type)
from demisto_sdk.commands.common.git_tools import git_path


class LayoutConverter:
    """
    LayoutConverter is a class that's designed to convert a local layout in content repository from old format
    to 6.0 format.

    Attributes:
        input_packs (list): The list of input packs to make conversions in
        pack_tempdirs (list): A dict of all corresponding pack temporary directories
    """

    def __init__(self, input: str):
        self.input_packs = list(input)
        self.pack_tempdirs: dict = {pack: mkdtemp() for pack in self.input_packs}
        self.schema_path: str = os.path.normpath(os.path.join(__file__, '..', '..', 'common/schemas/',
                                                              f'{FileType.LAYOUTS_CONTAINER.value}.yml'))
        self.schema_data: dict = get_yaml(self.schema_path)
        self.layout_dynamic_fields: list = [f for f, _ in self.schema_data.get('mapping').items() if
                                            self.schema_data.get('mapping').get(f).get('mapping')]
        self.layout_indicator_fields: list = [f for f in self.layout_dynamic_fields if 'indicator' in f]

    def convert(self) -> int:
        """
        Manages all conversions
        :return The exit code of each flow
        """
        if not self.verify_input_packs_is_pack():
            return 1
        for input_pack in self.input_packs:
            pack_layouts_path: str = os.path.join(input_pack, LAYOUTS_DIR)
            pack_layouts_tempdir_path: str = self.copy_layouts_to_tempdir(input_pack)
            pack_layouts_object: dict = self.build_pack_layouts_object(pack_layouts_tempdir_path)
            self.support_old_format(pack_layouts_tempdir_path, pack_layouts_object)
            self.support_new_format(pack_layouts_tempdir_path, pack_layouts_object)
            self.replace_layouts_dir(pack_layouts_tempdir_path, pack_layouts_path)
        self.remove_traces()
        return 0

    def copy_layouts_to_tempdir(self, input_pack_path: str) -> str:
        try:
            pack_tempdir_path = self.pack_tempdirs.get(input_pack_path)
            pack_layouts_tempdir_path = os.path.join(pack_tempdir_path, LAYOUTS_DIR)
            shutil.copytree(src=os.path.join(input_pack_path, LAYOUTS_DIR), dst=pack_layouts_tempdir_path)
            return pack_layouts_tempdir_path
        except shutil.Error as e:
            print(f'Shutil Error: {str(e)}')

    def build_pack_layouts_object(self, pack_layouts_tempdir_path) -> dict:
        pack_layouts_object: dict = dict()
        files = get_child_files(pack_layouts_tempdir_path)

        for file_path in files:
            file_data = get_json(file_path)
            if find_type(path=file_path, _dict=file_data, file_type='json') == FileType.LAYOUT:
                layout_version = self.get_layout_version(file_data)
                layout_id = self.get_layout_id(file_data, layout_version)
                file_object = {'path': file_path, 'version': layout_version}
                is_old_version = layout_version == '<6.0'
                is_new_version = layout_version == '>=6.0'

                if layout_id in pack_layouts_object:
                    pack_layouts_object[layout_id]['files'].append(file_object)
                    pack_layouts_object[layout_id]['>=6.0_exist'] = pack_layouts_object[layout_id]['>=6.0_exist'] \
                                                                    or is_new_version
                    pack_layouts_object[layout_id]['<6.0_exist'] = pack_layouts_object[layout_id]['<6.0_exist'] \
                                                                   or is_old_version
                else:
                    pack_layouts_object[layout_id] = {
                        'files': [file_object],
                        '>=6.0_exist': is_new_version,
                        '<6.0_exist': is_old_version
                    }

        return pack_layouts_object

    def support_old_format(self, pack_layouts_tempdir_path, pack_layouts_object):
        for layout_id, layout_object in pack_layouts_object.items():
            if layout_object['>=6.0_exist']:
                new_layout = self.get_new_layout(layout_object, layout_id)
                new_layout_data = new_layout.get('data')
                dynamic_fields, static_fields = self.get_layout_fields(new_layout_data)
                for key, value in dynamic_fields.items():
                    if not self.is_kind_layout_exist(key, layout_object):
                        old_layout_temp_path = self.create_old_layout(key, value, static_fields,
                                                                      pack_layouts_tempdir_path, layout_id)
                        pack_layouts_object[layout_id]['files'].append({
                            'path': old_layout_temp_path,
                            'version': '<6.0'
                        })
                        pack_layouts_object[layout_id]['<6.0_exist'] = True

                    else:
                        # @TODO: might not be needed
                        # self.update_old_layout({key: value}, static_fields, layout_id)
                        pass

    def get_layout_fields(self, new_layout_data: dict):
        dynamic_fields: dict = dict()
        static_fields: dict = dict()
        for key, value in new_layout_data.items():
            # Check if it's a kind section
            if key in self.layout_dynamic_fields:
                dynamic_fields[key] = value
            else:
                static_fields[key] = value
        return dynamic_fields, static_fields

    def is_kind_layout_exist(self, kind_field_key, layout_object):
        """
        @TODO:
        :param layout_object: @TODO:
        :param kind_field_key: @TODO:
        :return: @TODO:
        """
        old_layouts_data: list = [ol.get('data') for ol in self.get_old_layouts(layout_object)]
        return any(kind_field_key in old_layout_data for old_layout_data in old_layouts_data)

    def create_old_layout(self, key, value, non_kind_fields, layouts_tempdir_path, layout_id):
        """
        @TODO:
        :param key: @TODO:
        :param value: @TODO:
        :param non_kind_fields: @TODO:
        :param layouts_tempdir_path: @TODO:
        :param layout_id: @TODO:
        :return: @TODO:
        """
        data: dict = dict()
        data['kind'] = key
        data['layout'] = self.build_section_layout(key, value, non_kind_fields, layout_id)
        data['fromVersion'] = '4.1.0'
        data['toVersion'] = '5.0.0'
        data['typeId'] = self.get_layout_type_id(value, non_kind_fields)
        data['version'] = -1

        old_layout_basename: str = layout_id
        for separator in ENTITY_NAME_SEPARATORS:
            old_layout_basename = old_layout_basename.replace(separator, '_')
        old_layout_basename = f'{FileType.LAYOUT.value}-{key}-{old_layout_basename}.json'
        old_layout_temp_path: str = os.path.join(layouts_tempdir_path, old_layout_basename)
        with open(old_layout_temp_path, 'w') as jf:
            json.dump(obj=data, fp=jf)

        return old_layout_temp_path

    def build_section_layout(self, key, value, non_kind_fields, layout_id):
        """
        @TODO:
        :param key: @TODO:
        :param value: @TODO:
        :param layout_id: @TODO:
        :param non_kind_fields: @TODO:
        :return: @TODO:
        """
        section_layout: dict = dict()
        section_layout['id'] = layout_id
        section_layout['version'] = -1
        section_layout['kind'] = key
        section_layout['typeId'] = self.get_layout_type_id(value, non_kind_fields)
        if value and isinstance(value, dict):
            section_layout.update(value)
        return section_layout

    @staticmethod
    def get_layout_type_id(value, non_kind_fields):
        """
        @TODO:
        :param value: @TODO:
        :param non_kind_fields: @TODO:
        :return: @TODO:
        """
        return str()

    @staticmethod
    def update_old_layout(kind_field, non_kind_fields, layout_id):
        """
        @TODO:
        :param kind_field: @TODO:
        :param non_kind_fields: @TODO:
        :param layout_id: @TODO:
        :return: @TODO:
        """
        pass

    def support_new_format(self, pack_layouts_tempdir_path, pack_layouts_object):
        for layout_id, layout_object in pack_layouts_object.items():
            old_layouts = self.get_old_layouts(layout_object)
            if not layout_object['>=6.0_exist']:
                new_layout_temp_path = self.create_new_layout(layout_id, pack_layouts_tempdir_path)
                pack_layouts_object[layout_id]['files'].append({'path': new_layout_temp_path, 'version': '>=6.0'})
                pack_layouts_object[layout_id]['>=6.0_exist'] = True
                self.update_new_layout(layout_object, layout_id, old_layouts)
            else:
                self.update_new_layout(layout_object, layout_id, old_layouts)
            self.update_old_layouts(old_layouts)

    @staticmethod
    def replace_layouts_dir(pack_layouts_tempdir_path, pack_layouts_path):
        # Switch between the layouts temp dir to original one
        try:
            shutil.rmtree(pack_layouts_path)
            shutil.move(src=pack_layouts_tempdir_path, dst=pack_layouts_path)
        except shutil.Error as e:
            print(f'Shutil Error: {str(e)}')

    @staticmethod
    def get_layout_id(layout_data: dict, layout_version: str):
        if layout_version == '<6.0':
            return layout_data.get('layout', {}).get('id')
        return layout_data.get('id')

    @staticmethod
    def get_layout_version(layout_data: dict):
        if 'layout' in layout_data:
            return '<6.0'
        return '>=6.0'

    @staticmethod
    def update_old_layouts(old_layouts):
        for layout in old_layouts:
            data = layout.get('data')
            path = layout.get('file_object', {}).get('path')
            if 'toVersion' not in data:
                data["toVersion"] = "5.9.9"
            if 'fromVersion' not in data:
                data["fromVersion"] = "4.1.0"
            # TODO: Check if more fields are needed
            json_depth: int = get_depth(data)
            with open(path, 'w') as jf:
                json.dump(obj=data, fp=jf, indent=json_depth)

    @staticmethod
    def create_new_layout(layout_id, layouts_tempdir_path):
        data = dict()
        data["fromVersion"] = "6.0.0"
        data["group"] = ""  # to be defined in update_new_layout
        data["name"] = layout_id
        data["id"] = layout_id
        data["version"] = -1

        new_layout_basename = layout_id
        for separator in ENTITY_NAME_SEPARATORS:
            new_layout_basename = new_layout_basename.replace(separator, '_')
        new_layout_basename = f'{FileType.LAYOUTS_CONTAINER.value}-{new_layout_basename}.json'
        new_layout_temp_path = os.path.join(layouts_tempdir_path, new_layout_basename)
        with open(new_layout_temp_path, 'w') as jf:
            json.dump(obj=data, fp=jf)

        return new_layout_temp_path

    def update_new_layout(self, layout_object, layout_id, old_layouts):
        new_layout: dict = self.get_new_layout(layout_object, layout_id)
        new_layout_path: str = new_layout.get('file_object').get('path')
        data: dict = new_layout.get('data')
        is_group_indicator: bool = False

        for old_layout in old_layouts:
            old_data = old_layout.get('data')
            old_layout_kind = old_data.get('kind')

            if old_layout_kind:
                # Update group field
                is_group_indicator = is_group_indicator or old_layout_kind in self.layout_indicator_fields
                if is_group_indicator and not data['group']:
                    data['group'] = 'indicator'

                # Update dynamic fields
                if sections := old_data.get('layout', {}).get('sections', []):
                    data[old_layout_kind] = {'sections': sections}
                if tabs := old_data.get('layout', {}).get('tabs', []):
                    data[old_layout_kind] = {'tabs': tabs}
                if fields := old_data.get('layout', {}).get('fields', []):
                    data[old_layout_kind] = {'fields': fields}

        # Update group field
        if not is_group_indicator:
            data['group'] = 'incident'

        json_depth: int = get_depth(data)
        with open(new_layout_path, 'w') as jf:
            json.dump(obj=data, fp=jf, indent=json_depth)

    @staticmethod
    def get_old_layouts(layout_object) -> list:
        return [{'file_object': file_object, 'data': get_json(file_object.get('path'))}
                for file_object in layout_object.get('files', []) if file_object.get('version') == '<6.0']

    @staticmethod
    def get_new_layout(layout_object, layout_id) -> dict:
        new_layout: dict = dict()
        num_new_layouts = 0

        for file_object in layout_object.get('files', []):
            if file_object.get('version') == '>=6.0':
                new_layout = file_object
                num_new_layouts += 1

        if num_new_layouts != 1:
            # @TODO: Think if need to raise here
            raise Exception(f'Error: Found more than 1 new 6.0 format layout with id: {layout_id}')

        return {'file_object': new_layout, 'data': get_json(new_layout.get('path'))}

    def remove_traces(self):
        """
        Removes (recursively) all temporary files & directories used across the module
        """
        try:
            for _, pack_tempdir in self.pack_tempdirs.items():
                shutil.rmtree(pack_tempdir, ignore_errors=True)
        except shutil.Error as e:
            print_color(e, LOG_COLORS.RED)
            raise

    def verify_input_packs_is_pack(self) -> bool:
        """
        Verifies the input pack paths entered by the user are an actual pack path in content repository.
        :return: The verification result
        """
        input_packs_path_list: list = self.input_packs
        ans: bool = True
        err_msg: str = str()
        for input_pack_path in input_packs_path_list:
            if not (os.path.isdir(input_pack_path) and
                    os.path.basename(os.path.dirname(os.path.abspath(input_pack_path))) == 'Packs' and
                    os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(input_pack_path)))) == 'content'):
                err_msg += f'{input_pack_path},'
                ans = ans and False
        if not ans:
            print_color(f"{err_msg.strip(',')} don't have the format of a valid pack path. The designated output "
                        f"pack's path is of format ~/.../content/Packs/$PACK_NAME", LOG_COLORS.RED)
        return ans
