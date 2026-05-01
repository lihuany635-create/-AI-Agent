"""**工程需求（≤200字）**"""
# ── 工坊組裝：管道模式器官 ──────────────────────────────────────────
# 組裝時間：2026-04-28T09:10:57
# 任務數：7

from abc import ABC, abstractmethod
from collections import defaultdict
from collections import defaultdict, deque
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from typing import Any, Dict, Iterable, List, Set
from typing import Any, Dict, Iterable, List, Set, Type
from typing import Callable, Dict, List, Any
import argparse
import asyncio
import importlib
import json
import logging
import sys
import threading
import unittest

class Skill(ABC):
    """
    Abstract base class for all skills.

    Subclasses must implement the `execute` method which receives an input
    of any type and returns any type. Basic validation ensures that the
    input is not None; subclasses may extend this validation as needed.
    """

    @abstractmethod
    def execute(self, input: Any) -> Any:
        """
        Execute the skill logic.

        Parameters
        ----------
        input : Any
            Input data for the skill. Must not be None.

        Returns
        -------
        Any
            Result of the skill execution.
        """
        if input is None:
            raise ValueError('Input to Skill.execute cannot be None')
        pass

try:
    from skill_interface import Skill
except Exception:

    class Skill(ABC):

        @abstractmethod
        def execute(self, inputs: Any) -> Any:
            """Execute the skill logic."""
            pass

def add_node(self, skill: Skill) -> None:
    """Add a Skill node to the pipeline.
    1. Check if the node already exists in the set of nodes.
    2. Add the node to the set of nodes.
    3. Initialize adjacency entries for both outgoing and incoming edges.
    """
    if skill not in self._nodes:
        self._nodes.add(skill)
        self._adj[skill] = set()
        self._rev_adj[skill] = set()

def remove_node(self, skill: Skill) -> None:
    """Remove a Skill node and all associated edges.
    1. Check if the node exists in the set of nodes.
    2. Remove outgoing edges by iterating over list copies to avoid runtime modification issues.
    3. Remove incoming edges similarly.
    4. Delete adjacency entries for the node from both `_adj` and `_rev_adj`.
    5. Remove the node from the set of nodes.
    """
    if skill in self._nodes:
        for adj_skill in list(self._adj[skill]):
            self.remove_edge(skill, adj_skill)
        for rev_adj_skill in list(self._rev_adj[skill]):
            self.remove_edge(rev_adj_skill, skill)
        del self._adj[skill]
        del self._rev_adj[skill]
        self._nodes.remove(skill)

def add_edge(self, src: Skill, dst: Skill) -> None:
    """Add a directed edge from src to dst, ensuring the graph remains acyclic.
    1. Check if both nodes are in the set of nodes.
    2. Raise ValueError if the edge already exists.
    3. Raise ValueError if adding this edge would create a cycle using `_has_path` method.
    """
    if src not in self._nodes or dst not in self._nodes:
        raise ValueError('Both nodes must be added to the pipeline before creating an edge.')
    if dst in self._adj[src]:
        raise ValueError(f'Edge from {src} to {dst} already exists.')
    if self._has_path(dst, src):
        raise ValueError(f'Adding this edge would create a cycle (path from {dst} to {src} exists).')
    self._adj[src].add(dst)
    self._rev_adj[dst].add(src)

self._adj: Dict[Skill, Set[Skill]] = defaultdict(set)

self._rev_adj: Dict[Skill, Set[Skill]] = defaultdict(set)

async def load_skill(self, skill_name):
    try:
        module = await importlib.import_module(f'skills.{skill_name}')
        skill_class = getattr(module, skill_name)
        return skill_class()
    except ImportError as e:
        logger.error(f'Failed to load skill {skill_name}: {e}', exc_info=True)
        return None

async def _execute_node(self, node: Skill, input_data: Any) -> None:
    cfg = self._config[node]
    attempt = 0
    while True:
        try:
            start = asyncio.get_event_loop().time()
            if asyncio.iscoroutinefunction(node.execute):
                result = await asyncio.wait_for(node.execute(input_data), cfg.timeout)
            else:
                result = await asyncio.to_thread(node.execute, input_data)
            elapsed = asyncio.get_event_loop().time() - start
            logger.info(f'Skill {node.__class__.__name__} executed in {elapsed:.3f}s. Input: {input_data!r} Output: {result!r}')
            self._outputs[node] = result
            break
        except Exception as exc:
            attempt += 1
            logger.error(f'Error executing skill {node.__class__.__name__} (attempt {attempt}/{cfg.retry + 1}): {exc}', exc_info=True)
            if attempt > cfg.retry:
                if cfg.skip_on_failure:
                    logger.warning(f'Skipping skill {node.__class__.__name__} after {cfg.retry + 1} attempts.')
                    self._outputs[node] = None
                    break
                else:
                    raise
        if attempt > cfg.retry:
            break

@dataclass
class NodeConfig:
    timeout: float = 30.0
    retry: int = 0
    skip_on_failure: bool = True

class Pipeline:

    def __init__(self):
        self._nodes: Set[Skill] = set()
        self._adj: Dict[Skill, Set[Skill]] = defaultdict(set)
        self._rev_adj: Dict[Skill, Set[Skill]] = defaultdict(set)
        self._config: Dict[Skill, NodeConfig] = {}
        self._outputs: Dict[Skill, Any] = {}
        self._logger = self._get_logger()

    @staticmethod
    def _get_logger() -> logging.Logger:
        try:
            from agent_logger import get_logger
            return get_logger(__name__)
        except Exception:
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            return logger

    def add_node(self, skill: Skill, config: NodeConfig=None) -> None:
        if skill not in self._nodes:
            self._nodes.add(skill)
            self._adj[skill] = set()
            self._rev_adj[skill] = set()
            self._config[skill] = config or NodeConfig()

    def remove_node(self, skill: Skill) -> None:
        if skill in self._nodes:
            for nxt in list(self._adj[skill]):
                self.remove_edge(skill, nxt)
            for prev in list(self._rev_adj[skill]):
                self.remove_edge(prev, skill)
            del self._adj[skill]
            del self._rev_adj[skill]
            self._nodes.remove(skill)
            self._config.pop(skill, None)
            self._outputs.pop(skill, None)

    def add_edge(self, src: Skill, dst: Skill) -> None:
        if src not in self._nodes or dst not in self._nodes:
            raise ValueError('Both nodes must be added before creating an edge.')
        if dst in self._adj[src]:
            raise ValueError(f'Edge from {src} to {dst} already exists.')
        if self._has_path(dst, src):
            raise ValueError('Adding this edge would create a cycle.')
        self._adj[src].add(dst)
        self._rev_adj[dst].add(src)

    def remove_edge(self, src: Skill, dst: Skill) -> None:
        self._adj[src].discard(dst)
        self._rev_adj[dst].discard(src)

    def _has_path(self, start: Skill, end: Skill) -> bool:
        visited = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == end:
                return True
            if node not in visited:
                visited.add(node)
                stack.extend(self._adj[node])
        return False

    async def _execute_node(self, node: Skill, input_data: Any) -> None:
        cfg = self._config[node]
        attempt = 0
        while True:
            try:
                start_time = asyncio.get_event_loop().time()
                if asyncio.iscoroutinefunction(node.execute):
                    result = await asyncio.wait_for(node.execute(input_data), cfg.timeout)
                else:
                    result = await asyncio.to_thread(node.execute, input_data)
                elapsed = asyncio.get_event_loop().time() - start_time
                self._logger.info(f'[{node.__class__.__name__}] Input: {input_data!r} | Output: {result!r} | Time: {elapsed:.3f}s')
                self._outputs[node] = result
                break
            except Exception as exc:
                attempt += 1
                self._logger.error(f'[{node.__class__.__name__}] Error on attempt {attempt}/{cfg.retry + 1}: {exc}', exc_info=True)
                if attempt > cfg.retry:
                    if cfg.skip_on_failure:
                        self._logger.warning(f'[{node.__class__.__name__}] Skipping after {cfg.retry + 1} attempts.')
                        self._outputs[node] = None
                        break
                    else:
                        raise

    async def run(self, initial_inputs: Dict[Skill, Any]=None) -> Dict[Skill, Any]:
        initial_inputs = initial_inputs or {}
        indegree = {node: len(self._rev_adj[node]) for node in self._nodes}
        queue = deque([node for node in self._nodes if indegree[node] == 0])
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in self._adj[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(self._nodes):
            raise RuntimeError('Pipeline has a cycle.')
        for node in order:
            preds = self._rev_adj[node]
            if preds:
                inputs = [self._outputs[p] for p in preds]
                if len(inputs) == 1:
                    input_data = inputs[0]
                else:
                    input_data = inputs
            else:
                input_data = initial_inputs.get(node, None)
            await self._execute_node(node, input_data)
        return self._outputs

def parse_json_config(path: str) -> Pipeline:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    pipeline = Pipeline()
    skills = {}
    for node_def in data.get('nodes', []):
        mod = node_def['module']
        cls = node_def['class']
        cfg_dict = node_def.get('config', {})
        cfg = NodeConfig(**cfg_dict)
        skill = asyncio.run(load_skill(mod, cls))
        pipeline.add_node(skill, cfg)
        skills[node_def['id']] = skill
    for edge in data.get('edges', []):
        src_id, dst_id = edge
        pipeline.add_edge(skills[src_id], skills[dst_id])
    return (pipeline, skills)

def main():
    parser = argparse.ArgumentParser(description='Dynamic Skill Pipeline')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to JSON pipeline config.')
    parser.add_argument('-i', '--inputs', type=str, default='{}', help='JSON string of initial inputs.')
    args = parser.parse_args()
    try:
        pipeline, skills = parse_json_config(args.config)
    except Exception as exc:
        logging.getLogger(__name__).error(f'Failed to build pipeline: {exc}', exc_info=True)
        sys.exit(1)
    try:
        initial_inputs = json.loads(args.inputs)
    except json.JSONDecodeError as e:
        logging.getLogger(__name__).error(f'Invalid inputs JSON: {e}', exc_info=True)
        sys.exit(1)
    init_map = {}
    for key, val in initial_inputs.items():
        if key in skills:
            init_map[skills[key]] = val
        else:
            logging.getLogger(__name__).warning(f'Input key {key} not found in pipeline nodes.')
    asyncio.run(pipeline.run(init_map))

if __name__ == '__main__':
    main()

if __name__ == '__main__':
    main()

class UpperCaseSkill(Skill):

    def run(self, data: str) -> str:
        return data.upper()

class ReverseSkill(Skill):

    def run(self, data: str) -> str:
        return data[::-1]

class AppendSkill(Skill):

    def __init__(self, suffix: str):
        self.suffix = suffix

    def run(self, data: str) -> str:
        return data + self.suffix

SKILL_REGISTRY: Dict[str, Callable[..., Skill]] = {'uppercase': lambda: UpperCaseSkill(), 'reverse': lambda: ReverseSkill(), 'append': lambda suffix: AppendSkill(suffix)}

class PipelineManager:

    def __init__(self):
        self._skills: List[Skill] = []
        self._skill_names: List[str] = []

    def add_skill(self, name: str, constructor: Callable[..., Skill], position: int=None, **kwargs):
        if name in self._skill_names:
            raise ValueError(f"Skill '{name}' already exists in the pipeline.")
        skill = constructor(**kwargs)
        if position is None:
            self._skills.append(skill)
            self._skill_names.append(name)
        else:
            if not 0 <= position <= len(self._skills):
                raise IndexError('Position out of bounds.')
            self._skills.insert(position, skill)
            self._skill_names.insert(position, name)

    def remove_skill(self, name: str):
        if name not in self._skill_names:
            raise ValueError(f"Skill '{name}' not found in the pipeline.")
        idx = self._skill_names.index(name)
        del self._skills[idx]
        del self._skill_names[idx]

    def reorder_skill(self, name: str, new_position: int):
        if name not in self._skill_names:
            raise ValueError(f"Skill '{name}' not found in the pipeline.")
        if not 0 <= new_position < len(self._skills):
            raise IndexError('New position out of bounds.')
        idx = self._skill_names.index(name)
        skill = self._skills.pop(idx)
        name_item = self._skill_names.pop(idx)
        self._skills.insert(new_position, skill)
        self._skill_names.insert(new_position, name_item)

    def run(self, data: Any) -> Any:
        result = data
        for skill in self._skills:
            result = skill.run(result)
        return result

    def list_skills(self) -> List[str]:
        return list(self._skill_names)

def cli():
    parser = argparse.ArgumentParser(description='Dynamic Pipeline Manager CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)
    add_parser = subparsers.add_parser('add', help='Add a skill to the pipeline')
    add_parser.add_argument('name', help='Unique name for the skill instance')
    add_parser.add_argument('skill_type', help='Type of skill to add', choices=SKILL_REGISTRY.keys())
    add_parser.add_argument('--position', type=int, default=None, help='Position to insert the skill')
    add_parser.add_argument('--suffix', help='Suffix for append skill')
    remove_parser = subparsers.add_parser('remove', help='Remove a skill from the pipeline')
    remove_parser.add_argument('name', help='Name of the skill to remove')
    reorder_parser = subparsers.add_parser('reorder', help='Reorder a skill in the pipeline')
    reorder_parser.add_argument('name', help='Name of the skill to reorder')
    reorder_parser.add_argument('position', type=int, help='New position for the skill')
    run_parser = subparsers.add_parser('run', help='Run the pipeline on input data')
    run_parser.add_argument('input', help='Input data (string)')
    list_parser = subparsers.add_parser('list', help='List current skills in the pipeline')
    args = parser.parse_args()
    manager = PipelineManager()
    state_file = 'pipeline_state.json'
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            for entry in state.get('skills', []):
                name = entry['name']
                skill_type = entry['skill_type']
                position = entry.get('position')
                kwargs = entry.get('kwargs', {})
                manager.add_skill(name, SKILL_REGISTRY[skill_type], position, **kwargs)
    except FileNotFoundError:
        pass
    try:
        if args.command == 'add':
            kwargs = {}
            if args.skill_type == 'append':
                if not args.suffix:
                    raise ValueError('Append skill requires --suffix')
                kwargs['suffix'] = args.suffix
            manager.add_skill(args.name, SKILL_REGISTRY[args.skill_type], args.position, **kwargs)
            print(f"Added skill '{args.name}' of type '{args.skill_type}'.")
        elif args.command == 'remove':
            manager.remove_skill(args.name)
            print(f"Removed skill '{args.name}'.")
        elif args.command == 'reorder':
            manager.reorder_skill(args.name, args.position)
            print(f"Moved skill '{args.name}' to position {args.position}.")
        elif args.command == 'run':
            result = manager.run(args.input)
            print(f'Result: {result}')
        elif args.command == 'list':
            print('Current pipeline:')
            for idx, name in enumerate(manager.list_skills()):
                print(f'  {idx}: {name}')
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    state = {'skills': [{'name': name, 'skill_type': next((k for k, v in SKILL_REGISTRY.items() if isinstance(manager._skills[idx], v())), None), 'position': idx, 'kwargs': getattr(manager._skills[idx], '__dict__', {})} for idx, name in enumerate(manager.list_skills())]}
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)

def create_app():
    from flask import Flask, request, jsonify
    app = Flask(__name__)
    manager = PipelineManager()

    @app.route('/add', methods=['POST'])
    def add():
        data = request.get_json()
        name = data['name']
        skill_type = data['skill_type']
        position = data.get('position')
        kwargs = data.get('kwargs', {})
        if skill_type not in SKILL_REGISTRY:
            return (jsonify({'error': 'Unknown skill type'}), 400)
        try:
            manager.add_skill(name, SKILL_REGISTRY[skill_type], position, **kwargs)
            return (jsonify({'status': 'added'}), 200)
        except Exception as e:
            return (jsonify({'error': str(e)}), 400)

    @app.route('/remove', methods=['POST'])
    def remove():
        data = request.get_json()
        name = data['name']
        try:
            manager.remove_skill(name)
            return (jsonify({'status': 'removed'}), 200)
        except Exception as e:
            return (jsonify({'error': str(e)}), 400)

    @app.route('/reorder', methods=['POST'])
    def reorder():
        data = request.get_json()
        name = data['name']
        position = data['position']
        try:
            manager.reorder_skill(name, position)
            return (jsonify({'status': 'reordered'}), 200)
        except Exception as e:
            return (jsonify({'error': str(e)}), 400)

    @app.route('/run', methods=['POST'])
    def run():
        data = request.get_json()
        input_data = data['input']
        try:
            result = manager.run(input_data)
            return (jsonify({'result': result}), 200)
        except Exception as e:
            return (jsonify({'error': str(e)}), 400)

    @app.route('/list', methods=['GET'])
    def list_skills():
        return (jsonify({'skills': manager.list_skills()}), 200)
    return app

class TestPipelineManager(unittest.TestCase):

    def setUp(self):
        self.manager = PipelineManager()
        self.manager.add_skill('upper', SKILL_REGISTRY['uppercase'])
        self.manager.add_skill('rev', SKILL_REGISTRY['reverse'])
        self.manager.add_skill('app', SKILL_REGISTRY['append'], suffix='_END')

    def test_run(self):
        result = self.manager.run('hello')
        self.assertEqual(result, 'OLLEH_END')

    def test_add_duplicate(self):
        with self.assertRaises(ValueError):
            self.manager.add_skill('upper', SKILL_REGISTRY['uppercase'])

    def test_remove(self):
        self.manager.remove_skill('rev')
        self.assertNotIn('rev', self.manager.list_skills())
        with self.assertRaises(ValueError):
            self.manager.remove_skill('rev')

    def test_reorder(self):
        self.manager.reorder_skill('app', 0)
        self.assertEqual(self.manager.list_skills(), ['app', 'upper', 'rev'])
        with self.assertRaises(IndexError):
            self.manager.reorder_skill('app', 5)

    def test_invalid_position(self):
        with self.assertRaises(IndexError):
            self.manager.add_skill('new', SKILL_REGISTRY['uppercase'], position=5)

class TestCLI(unittest.TestCase):

    def test_cli_add_and_list(self):
        manager = PipelineManager()
        manager.add_skill('upper', SKILL_REGISTRY['uppercase'])
        self.assertIn('upper', manager.list_skills())

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'serve':
        app = create_app()
        app.run(host='0.0.0.0', port=5000)
    else:
        cli()