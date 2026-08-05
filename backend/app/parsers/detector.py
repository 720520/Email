"""多行表头扫描与工作簿类型评分。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.core.config import ExcelSettings
from app.parsers.field_registry import FieldAliasRegistry
from app.parsers.models import FieldColumn, TableDetection, WorkbookType
from app.parsers.normalizers import is_blank, normalize_text


@dataclass(frozen=True, slots=True)
class _TypeScore:
    workbook_type: WorkbookType
    score: float
    confidence: float
    missing_fields: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


@dataclass(frozen=True, slots=True)
class _HeaderCandidate:
    start_row: int
    row_count: int
    field_columns: dict[str, FieldColumn]
    type_scores: tuple[_TypeScore, ...]

    @property
    def best_type(self) -> _TypeScore:
        return self.type_scores[0]


class TableDetector:
    def __init__(self, registry: FieldAliasRegistry, settings: ExcelSettings) -> None:
        self.registry = registry
        self.settings = settings

    def detect(self, sheet_name: str, frame: pd.DataFrame) -> TableDetection | None:
        candidates: list[_HeaderCandidate] = []
        row_limit = min(len(frame.index), self.settings.header_scan_rows)
        column_limit = min(len(frame.columns), self.settings.max_columns)
        for start_row in range(row_limit):
            for row_count in range(1, self.settings.max_header_rows + 1):
                if start_row + row_count > row_limit:
                    break
                field_columns = self._match_header(
                    frame,
                    start_row=start_row,
                    row_count=row_count,
                    column_limit=column_limit,
                )
                if len(field_columns) < self.settings.min_header_fields:
                    continue
                scores = self._score_types(field_columns)
                candidates.append(
                    _HeaderCandidate(start_row, row_count, field_columns, tuple(scores))
                )

        if not candidates:
            return None
        candidates.sort(key=self._candidate_sort_key, reverse=True)
        selected = candidates[0]
        best = selected.type_scores[0]
        ambiguous_with = self._ambiguous_type(selected.type_scores)
        return TableDetection(
            workbook_type=best.workbook_type,
            sheet_name=sheet_name,
            header_start_row=selected.start_row,
            header_row_count=selected.row_count,
            field_columns=selected.field_columns,
            score=best.score,
            confidence=best.confidence,
            missing_fields=best.missing_fields,
            ambiguous_with=ambiguous_with,
        )

    def _match_header(
        self,
        frame: pd.DataFrame,
        *,
        start_row: int,
        row_count: int,
        column_limit: int,
    ) -> dict[str, FieldColumn]:
        matches: dict[str, FieldColumn] = {}
        for column_index in range(column_limit):
            raw_parts = [
                frame.iat[row_index, column_index]
                for row_index in range(start_row, start_row + row_count)
            ]
            text_parts = [normalize_text(value) for value in raw_parts if not is_blank(value)]
            clean_parts = [value for value in text_parts if value]
            if not clean_parts:
                continue
            variants = [*clean_parts]
            if len(clean_parts) > 1:
                variants.append("".join(clean_parts))
            match = self.registry.match(variants)
            if match is None:
                continue
            field_column = FieldColumn(
                column_index=column_index,
                header_label=" / ".join(clean_parts),
                matched_alias=match.matched_alias,
                match_strength=match.strength,
            )
            current = matches.get(match.field_name)
            if current is None or field_column.match_strength > current.match_strength:
                matches[match.field_name] = field_column
        return matches

    def _score_types(self, field_columns: dict[str, FieldColumn]) -> list[_TypeScore]:
        matched_fields = set(field_columns)
        matched_aliases = {column.matched_alias for column in field_columns.values()}
        scores: list[_TypeScore] = []
        for rule in self.registry.type_rules.values():
            required_hits = len(rule.required_fields & matched_fields)
            group_hits = sum(bool(group & matched_fields) for group in rule.required_any)
            required_count = len(rule.required_fields) + len(rule.required_any)
            required_ratio = (required_hits + group_hits) / required_count
            missing = set(rule.required_fields - matched_fields)
            missing.update(
                "|".join(sorted(group))
                for group in rule.required_any
                if not group & matched_fields
            )
            missing_fields = tuple(sorted(missing))
            signature_hits = len(rule.signature_aliases & matched_aliases)
            score = (
                required_ratio * 100
                + (required_count * 6 if not missing_fields else 0)
                + signature_hits * 15
                + len(matched_fields)
            )
            signature_ratio = (
                signature_hits / len(rule.signature_aliases) if rule.signature_aliases else 0
            )
            confidence = min(1.0, required_ratio * 0.85 + signature_ratio * 0.15)
            scores.append(
                _TypeScore(rule.workbook_type, score, confidence, missing_fields)
            )
        scores.sort(key=lambda item: (item.is_complete, item.score), reverse=True)
        return scores

    @staticmethod
    def _candidate_sort_key(candidate: _HeaderCandidate) -> tuple[Any, ...]:
        best = candidate.best_type
        return (
            best.is_complete,
            best.score,
            len(candidate.field_columns),
            -candidate.row_count,
            -candidate.start_row,
        )

    def _ambiguous_type(self, scores: tuple[_TypeScore, ...]) -> WorkbookType | None:
        if len(scores) < 2 or not scores[0].is_complete or not scores[1].is_complete:
            return None
        if scores[0].score - scores[1].score <= self.settings.ambiguity_score_delta:
            return scores[1].workbook_type
        return None
