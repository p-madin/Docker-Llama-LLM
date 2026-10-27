#!/usr/bin/env python3
"""
modelAssertion.py - SOLID-compliant Assertions Framework for LLM Model Outputs

Architecture & SOLID Principles:
  - Single Responsibility Principle (SRP):
      Each assertion class is solely responsible for one evaluation rule.
  - Open/Closed Principle (OCP):
      New assertion rules can be added via AssertionFactory.register() without modifying existing classes.
  - Liskov Substitution Principle (LSP):
      All assertion classes implement the BaseAssertion abstract interface and can be used interchangeably.
  - Interface Segregation Principle (ISP):
      The BaseAssertion interface exposes only the essential evaluate() method.
  - Dependency Inversion Principle (DIP):
      High-level execution runners depend on BaseAssertion and ModelAssertion abstractions rather than concrete checks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Type
import re


@dataclass
class AssertionResult:
    """Represents the structured outcome of an assertion evaluation."""
    rule_type: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result to dictionary format for reporting."""
        return {
            "rule": self.rule_type,
            "passed": self.passed,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


class BaseAssertion(ABC):
    """Abstract Base Class for all model output assertions."""
    rule_type: str = "base"

    def __init__(self, expected_values: Any, case_sensitive: bool = False):
        if isinstance(expected_values, str):
            self.expected_values = [expected_values]
        else:
            self.expected_values = list(expected_values) if expected_values else []
        self.case_sensitive = case_sensitive

    @abstractmethod
    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        """
        Evaluates the assertion against the LLM's text output and performance metrics.
        Returns an AssertionResult instance.
        """
        pass

    def _normalize(self, text: str) -> str:
        """Normalizes text according to case_sensitive configuration."""
        return text if self.case_sensitive else text.lower()

    def _clean_markdown(self, text: str) -> str:
        """Strips markdown emphasis formatting (**, *, `) for resilient substring checks."""
        return text.replace("**", "").replace("`", "")


# ==============================================================================
# Concrete Assertions (Single Responsibility Principle)
# ==============================================================================

class ContainsAssertion(BaseAssertion):
    """Asserts that the output contains a specific substring."""
    rule_type = "contains"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        target = self.expected_values[0] if self.expected_values else ""
        text = self._normalize(output)
        check = self._normalize(target)
        passed = (check in text) or (self._clean_markdown(check) in self._clean_markdown(text))
        msg = f"Contains '{target}'" if passed else f"Expected output to contain '{target}'"
        return AssertionResult(self.rule_type, passed, msg, expected=target, actual=output.strip()[:100])


class ContainsAnyAssertion(BaseAssertion):
    """Asserts that the output contains at least one of the specified candidate substrings."""
    rule_type = "contains_any"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        text = self._normalize(output)
        clean_text = self._clean_markdown(text)
        for target in self.expected_values:
            check = self._normalize(target)
            if (check in text) or (self._clean_markdown(check) in clean_text):
                return AssertionResult(
                    self.rule_type, True,
                    f"Contains match '{target}' (any of {self.expected_values})",
                    expected=self.expected_values, actual=target
                )
        return AssertionResult(
            self.rule_type, False,
            f"Expected output to contain at least one of: {self.expected_values}",
            expected=self.expected_values, actual=output.strip()[:100]
        )


class ContainsAllAssertion(BaseAssertion):
    """Asserts that all required substrings are present in the output."""
    rule_type = "contains_all"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        text = self._normalize(output)
        clean_text = self._clean_markdown(text)
        missing = [
            target for target in self.expected_values
            if (self._normalize(target) not in text) and (self._clean_markdown(self._normalize(target)) not in clean_text)
        ]
        passed = len(missing) == 0
        msg = f"Contains all: {self.expected_values}" if passed else f"Missing required items: {missing}"
        return AssertionResult(self.rule_type, passed, msg, expected=self.expected_values, actual=f"missing: {missing}")


class NotContainsAssertion(BaseAssertion):
    """Asserts that a prohibited substring does NOT appear in the output."""
    rule_type = "not_contains"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        target = self.expected_values[0] if self.expected_values else ""
        text = self._normalize(output)
        check = self._normalize(target)
        passed = check not in text
        msg = f"Does not contain prohibited '{target}'" if passed else f"Output contains prohibited substring '{target}'"
        return AssertionResult(self.rule_type, passed, msg, expected=f"NOT '{target}'", actual=f"contains: {target}" if not passed else "absent")


class RegexAssertion(BaseAssertion):
    """Asserts that the output matches a regular expression pattern."""
    rule_type = "regex"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        pattern = self.expected_values[0] if self.expected_values else ""
        flags = 0 if self.case_sensitive else re.IGNORECASE
        passed = bool(re.search(pattern, output, flags))
        msg = f"Matches regex pattern: r'{pattern}'" if passed else f"Failed regex match: r'{pattern}'"
        return AssertionResult(self.rule_type, passed, msg, expected=f"regex: {pattern}", actual=output.strip()[:100])


class ExactAssertion(BaseAssertion):
    """Asserts that the output exactly matches the expected string (whitespace trimmed)."""
    rule_type = "exact"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        target = self.expected_values[0] if self.expected_values else ""
        text = self._normalize(output.strip())
        check = self._normalize(target.strip())
        passed = text == check
        msg = f"Exact match: '{target}'" if passed else f"Expected exact match '{target}', got '{output.strip()}'"
        return AssertionResult(self.rule_type, passed, msg, expected=target, actual=output.strip())


class MaxLatencyAssertion(BaseAssertion):
    """Performance assertion: Response latency must be under threshold (seconds)."""
    rule_type = "max_latency_sec"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        max_sec = float(self.expected_values[0]) if self.expected_values else 10.0
        actual_sec = metrics.get("latency_sec", 0.0)
        passed = actual_sec <= max_sec
        msg = f"Latency {actual_sec:.2f}s <= limit {max_sec:.2f}s" if passed else f"Latency {actual_sec:.2f}s exceeded limit of {max_sec:.2f}s"
        return AssertionResult(self.rule_type, passed, msg, expected=f"<= {max_sec}s", actual=f"{actual_sec}s")


class MinTokensPerSecAssertion(BaseAssertion):
    """Performance assertion: Generation throughput must meet minimum tokens/second."""
    rule_type = "min_tokens_per_sec"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        min_tps = float(self.expected_values[0]) if self.expected_values else 10.0
        actual_tps = metrics.get("eval_tokens_per_sec", 0.0)
        passed = actual_tps >= min_tps
        msg = f"Speed {actual_tps:.1f} tok/s >= threshold {min_tps:.1f} tok/s" if passed else f"Speed {actual_tps:.1f} tok/s fell below threshold {min_tps:.1f} tok/s"
        return AssertionResult(self.rule_type, passed, msg, expected=f">= {min_tps} tok/s", actual=f"{actual_tps} tok/s")


class MinWordsAssertion(BaseAssertion):
    """Asserts that the output contains at least N words (ensures a sentence/statement was fabricated)."""
    rule_type = "min_words"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        min_words = int(self.expected_values[0]) if self.expected_values else 1
        words = output.strip().split()
        count = len(words)
        passed = count >= min_words
        msg = f"Word count {count} >= required minimum {min_words}" if passed else f"Fabricated output has only {count} word(s), expected at least {min_words}"
        return AssertionResult(self.rule_type, passed, msg, expected=f">= {min_words} words", actual=f"{count} words")


class MaxWordsAssertion(BaseAssertion):
    """Asserts that the output contains at most N words."""
    rule_type = "max_words"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        max_words = int(self.expected_values[0]) if self.expected_values else 100
        words = output.strip().split()
        count = len(words)
        passed = count <= max_words
        msg = f"Word count {count} <= maximum limit {max_words}" if passed else f"Fabricated output has {count} word(s), exceeded maximum {max_words}"
        return AssertionResult(self.rule_type, passed, msg, expected=f"<= {max_words} words", actual=f"{count} words")


class ExactWordsAssertion(BaseAssertion):
    """Asserts that the output contains exactly N words."""
    rule_type = "exact_words"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        target_words = int(self.expected_values[0]) if self.expected_values else 1
        words = output.strip().split()
        count = len(words)
        passed = count == target_words
        msg = f"Word count exactly matches target {target_words}" if passed else f"Fabricated output has {count} word(s), expected exactly {target_words}"
        return AssertionResult(self.rule_type, passed, msg, expected=f"== {target_words} words", actual=f"{count} words")


class NotEmptyAssertion(BaseAssertion):
    """Asserts that the output is not empty or pure whitespace."""
    rule_type = "not_empty"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        text = output.strip()
        passed = len(text) > 0
        msg = "Output is not empty" if passed else "Output is empty (no sentence was fabricated)"
        return AssertionResult(self.rule_type, passed, msg, expected="non-empty string", actual=f"len: {len(text)}")


class MinLengthAssertion(BaseAssertion):
    """Asserts that the output text meets a minimum character count."""
    rule_type = "min_length"

    def evaluate(self, output: str, metrics: Dict[str, Any]) -> AssertionResult:
        min_chars = int(self.expected_values[0]) if self.expected_values else 1
        actual_len = len(output.strip())
        passed = actual_len >= min_chars
        msg = f"Length {actual_len} chars >= limit {min_chars}" if passed else f"Length {actual_len} chars fell short of minimum {min_chars}"
        return AssertionResult(self.rule_type, passed, msg, expected=f">= {min_chars} chars", actual=f"{actual_len} chars")


# ==============================================================================
# Factory (Open/Closed Principle)
# ==============================================================================

class AssertionFactory:
    """Factory for registering and instantiating BaseAssertion subclasses."""
    _registry: Dict[str, Type[BaseAssertion]] = {}

    @classmethod
    def register(cls, rule_type: str, assertion_cls: Type[BaseAssertion]):
        """Registers a new assertion class under the given rule type name."""
        cls._registry[rule_type.lower().strip()] = assertion_cls

    @classmethod
    def create(cls, rule_type: str, expected_values: List[str], case_sensitive: bool = False) -> BaseAssertion:
        """Instantiates an assertion for the requested rule type."""
        key = rule_type.lower().strip()
        assertion_cls = cls._registry.get(key)
        if not assertion_cls:
            raise ValueError(f"Unknown assertion type '{rule_type}'. Registered types: {list(cls._registry.keys())}")
        return assertion_cls(expected_values=expected_values, case_sensitive=case_sensitive)


# Register all built-in assertion classes
AssertionFactory.register("contains", ContainsAssertion)
AssertionFactory.register("contains_any", ContainsAnyAssertion)
AssertionFactory.register("contains_all", ContainsAllAssertion)
AssertionFactory.register("not_contains", NotContainsAssertion)
AssertionFactory.register("regex", RegexAssertion)
AssertionFactory.register("exact", ExactAssertion)
AssertionFactory.register("max_latency_sec", MaxLatencyAssertion)
AssertionFactory.register("min_tokens_per_sec", MinTokensPerSecAssertion)
AssertionFactory.register("min_words", MinWordsAssertion)
AssertionFactory.register("max_words", MaxWordsAssertion)
AssertionFactory.register("exact_words", ExactWordsAssertion)
AssertionFactory.register("not_empty", NotEmptyAssertion)
AssertionFactory.register("min_length", MinLengthAssertion)


# ==============================================================================
# ModelAssertion - Dedicated Evaluator for Model Outputs
# ==============================================================================

class ModelAssertion:
    """
    Unique class for evaluating an LLM model's output against a suite of assertions.
    Decouples assertion management and evaluation from the test runner orchestration.
    """
    def __init__(self, assertions: Optional[List[BaseAssertion]] = None):
        self.assertions: List[BaseAssertion] = assertions or []

    def add(self, assertion: BaseAssertion) -> "ModelAssertion":
        """Adds a single assertion to the evaluation suite."""
        self.assertions.append(assertion)
        return self

    def add_from_spec(self, rule_type: str, expected_values: List[str], case_sensitive: bool = False) -> "ModelAssertion":
        """Builds and adds an assertion rule via AssertionFactory."""
        assertion = AssertionFactory.create(rule_type, expected_values, case_sensitive)
        self.assertions.append(assertion)
        return self

    def evaluate(self, output: str, metrics: Optional[Dict[str, Any]] = None) -> List[AssertionResult]:
        """
        Evaluates model output against all registered assertion rules.
        Returns a list of AssertionResult objects.
        """
        metrics = metrics or {}
        return [rule.evaluate(output, metrics) for rule in self.assertions]

    def is_all_passed(self, results: List[AssertionResult]) -> bool:
        """Returns True if every assertion in the result list passed."""
        return all(r.passed for r in results)

    def evaluate_all(self, output: str, metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluates model output against all registered assertion rules.
        Returns a dictionary summary with 'all_passed' boolean and serialized 'results' list.
        """
        results = self.evaluate(output, metrics)
        return {
            "all_passed": self.is_all_passed(results),
            "results": [r.to_dict() for r in results]
        }

    def __len__(self) -> int:
        return len(self.assertions)

    def __iter__(self):
        return iter(self.assertions)
