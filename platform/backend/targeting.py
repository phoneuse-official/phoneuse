"""Structured, escaped WDA selectors and short-lived task-local element references."""
import json
import secrets
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

INPUT_TYPES = ('XCUIElementTypeTextField', 'XCUIElementTypeSearchField', 'XCUIElementTypeTextView')
CONTROL_TYPES = (*INPUT_TYPES, 'XCUIElementTypeButton', 'XCUIElementTypeLink',
                 'XCUIElementTypeCell', 'XCUIElementTypeSwitch')

class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identifier: str | None = Field(default=None, min_length=1, max_length=500)
    label: str | None = Field(default=None, min_length=1, max_length=500)
    types: tuple[str,...] | None = Field(default=None,min_length=1,max_length=12)
    type: str | None = Field(default=None, pattern=r'^XCUIElementType[A-Za-z]+$')

    @model_validator(mode='after')
    def populated(self):
        if not any((self.identifier, self.label, self.type, self.types)):
            raise ValueError('At least one target attribute is required')
        if self.types:
            import re
            if any(not re.fullmatch(r'XCUIElementType[A-Za-z]+',kind) for kind in self.types):
                raise ValueError('Invalid element type')
        return self

class Target(Scope):
    strategy: Literal['predicate','class_chain'] = 'predicate'
    ref: str | None = Field(default=None, pattern=r'^[a-f0-9]{16}:\d+$')
    within: Scope | None = None

    @model_validator(mode='after')
    def populated(self):
        if not any((self.ref, self.identifier, self.label, self.type, self.types)):
            raise ValueError('At least one target attribute or reference is required')
        if not self.ref:super().populated()
        if self.ref and any((self.identifier, self.label, self.type, self.types, self.within)):
            raise ValueError('Use a reference alone, or a structured selector')
        return self


def predicate(target):
    clauses=[]
    for field, attr in (('identifier','name'), ('label','label'), ('type','type')):
        value=getattr(target,field)
        if value is not None:
            clauses.append(f'{attr} == {json.dumps(value,ensure_ascii=False)}')
    if target.types:
        clauses.append('type IN {'+','.join(json.dumps(kind) for kind in target.types)+'}')
    return ' AND '.join(clauses)


def selectors(target):
    """Raw WDA strategy names, not Appium's public aliases. Never use XPath."""
    if target.ref:
        raise ValueError('References must be resolved inside the issuing task')
    if target.strategy=='class_chain' and not target.types:
        condition=predicate(target)
        # A backtick delimits class-chain predicates; use native predicate mode for such labels.
        if '`' not in condition:
            return [('class chain','**/XCUIElementTypeAny[`'+condition+'`]')]
    if target.identifier and not (target.label or target.type or target.types):
        return [('accessibility id',target.identifier)]
    if target.label and not (target.identifier or target.type or target.types):
        value=json.dumps(target.label,ensure_ascii=False)
        return [('accessibility id',target.label),('predicate string',f'name == {value} OR label == {value}')]
    return [('predicate string',predicate(target))]


class References:
    def __init__(self):
        self.invalidate()

    def invalidate(self):
        self.revision=secrets.token_hex(8)
        self.items={}

    def add(self, candidate):
        ref=f'{self.revision}:{len(self.items)+1}'
        self.items[ref]=dict(candidate)
        return ref

    def get(self, ref):
        return self.items.get(ref)
