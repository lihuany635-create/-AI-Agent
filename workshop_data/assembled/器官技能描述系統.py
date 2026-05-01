"""做一個器官技能描述系統："""
# ── 工坊組裝：器官技能描述系統 ──────────────────────────────────────────
# 組裝時間：2026-04-27T15:15:23
# 任務數：6

from dataclasses import dataclass, field
from jsonschema import validate, ValidationError
from pathlib import Path
from typing import Any, Dict, List, Tuple
from typing import Dict, Any, List
from typing import List, Dict, Any
from typing import Optional, Dict, Any
import argparse
import importlib.util
import inspect
import json
import os
import pathlib
import sys
import tempfile
import unittest

@dataclass
class OrganDescription:
    name: str
    function: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    example: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {'name': self.name, 'function': self.function, 'inputs': self.inputs, 'outputs': self.outputs, 'example': self.example}

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

def load_module_from_path(module_path: Path) -> Any:
    """Load a Python module from a given file path."""
    spec = importlib.util.spec_from_file_location(module_path.stem, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def extract_function_metadata(func: Any) -> Dict[str, Any]:
    """Extract metadata from a function."""
    sig = inspect.signature(func)
    parameters = {k: v.annotation for k, v in sig.parameters.items() if v.annotation is not inspect.Parameter.empty}
    return {'name': func.__name__, 'docstring': inspect.getdoc(func), 'annotations': parameters}

def generate_json_from_module(module_path: Path) -> Dict[str, Any]:
    """Generate a JSON-serializable dictionary from a Python module."""
    module = load_module_from_path(module_path)
    module_metadata = {'module_name': module.__name__, 'docstring': inspect.getdoc(module), 'functions': []}
    functions: List[Tuple[str, Any]] = inspect.getmembers(module, inspect.isfunction)
    for _, func in functions:
        module_metadata['functions'].append(extract_function_metadata(func))
    return module_metadata

def write_json_to_file(data: Dict[str, Any], output_path: Path) -> None:
    """Write the JSON data to the specified file."""
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def main() -> None:
    parser = argparse.ArgumentParser(description='Generate JSON metadata from a Python organ module.')
    parser.add_argument('module_file', type=Path, help='Path to the .py organ module.')
    parser.add_argument('-o', '--output', type=Path, help='Output JSON file path. Defaults to <module_name>.json in the same directory.')
    args = parser.parse_args()
    module_path = args.module_file.resolve()
    if not module_path.is_file():
        print(f'Error: File not found: {module_path}', file=sys.stderr)
        sys.exit(1)
    output_path = args.output or module_path.with_stem('.json')
    try:
        metadata = generate_json_from_module(module_path)
        write_json_to_file(metadata, output_path)
        print(f'Metadata written to {output_path}')
    except Exception as e:
        print(f'Error processing module: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

def process_directory(source_dir: Path, output_dir: Path | None=None, recursive: bool=False) -> None:
    """Scan a directory for .py files and generate JSON descriptions."""
    if not source_dir.is_dir():
        raise NotADirectoryError(f'Source directory does not exist: {source_dir}')
    pattern = '**/*.py' if recursive else '*.py'
    py_files = list(source_dir.glob(pattern))
    if not py_files:
        print(f'No .py files found in {source_dir}', file=sys.stderr)
        return
    for py_file in py_files:
        try:
            metadata = generate_json_from_module(py_file)
            out_path = output_dir / py_file.with_suffix('.json').name if output_dir else py_file.with_suffix('.json')
            out_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_to_file(metadata, out_path)
            print(f'Generated {out_path}')
        except Exception as exc:
            print(f'Failed to process {py_file}: {exc}', file=sys.stderr)

if __name__ == '__main__':
    main()

class OrganRegistry:

    def __init__(self, directory: str | pathlib.Path):
        self._directory = pathlib.Path(directory)
        if not self._directory.is_absolute():
            self._directory = pathlib.Path(os.path.abspath(self._directory))
        if not self._directory.exists():
            raise ValueError(f'Directory does not exist: {self._directory}')
        self._organ_map: Dict[str, Any] = {}
        self._load_all_organs()

    def _load_all_organs(self) -> None:
        for json_file in self._directory.glob('*.json'):
            try:
                organ_data = self._read_and_parse_json(json_file)
                if organ_data is not None:
                    name = organ_data.get('name')
                    if name:
                        self._organ_map[name.lower()] = organ_data
            except (json.JSONDecodeError, OSError):
                print(f'Warning: Failed to load or parse JSON file {json_file}')

    def _read_and_parse_json(self, json_file: pathlib.Path) -> Dict[str, Any] | None:
        try:
            with json_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError):
            print(f'Warning: Failed to load or parse JSON file {json_file}')
            return None

SCHEMA = {'type': 'object', 'properties': {'organ': {'type': 'string'}, 'function': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['healthy', 'diseased']}}, 'required': ['organ', 'function', 'status'], 'additionalProperties': False}

def validate_schema(data):
    """Validate data against the organ system schema."""
    validate(instance=data, schema=SCHEMA)

def generate_json(data):
    """Generate a pretty-printed JSON string from data."""
    return json.dumps(data, indent=2, sort_keys=True)

def load_registry(path):
    """Load a registry JSON file from the given path."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

_dispatcher_registry = {}

def register_handler(event_name, handler):
    """Register a handler function for a given event name."""
    _dispatcher_registry[event_name] = handler

def dispatch(event_name, *args, **kwargs):
    """Dispatch an event to the registered handler."""
    if event_name not in _dispatcher_registry:
        raise KeyError(f"No handler registered for event '{event_name}'")
    return _dispatcher_registry[event_name](*args, **kwargs)

class TestOrganSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.valid_data = {'organ': 'heart', 'function': 'pumping blood', 'status': 'healthy'}
        cls.invalid_data = {'organ': 'brain', 'status': 'healthy'}

    def test_validate_schema_with_valid_data(self):
        with self.assertRaises(ValidationError):
            validate_schema(self.invalid_data)
        try:
            validate_schema(self.valid_data)
        except ValidationError:
            self.fail('validate_schema raised ValidationError unexpectedly!')

    def test_validate_schema_with_invalid_data(self):
        with self.assertRaises(ValidationError):
            validate_schema(self.invalid_data)
        try:
            validate_schema(self.valid_data)
        except ValidationError:
            pass

    def test_generate_json_output(self):
        json_str = generate_json(self.valid_data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed, self.valid_data)

    def test_generate_json_format(self):
        json_str = generate_json(self.valid_data)
        self.assertIn('\n', json_str)
        self.assertIn('  ', json_str)

    def test_load_registry_success(self):
        registry_content = {'handler': 'process_organ'}
        with tempfile.NamedTemporaryFile('w+t', delete=False, suffix='.json') as tmp:
            json.dump(registry_content, tmp)
            tmp_path = tmp.name
        try:
            loaded = load_registry(tmp_path)
            self.assertEqual(loaded, registry_content)
        finally:
            os.remove(tmp_path)

    def test_load_registry_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_registry('non_existent_file.json')

    def test_dispatch_success(self):

        def dummy_handler(organ):
            return f'Processed {organ}'
        register_handler('process_organ', dummy_handler)
        result = dispatch('process_organ', 'liver')
        self.assertEqual(result, 'Processed liver')

    def test_dispatch_no_handler(self):
        with self.assertRaises(KeyError):
            dispatch('unknown_event')

    def test_dispatch_handler_arguments(self):

        def sum_handler(a, b):
            return a + b
        register_handler('sum', sum_handler)
        result = dispatch('sum', 3, 4)
        self.assertEqual(result, 7)

    def test_dispatch_handler_kwargs(self):

        def greet_handler(name, greeting='Hello'):
            return f'{greeting}, {name}!'
        register_handler('greet', greet_handler)
        result = dispatch('greet', 'Alice', greeting='Hi')
        self.assertEqual(result, 'Hi, Alice!')

if __name__ == '__main__':
    unittest.main()