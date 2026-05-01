"""提供「技能匹配」服務，根據使用者輸入的需求文字與技能清單，計算相似度並在必要時使用 GPT‑OSS 20B 進行推理，輸出最適合的技能名稱、相似度分數與備註。"""
# ── 工坊組裝：Skill Matching Organ ──────────────────────────────────────────
# 組裝時間：2026-04-30T22:40:30
# 任務數：6

from agent_logger import get_logger
from fastapi import FastAPI, HTTPException
from fastapi import HTTPException
from functools import lru_cache
from logging import logger
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from typing import List, Tuple
import ai_bridge
import asyncio
import concurrent.futures
import logging
import numpy as np
import random
import re
import sys
import threading
import time

app = FastAPI(title='Skill Matching API')

def _tokenize(text: str) -> set:
    """Simple tokenizer: lowercased words, stripped of punctuation."""
    return set(re.findall('\\b\\w+\\b', text.lower()))

def _jaccard_similarity(a: set, b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0

class MatchSkillRequest(BaseModel):
    description: str = Field(..., example='I have experience in Python and data analysis.')
    skills: List[str] = Field(..., example=['Python', 'Data Analysis', 'Machine Learning'])
    threshold: Optional[float] = Field(0.5, ge=0.0, le=1.0, example=0.6)

    @validator('skills')
    def skills_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('skills list must contain at least one skill')
        return v

class MatchedSkill(BaseModel):
    skill: str
    score: float

class MatchSkillResponse(BaseModel):
    matched_skills: List[MatchedSkill]

@app.post('/match_skill', response_model=MatchSkillResponse)
async def match_skill(request: MatchSkillRequest):
    desc_tokens = _tokenize(request.description)
    matched: List[MatchedSkill] = []
    for skill in request.skills:
        skill_tokens = _tokenize(skill)
        score = _jaccard_similarity(desc_tokens, skill_tokens)
        if score >= request.threshold:
            matched.append(MatchedSkill(skill=skill, score=round(score, 4)))
    if not matched:
        raise HTTPException(status_code=404, detail='No skills matched the given threshold.')
    return MatchSkillResponse(matched_skills=matched)

try:
    import ai_bridge
except Exception:

    class _StubBridge:
        """Fallback bridge that returns a deterministic 768‑dim vector."""

        def __init__(self):
            self.lock = threading.Lock()

        def send_to_bridge(self, payload):
            with self.lock:
                text = payload.get('text', '')
                seed = hash(text) & 4294967295
                rng = random.Random(seed)
                return [rng.random() for _ in range(768)]
    ai_bridge = _StubBridge()
    print('Warning: ai_bridge module not found. Using stub implementation.', file=sys.stderr)

@lru_cache(maxsize=128)
def get_embedding(text: str):
    """
    Retrieve a 768‑dimensional embedding for the given text.

    Parameters
    ----------
    text : str
        The input text to embed.

    Returns
    -------
    list[float]
        A list of 768 floating‑point numbers representing the embedding.
    """
    payload = {'task': 'embed', 'text': text}
    result = ai_bridge.send_to_bridge(payload)
    if not isinstance(result, (list, tuple)):
        raise ValueError(f'Unexpected type: {type(result)}')
    if len(result) != 768:
        raise ValueError(f'Unexpected length: {len(result)}')
    return list(result)

if __name__ == '__main__':
    sample_text = 'Hello, world!'
    embedding = get_embedding(sample_text)
    print(f"Embedding for '{sample_text}':")
    print(embedding[:5], '...', embedding[-5:])

def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if np.isclose(norm1, 0) or np.isclose(norm2, 0):
        return 0.0
    return dot_product / (norm1 * norm2)

def compute_similarity(description_embedding: np.ndarray, skill_embeddings: np.ndarray, skill_names: List[str]=None) -> List[Tuple[str, float]]:
    """
    Compute cosine similarity between a description embedding and each skill embedding.
    Returns a list of (skill_name, similarity) tuples sorted by descending similarity.
    """
    similarities = []
    for idx, skill_emb in enumerate(skill_embeddings):
        sim = cosine_similarity(description_embedding, skill_emb)
        skill_name = skill_names[idx] if skill_names and idx < len(skill_names) else f'Skill_{idx}'
        similarities.append((skill_name, sim))
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities

def main():
    try:
        description_embedding = np.load('description_embedding.npy')
        skill_embeddings = np.load('skill_embeddings.npy')
        if np.isscalar(skill_embeddings):
            skill_embeddings = np.array([skill_embeddings])
        skill_names = np.load('skill_names.npy') if 'skill_names.npy' in locals() else None
    except FileNotFoundError:
        np.random.seed(42)
        description_embedding = np.random.rand(768)
        skill_embeddings = np.random.rand(10, 768)
        if 'skill_names' not in globals():
            skill_names = [f'Skill_{i}' for i in range(skill_embeddings.shape[0])]
    except Exception as e:
        print(f'An error occurred: {e}')
        description_embedding = np.random.rand(768)
        skill_embeddings = np.random.rand(10, 768)
        if 'skill_names' not in globals():
            skill_names = [f'Skill_{i}' for i in range(skill_embeddings.shape[0])]
    similarities = compute_similarity(description_embedding, skill_embeddings, skill_names)
    print('Skills sorted by descending cosine similarity:')
    for skill, sim in similarities:
        print(f'{skill}: {sim:.4f}')

if __name__ == '__main__':
    main()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S.%f')

logger = logging.getLogger(__name__)

class LoggerContext:
    """Context manager that logs request time, input, output and duration."""

    def __init__(self, request_input):
        self.request_input = request_input
        self.start_time = None
        self.output = None

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Request time: {time.strftime('%Y-%m-%d %H:%M:%S.%f', time.localtime(self.start_time))}")
        logger.info(f'Input: {self.request_input}')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        duration_ms = (end_time - self.start_time) * 1000
        logger.info(f'Output: {self.output}')
        logger.info(f'Execution duration: {duration_ms:.2f} ms')
        if duration_ms > 200:
            logger.warning(f'Processing exceeded 200 ms: {duration_ms:.2f} ms')

def get_logger(request_input):
    """Return a LoggerContext instance for the given request input."""
    return LoggerContext(request_input)

def handle_request(request_input):
    """Example request handler that uses the logging context."""
    with get_logger(request_input) as ctx:
        time.sleep(0.5)
        ctx.output = {'status': 'success', 'echo': request_input}
        return ctx.output

if __name__ == '__main__':
    sample_request = {'message': 'Hello, world!'}
    response = handle_request(sample_request)
    print('Response:', response)

lock = threading.Lock()

@lru_cache(maxsize=256)
def _sync_get_embedding(text: str) -> List[float]:
    """Synchronous cached embedding fetch."""
    return ai_bridge.send_to_bridge({'task': 'embed', 'text': text})

def sync_get_embedding(text: str) -> List[float]:
    """Sync wrapper around the cached sync function."""
    with lock:
        return _sync_get_embedding(text)

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity for two 768‑dim vectors."""
    import numpy as np
    v1, v2 = (np.array(vec1), np.array(vec2))
    dot = v1 @ v2
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    return float(dot / norm) if norm else 0.0

async def async_similarity(desc: str, skills: List[str]) -> List[Tuple[str, float]]:
    """Compute similarities asynchronously."""
    desc_emb = sync_get_embedding(desc)
    tasks = [sync_get_embedding(skill) for skill in skills]
    skill_embs = await asyncio.gather(*tasks)
    sims = [_cosine_similarity(desc_emb, emb) for emb in skill_embs]
    return list(zip(skills, sims))

def _batch_worker(args: Tuple[str, List[str]]) -> List[Tuple[str, float]]:
    desc, skills = args
    return asyncio.run(async_similarity(desc, skills))

def batch_process(descs: List[str], skill_sets: List[List[str]], max_workers=None) -> List[List[Tuple[str, float]]]:
    """Process batches in parallel (multiprocessing) if requested."""
    if max_workers is None:
        max_workers = concurrent.futures.ThreadPoolExecutor().max_workers or 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_batch_worker, (desc, skills)) for desc, skills in zip(descs, skill_sets)]
        return [future.result() for future in concurrent.futures.as_completed(futures)]

logger = get_logger(__name__)

if __name__ == '__main__':
    desc = 'Experienced in Python, data analysis, and machine learning.'
    skills = ['Python', 'Data Analysis', 'Machine Learning', 'Java', 'C++']
    sims = asyncio.run(async_similarity(desc, skills))
    print('Async similarities:', sims)
    descs = [desc, 'Skilled in Java and Spring Boot.']
    skill_sets = [skills, ['Java', 'Spring Boot', 'Docker']]
    batch_sims = batch_process(descs, skill_sets)
    print('Batch results:', batch_sims)