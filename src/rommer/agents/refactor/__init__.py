"""Refactor pipeline agents - multi-stage code transformation."""

from rommer.agents.refactor.type_resolver import TypeResolver
from rommer.agents.refactor.literal_pool import LiteralPoolResolver
from rommer.agents.refactor.forward_decl import ForwardDeclGenerator
from rommer.agents.refactor.struct_annotator import StructAnnotator
from rommer.agents.refactor.system_tracer import SystemTracer

PIPELINE_ORDER = [
    TypeResolver,
    LiteralPoolResolver,
    ForwardDeclGenerator,
    StructAnnotator,
    SystemTracer,
]

__all__ = [
    "TypeResolver",
    "LiteralPoolResolver",
    "ForwardDeclGenerator",
    "StructAnnotator",
    "SystemTracer",
    "PIPELINE_ORDER",
]
