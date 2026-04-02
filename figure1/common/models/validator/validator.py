import jsonschema
import json
import os

DEFINITIONS = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'definitions')
SCHEMAS = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'schemas')


class SchemaNotFound(Exception):
    def __init__(self, *args, **kwargs):
        pass


class Validate:
    def __init__(self):
        self._schemas = self._load_schemas()
        self.resolver = jsonschema.RefResolver(
            '',
            {},
            store={
                schema['id']: schema
                for schema in self._schemas
            }
        )
        self.format_checker = jsonschema.FormatChecker()

    def _lookup_schema(self, json_schema):
        for schema in self._schemas:
            if schema['id'] == json_schema:
                return schema
        else:
            return None

    def _get_schemas(self):
        schema_list = []
        for base_dir, dirs, files in os.walk(SCHEMAS):
            for file in files:
                if file.endswith('.json'):
                    schema_list.append(os.path.join(base_dir, file))
                    yield os.path.join(base_dir, file)

    def _get_definitions(self):
        schema_list = []
        for base_dir, dirs, files in os.walk(DEFINITIONS):
            for file in files:
                if file.endswith('.json'):
                    schema_list.append(os.path.join(base_dir, file))
                    yield os.path.join(base_dir, file)

    def _load_schemas(self):
        schemas = []
        for schema in self._get_schemas():
            schemas.append(self._load_json_from_file(schema))
        for definition in self._get_definitions():
            schemas.append(self._load_json_from_file(definition))
        return schemas

    def _load_json_from_file(self, path):
        with open(path) as file_in:
            return json.load(file_in)

    def validate(self, json_data, json_schema):
        schema = self._lookup_schema(json_schema)
        if not schema:
            raise SchemaNotFound
        return jsonschema.validate(
            json_data,
            schema,
            resolver=self.resolver,
            format_checker=self.format_checker)
