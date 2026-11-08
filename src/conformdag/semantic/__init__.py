"""Privacy-preserving semantic provider, context, and normalized cache primitives."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import httpx

from conformdag.models import SemanticRequest, SemanticResponse
from conformdag.security.redaction import CREDENTIAL_PATTERNS, redact_credentials
from conformdag.semantic.cache import LOGGER, CachedSemanticProvider, SemanticCache, semantic_cache_key
from conformdag.semantic.context import DEFAULT_SECRET_PATTERNS, SemanticContext, build_context, redact_text
from conformdag.semantic.prompts import DEFAULT_PROMPT_TEMPLATE, GENERIC_REVIEWER_PROMPT, PromptTemplate
from conformdag.semantic.provider import (
    OpenAICompatibleProvider,
    SemanticProviderError,
    strict_semantic_response_schema,
)

__all__ = [
    "annotations",
    "fcntl",
    "hashlib",
    "json",
    "logging",
    "os",
    "re",
    "tempfile",
    "Iterable",
    "Iterator",
    "Mapping",
    "Sequence",
    "ThreadPoolExecutor",
    "contextmanager",
    "suppress",
    "deepcopy",
    "dataclass",
    "Path",
    "monotonic",
    "sleep",
    "Any",
    "cast",
    "httpx",
    "SemanticRequest",
    "SemanticResponse",
    "CREDENTIAL_PATTERNS",
    "redact_credentials",
    "LOGGER",
    "SemanticProviderError",
    "strict_semantic_response_schema",
    "DEFAULT_SECRET_PATTERNS",
    "SemanticContext",
    "PromptTemplate",
    "DEFAULT_PROMPT_TEMPLATE",
    "GENERIC_REVIEWER_PROMPT",
    "redact_text",
    "build_context",
    "OpenAICompatibleProvider",
    "semantic_cache_key",
    "SemanticCache",
    "CachedSemanticProvider",
]
