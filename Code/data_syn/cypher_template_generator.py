#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field

from typing import List, Optional, Union, Any, Tuple, Dict

from abc import ABC, abstractmethod

import random

import os

import string

import json


class DataSampler:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.sampled_data = {}
        self._load_sampled_data()

    def _load_sampled_data(self):
        if not os.path.exists(self.data_dir):
            return
        for filename in os.listdir(self.data_dir):
            if "cycles" in filename and filename.endswith(".json"):
                filepath = os.path.join(self.data_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "nodes" in data:
                            self.sampled_data[filename] = data["nodes"]
                except Exception as e:
                    print(f"加载数据文件失败 {filename}: {e}")

    def sample_property_value(
        self, node_type: str, property_name: str, property_type: str
    ) -> str:
        matching_values = []
        for (filename, nodes) in self.sampled_data.items():
            for node in nodes:
                if node.get("type") == node_type and property_name in node.get(
                    "properties", {}
                ):
                    value = node["properties"][property_name]
                    matching_values.append(value)
        if matching_values:
            sampled_value = random.choice(matching_values)
            if isinstance(sampled_value, str):
                return f"'{sampled_value}'"
            else:
                return str(sampled_value)
        return self._generate_random_value(property_type)

    def _generate_random_value(self, property_type: str) -> str:
        if property_type == "string":
            length = random.randint(3, 15)
            random_str = "".join(
                random.choices(string.ascii_letters + string.digits, k=length)
            )
            return f"'{random_str}'"
        elif property_type in ["int", "integer"]:
            return str(random.randint(1, 1000))
        elif property_type == "float":
            return str(round(random.uniform(1.0, 100.0), 2))
        elif property_type == "boolean":
            return str(random.choice([True, False]))
        else:
            length = random.randint(5, 15)
            random_str = "".join(
                random.choices(string.ascii_letters + string.digits, k=length)
            )
            return f"'{random_str}'"

    def sample_node_id(self, node_type: str) -> str:
        matching_ids = []
        for (filename, nodes) in self.sampled_data.items():
            for node in nodes:
                if node.get("type") == node_type:
                    matching_ids.append(node.get("id"))
        if matching_ids:
            return random.choice(matching_ids)
        return f"{node_type}_{random.randint(0, 999)}"

    def sample_relationship_id(self, rel_type: str) -> str:
        for (filename, nodes) in self.sampled_data.items():
            pass
        return f"{rel_type}_{random.randint(0, 999)}"


@dataclass
class Expression:
    def to_cypher(self) -> str:
        raise NotImplementedError

    def to_nebula(self) -> str:
        raise NotImplementedError


@dataclass
class Identifier(Expression):

    name: str

    def to_cypher(self) -> str:
        return self.name

    def to_nebula(self) -> str:
        return self.name


@dataclass
class PropertyRef(Expression):

    identifier: Identifier
    property_name: str

    def to_cypher(self) -> str:
        return f"{self.identifier.to_cypher()}.`{self.property_name}`"

    def to_nebula(self) -> str:
        return f"{self.identifier.to_nebula()}.`{self.property_name}`"


@dataclass
class Value(Expression):

    value: Any

    def to_cypher(self) -> str:
        v = self.value
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace("'", "\\'")
            return f"'{escaped}'"
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "null"
        return str(v)

    def to_nebula(self) -> str:
        return self.to_cypher()


@dataclass
class BinaryOp(Expression):

    left: Expression
    op: str
    right: Expression

    def to_cypher(self) -> str:
        left_str = self.left.to_cypher()
        right_str = self.right.to_cypher()
        return f"{left_str} {self.op} {right_str}"

    def to_nebula(self) -> str:
        left_str = self.left.to_nebula()
        right_str = self.right.to_nebula()
        if self.op in ["CONTAINS", "STARTS WITH", "ENDS WITH"]:
            return f"contains({left_str},{right_str})"
        if self.op == "=~":
            return f"regexp_like({left_str},{right_str})"
        return f"{left_str} {self.op} {right_str}"


@dataclass
class UnaryOp(Expression):

    op: str
    expr: Expression

    def to_cypher(self) -> str:
        expr_str = self.expr.to_cypher()
        if self.op == "NOT":
            return f"NOT {expr_str}"
        elif self.op == "IS NULL":
            return f"{expr_str} IS NULL"
        elif self.op == "IS NOT NULL":
            return f"{expr_str} IS NOT NULL"
        return f"{self.op} {expr_str}"

    def to_nebula(self) -> str:
        expr_str = self.expr.to_nebula()
        if self.op == "NOT":
            return f"NOT {expr_str}"
        elif self.op == "IS NULL":
            return f"{expr_str} IS NULL"
        elif self.op == "IS NOT NULL":
            return f"{expr_str} IS NOT NULL"
        return f"{self.op} {expr_str}"


@dataclass
class InOp(Expression):

    expr: Expression
    values: List[Expression]

    def to_cypher(self) -> str:
        expr_str = self.expr.to_cypher()
        values_str = ", ".join((v.to_cypher() for v in self.values))
        return f"{expr_str} IN [{values_str}]"

    def to_nebula(self) -> str:
        expr_str = self.expr.to_nebula()
        values_str = ", ".join((v.to_nebula() for v in self.values))
        return f"{expr_str} IN [{values_str}]"


@dataclass
class ExistsOp(Expression):

    subquery: str

    def to_cypher(self) -> str:
        return f"EXISTS {{ {self.subquery} }}"

    def to_nebula(self) -> str:
        return f"EXISTS {{ {self.subquery} }}"


@dataclass
class CaseOp(Expression):

    when_conditions: List[Tuple[Expression, Expression]]
    else_result: Optional[Expression] = None

    def to_cypher(self) -> str:
        parts = ["CASE"]
        for (condition, result) in self.when_conditions:
            parts.append(f"WHEN {condition.to_cypher()} THEN {result.to_cypher()}")
        if self.else_result:
            parts.append(f"ELSE {self.else_result.to_cypher()}")
        parts.append("END")
        return " ".join(parts)

    def to_nebula(self) -> str:
        parts = ["CASE"]
        for (condition, result) in self.when_conditions:
            cond_str = condition.to_nebula()
            result_str = result.to_nebula()
            parts.append(f"WHEN {cond_str} THEN {result_str}")
        if self.else_result:
            else_str = self.else_result.to_nebula()
            parts.append(f"ELSE {else_str}")
        parts.append("END")
        return " ".join(parts)


@dataclass
class FunctionCall(Expression):

    function_name: str
    args: List[Expression]

    def to_cypher(self) -> str:
        args_str = ", ".join((arg.to_cypher() for arg in self.args))
        return f"{self.function_name}({args_str})"

    def to_nebula(self) -> str:
        func_name = self.function_name
        if func_name == "SIZE":
            func_name = "length"
        elif func_name == "localdatetime":
            func_name = "local_datetime"
            if len(self.args) == 1:
                date_arg = self.args[0]
                if isinstance(date_arg, Value) and isinstance(date_arg.value, str):
                    date_value = date_arg.value
                    if date_value.endswith("Z"):
                        date_value = date_value[:-1]
                        date_arg = Value(date_value)
                    if len(date_value) == 10 and "-" in date_value:
                        format_str = "%Y-%m-%d"
                    elif "T" in date_value:
                        format_str = "%Y-%m-%dT%H:%M:%S"
                    else:
                        format_str = "%Y-%m-%d"
                    date_str = date_arg.to_nebula()
                    return f"{func_name}({date_str}, '{format_str}')"
        args_str = ", ".join((arg.to_nebula() for arg in self.args))
        return f"{func_name}({args_str})"


@dataclass
class CollectionOp(Expression):

    left: Expression
    op: str
    right: Expression

    def to_cypher(self) -> str:
        left_str = self.left.to_cypher()
        right_str = self.right.to_cypher()
        if self.op == "SIZE":
            return f"SIZE({left_str})"
        return f"{left_str} {self.op} {right_str}"

    def to_nebula(self) -> str:
        left_str = self.left.to_nebula()
        right_str = self.right.to_nebula()
        if self.op == "SIZE":
            return f"length({left_str})"
        return f"{left_str} {self.op} {right_str}"


@dataclass
class StringOp(Expression):

    op: str
    expr: Expression
    args: List[Expression] = field(default_factory=list)

    def to_cypher(self) -> str:
        expr_str = self.expr.to_cypher()
        if self.op == "SUBSTRING" and len(self.args) >= 2:
            return f"SUBSTRING({expr_str}, {self.args[0].to_cypher()}, {self.args[1].to_cypher()})"
        elif self.op == "REPLACE" and len(self.args) >= 2:
            return f"REPLACE({expr_str}, {self.args[0].to_cypher()}, {self.args[1].to_cypher()})"
        elif self.op == "CONCAT" and len(self.args) >= 1:
            args_str = " || ".join((arg.to_cypher() for arg in self.args))
            return f"{expr_str} || {args_str}"
        elif self.op in ["TOUPPER", "TOLOWER", "TRIM"]:
            return f"{self.op}({expr_str})"
        return f"{self.op}({expr_str})"

    def to_nebula(self) -> str:
        expr_str = self.expr.to_nebula()
        if self.op == "SUBSTRING" and len(self.args) >= 2:
            arg0_str = self.args[0].to_nebula()
            arg1_str = self.args[1].to_nebula()
            return f"SUBSTRING({expr_str}, {arg0_str}, {arg1_str})"
        elif self.op == "TOUPPER":
            return f"upper({expr_str})"
        elif self.op == "TOLOWER":
            return f"lower({expr_str})"
        elif self.op == "TRIM":
            return f"trim({expr_str})"
        return f"{self.op}({expr_str})"


@dataclass
class MathOp(Expression):

    left: Expression
    op: str
    right: Expression

    def to_cypher(self) -> str:
        left_str = self.left.to_cypher()
        right_str = self.right.to_cypher()
        return f"{left_str} {self.op} {right_str}"

    def to_nebula(self) -> str:
        left_str = self.left.to_nebula()
        right_str = self.right.to_nebula()
        return f"{left_str} {self.op} {right_str}"


@dataclass
class AliasExpr(Expression):

    expr: Expression
    alias: str

    def to_cypher(self) -> str:
        return f"{self.expr.to_cypher()} AS {self.alias}"

    def to_nebula(self) -> str:
        expr_str = self.expr.to_nebula()
        return f"{expr_str} AS {self.alias}"


class Clause(ABC):
    @abstractmethod
    def to_cypher(self) -> str:
        pass

    @classmethod
    @abstractmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Clause"]:
        pass


@dataclass
class NodePattern:

    variable: Optional[str] = None
    labels: List[str] = field(default_factory=list)

    def to_cypher(self) -> str:
        var = self.variable or ""
        label_str = (
            ":" + ":".join([f"`{label}`" for label in self.labels])
            if self.labels
            else ""
        )
        if var or label_str:
            return f"({var}{label_str})"
        return "()"

    def to_nebula(self) -> str:
        var = self.variable or ""
        label_str = (
            "@" + "@".join([f"`{label}`" for label in self.labels])
            if self.labels
            else ""
        )
        if var or label_str:
            return f"({var}{label_str})"
        return "()"


@dataclass
class RelationshipPattern:

    variable: Optional[str] = None
    types: List[str] = field(default_factory=list)
    direction: str = "->"

    def to_cypher(self) -> str:
        var = self.variable or ""
        type_str = (
            ":" + "|".join([f"`{type}`" for type in self.types]) if self.types else ""
        )
        inner = var + type_str
        if inner:
            inner = f"[{inner}]"
        else:
            inner = "[]"
        if self.direction == "->":
            return f"-{inner}->"
        if self.direction == "<-":
            return f"<-{inner}-"
        return f"-{inner}-"

    def to_nebula(self) -> str:
        var = self.variable or ""
        type_str = (
            "@" + "|".join([f"`{type}`" for type in self.types]) if self.types else ""
        )
        inner = var + type_str
        if inner:
            inner = f"[{inner}]"
        else:
            inner = "[]"
        if self.direction == "->":
            return f"-{inner}->"
        if self.direction == "<-":
            return f"<-{inner}-"
        return f"-{inner}-"


@dataclass
class PathPattern:

    start: NodePattern
    segments: List[Tuple[RelationshipPattern, NodePattern]] = field(
        default_factory=list
    )

    def to_cypher(self) -> str:
        cy = [self.start.to_cypher()]
        for (rel, node) in self.segments:
            cy.append(rel.to_cypher())
            cy.append(node.to_cypher())
        return "".join(cy)

    def to_nebula(self) -> str:
        neb = [self.start.to_nebula()]
        for (rel, node) in self.segments:
            neb.append(rel.to_nebula())
            neb.append(node.to_nebula())
        return "".join(neb)


class Match(Clause):
    def __init__(
        self, patterns: List[Union[PathPattern, NodePattern]], is_optional: bool = False
    ):
        self.patterns = patterns
        self.is_optional = is_optional

    def to_cypher(self) -> str:
        if not self.patterns:
            raise ValueError("Match requires at least one pattern")
        if (
            hasattr(self, "has_optional")
            and self.has_optional
            and (len(self.patterns) == 2)
        ):
            base_match = self.patterns[0]
            optional_match = self.patterns[1]
            optional_match.is_optional = True
            base_cypher = base_match.to_cypher()
            optional_cypher = optional_match.to_cypher()
            return f"{base_cypher}\n{optional_cypher}"
        keyword = "OPTIONAL MATCH" if self.is_optional else "MATCH"
        patterns_str = ", ".join(
            (
                p.to_cypher() if hasattr(p, "to_cypher") else str(p)
                for p in self.patterns
            )
        )
        return f"{keyword} {patterns_str}"

    def to_nebula(self) -> str:
        if not self.patterns:
            raise ValueError("Match requires at least one pattern")
        if (
            hasattr(self, "has_optional")
            and self.has_optional
            and (len(self.patterns) == 2)
        ):
            base_match = self.patterns[0]
            optional_match = self.patterns[1]
            optional_match.is_optional = True
            base_nebula = base_match.to_nebula()
            optional_nebula = optional_match.to_nebula()
            return f"{base_nebula}\n{optional_nebula}"
        keyword = "OPTIONAL MATCH" if self.is_optional else "MATCH"
        patterns_str = ", ".join(
            (
                p.to_nebula()
                if hasattr(p, "to_nebula")
                else p.to_cypher()
                if hasattr(p, "to_cypher")
                else str(p)
                for p in self.patterns
            )
        )
        return f"{keyword} {patterns_str}"

    @classmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Match"]:
        variants = []
        node_types = schema.get("node_types", [])
        rel_types = schema.get("relationship_types", [])
        if not node_types:
            return variants
        for node_type in node_types[:2]:
            node = NodePattern(variable="n", labels=[node_type["name"]])
            variants.append(Match([node]))
        for (i, rel_type) in enumerate(rel_types[:2]):
            start_node = NodePattern(
                variable="n", labels=[rel_type.get("from_node", "Node")]
            )
            end_node = NodePattern(
                variable="m", labels=[rel_type.get("to_node", "Node")]
            )
            rel = RelationshipPattern(
                variable="r", types=[rel_type["name"]], direction="->"
            )
            path = PathPattern(start=start_node, segments=[(rel, end_node)])
            variants.append(Match([path]))
        if len(rel_types) >= 2:
            for i in range(min(3, len(rel_types))):
                rel1 = rel_types[i]
                valid_rel2 = [
                    r for r in rel_types if r.get("from_node") == rel1.get("to_node")
                ]
                if not valid_rel2:
                    continue
                rel2 = valid_rel2[0]
                start_node = NodePattern(
                    variable="n", labels=[rel1.get("from_node", "Node")]
                )
                mid_node = NodePattern(
                    variable="m", labels=[rel1.get("to_node", "Node")]
                )
                end_node = NodePattern(
                    variable="k", labels=[rel2.get("to_node", "Node")]
                )
                rel_pattern1 = RelationshipPattern(
                    variable="r1", types=[rel1["name"]], direction="->"
                )
                rel_pattern2 = RelationshipPattern(
                    variable="r2", types=[rel2["name"]], direction="->"
                )
                path = PathPattern(
                    start=start_node,
                    segments=[(rel_pattern1, mid_node), (rel_pattern2, end_node)],
                )
                variants.append(Match([path]))
        if len(rel_types) >= 3:
            for i in range(min(3, len(rel_types))):
                rel1 = rel_types[i]
                valid_rel2 = [
                    r for r in rel_types if r.get("from_node") == rel1.get("to_node")
                ]
                if not valid_rel2:
                    continue
                rel2 = valid_rel2[0]
                valid_rel3 = [
                    r for r in rel_types if r.get("from_node") == rel2.get("to_node")
                ]
                if not valid_rel3:
                    continue
                rel3 = valid_rel3[0]
                start_node = NodePattern(
                    variable="n", labels=[rel1.get("from_node", "Node")]
                )
                mid1_node = NodePattern(
                    variable="m", labels=[rel1.get("to_node", "Node")]
                )
                mid2_node = NodePattern(
                    variable="k", labels=[rel2.get("to_node", "Node")]
                )
                end_node = NodePattern(
                    variable="p", labels=[rel3.get("to_node", "Node")]
                )
                rel_pattern1 = RelationshipPattern(
                    variable="r1", types=[rel1["name"]], direction="->"
                )
                rel_pattern2 = RelationshipPattern(
                    variable="r2", types=[rel2["name"]], direction="->"
                )
                rel_pattern3 = RelationshipPattern(
                    variable="r3", types=[rel3["name"]], direction="->"
                )
                path = PathPattern(
                    start=start_node,
                    segments=[
                        (rel_pattern1, mid1_node),
                        (rel_pattern2, mid2_node),
                        (rel_pattern3, end_node),
                    ],
                )
                variants.append(Match([path]))
        if len(rel_types) >= 4:
            for i in range(min(2, len(rel_types))):
                rel1 = rel_types[i]
                path_rels = [rel1]
                current_node = rel1.get("to_node")
                for hop in range(3):
                    valid_next = [
                        r for r in rel_types if r.get("from_node") == current_node
                    ]
                    if not valid_next:
                        break
                    next_rel = valid_next[0]
                    path_rels.append(next_rel)
                    current_node = next_rel.get("to_node")
                if len(path_rels) < 4:
                    continue
                start_node = NodePattern(
                    variable="n", labels=[path_rels[0].get("from_node", "Node")]
                )
                segments = []
                for (j, rel) in enumerate(path_rels):
                    mid_node = NodePattern(
                        variable=f"m{j}", labels=[rel.get("to_node", "Node")]
                    )
                    rel_pattern = RelationshipPattern(
                        variable=f"r{j + 1}", types=[rel["name"]], direction="->"
                    )
                    segments.append((rel_pattern, mid_node))
                path = PathPattern(start=start_node, segments=segments)
                variants.append(Match([path]))
        if len(rel_types) >= 5:
            for i in range(min(2, len(rel_types))):
                rel1 = rel_types[i]
                path_rels = [rel1]
                current_node = rel1.get("to_node")
                for hop in range(4):
                    valid_next = [
                        r for r in rel_types if r.get("from_node") == current_node
                    ]
                    if not valid_next:
                        break
                    next_rel = valid_next[0]
                    path_rels.append(next_rel)
                    current_node = next_rel.get("to_node")
                if len(path_rels) < 5:
                    continue
                start_node = NodePattern(
                    variable="n", labels=[path_rels[0].get("from_node", "Node")]
                )
                segments = []
                for (j, rel) in enumerate(path_rels):
                    mid_node = NodePattern(
                        variable=f"m{j}", labels=[rel.get("to_node", "Node")]
                    )
                    rel_pattern = RelationshipPattern(
                        variable=f"r{j + 1}", types=[rel["name"]], direction="->"
                    )
                    segments.append((rel_pattern, mid_node))
                path = PathPattern(start=start_node, segments=segments)
                variants.append(Match([path]))
        cycle_patterns = schema.get("cycle_patterns", [])
        if cycle_patterns is None:
            cycle_patterns = []
        for cycle_pattern in cycle_patterns:
            if not cycle_pattern.get("is_valid", False):
                continue
            cycle_path = cycle_pattern.get("cycle_path", [])
            if len(cycle_path) < 3:
                continue
            try:
                start_node = NodePattern(variable="n", labels=[cycle_path[0]])
                segments = []
                current_node_var = "n"
                for i in range(1, len(cycle_path), 2):
                    if i + 1 < len(cycle_path):
                        rel_type = cycle_path[i]
                        next_node_type = cycle_path[i + 1]
                        next_node_var = f"m{(i - 1) // 2}"
                        next_node = NodePattern(
                            variable=next_node_var, labels=[next_node_type]
                        )
                        rel_pattern = RelationshipPattern(
                            variable=f"r{(i + 1) // 2}",
                            types=[rel_type],
                            direction="->",
                        )
                        segments.append((rel_pattern, next_node))
                        current_node_var = next_node_var
                if len(cycle_path) > 2 and cycle_path[-1] == cycle_path[0]:
                    if len(cycle_path) % 2 == 1:
                        last_rel = cycle_path[-2]
                        back_to_start = NodePattern(
                            variable="n", labels=[cycle_path[0]]
                        )
                        last_rel_pattern = RelationshipPattern(
                            variable=f"r{len(segments) + 1}",
                            types=[last_rel],
                            direction="->",
                        )
                        segments.append((last_rel_pattern, back_to_start))
                if segments:
                    path_cycle = PathPattern(start=start_node, segments=segments)
                    variants.append(Match([path_cycle]))
            except Exception as e:
                print(f"构建环模式失败: {cycle_pattern.get('name', 'unknown')}, 错误: {e}")
                continue
        if len(node_types) >= 2:
            nodes = []
            for (i, node_type) in enumerate(node_types[:3]):
                node = NodePattern(variable=f"n{i}", labels=[node_type["name"]])
                nodes.append(node)
            variants.append(Match(nodes))
        if len(variants) >= 2:
            base_match = None
            while (
                base_match is None
                or len(
                    [tmp for tmp in base_match.patterns if isinstance(tmp, NodePattern)]
                )
                < 2
            ):
                base_match = random.choice(variants)
            if (
                len(
                    [tmp for tmp in base_match.patterns if isinstance(tmp, NodePattern)]
                )
                > 1
            ):
                optional_match = random.choice(
                    [tmp for tmp in base_match.patterns if isinstance(tmp, NodePattern)]
                )
                optional_match = Match([optional_match])
                combined_match = Match([base_match, optional_match])
                combined_match.has_optional = True
                variants.append(combined_match)
        return variants


class Where(Clause):
    def __init__(self, conditions: List[Expression], conjunction: str = "AND"):
        self.conditions = conditions
        self.conjunction = conjunction

    def to_cypher(self) -> str:
        if not self.conditions:
            return ""
        joined = f" {self.conjunction} ".join(
            (
                f"({c.to_cypher()})" if isinstance(c, BinaryOp) else c.to_cypher()
                for c in self.conditions
            )
        )
        return f"WHERE {joined}"

    def to_nebula(self) -> str:
        if not self.conditions:
            return ""
        joined = f" {self.conjunction} ".join(
            (
                f"({c.to_nebula()})"
                if isinstance(c, BinaryOp)
                else c.to_nebula()
                if hasattr(c, "to_nebula")
                else c.to_cypher()
                for c in self.conditions
            )
        )
        return f"WHERE {joined}"

    @staticmethod
    def _generate_value_for_property(
        prop: Dict[str, Any],
        data_sampler: DataSampler = None,
        node_type: str = None,
        gql_type: str = "cypher",
    ) -> Expression:
        prop_type = prop.get("type", "string")
        min_val = prop.get("min_value")
        max_val = prop.get("max_value")
        enum_values = prop.get("enum_values", [])
        is_datetime_type = False
        prop_type_lower = prop_type.lower() if prop_type else ""
        if (
            prop_type_lower in ["date", "datetime", "timestamp"]
            or "date" in prop_type_lower
            or "time" in prop_type_lower
        ):
            is_datetime_type = True
        if data_sampler and node_type:
            prop_name = prop.get("name", "unknown")
            sampled_value = data_sampler.sample_property_value(
                node_type, prop_name, prop_type
            )
            if sampled_value.startswith("'") and sampled_value.endswith("'"):
                sampled_value = sampled_value[1:-1]
            if prop_type in ["int", "integer"]:
                try:
                    value_expr = Value(int(sampled_value))
                except ValueError:
                    value_expr = Value(sampled_value)
            elif prop_type == "float":
                try:
                    value_expr = Value(float(sampled_value))
                except ValueError:
                    value_expr = Value(sampled_value)
            elif prop_type == "bool" or prop_type == "boolean":
                if isinstance(sampled_value, str):
                    sampled_value_lower = sampled_value.lower().strip()
                    if sampled_value_lower in ("true", "1"):
                        value_expr = Value(True)
                    elif sampled_value_lower in ("false", "0"):
                        value_expr = Value(False)
                    else:
                        value_expr = Value(False)
                elif isinstance(sampled_value, bool):
                    value_expr = Value(sampled_value)
                else:
                    value_expr = Value(bool(sampled_value))
            else:
                value_expr = Value(sampled_value)
            date_str = (
                str(value_expr.value)
                if hasattr(value_expr, "value")
                else str(value_expr)
            )
            if date_str.endswith("Z"):
                date_str = date_str[:-1]
            if is_datetime_type and gql_type == "nebula":
                if len(date_str) == 10 and "-" in date_str:
                    format_str = "%Y-%m-%d"
                elif "T" in date_str:
                    format_str = "%Y-%m-%dT%H:%M:%S"
                else:
                    format_str = "%Y-%m-%d"
                return FunctionCall(
                    "localdatetime", [Value(date_str), Value(format_str)]
                )
            elif is_datetime_type and gql_type == "cypher":
                return FunctionCall("localdatetime", [Value(date_str)])
            else:
                return value_expr
        if prop_type == "string":
            if enum_values:
                value_expr = Value(random.choice(enum_values))
            else:
                string_values = [
                    "active",
                    "inactive",
                    "pending",
                    "completed",
                    "failed",
                    "test",
                    "example",
                    "sample",
                ]
                value_expr = Value(random.choice(string_values))
        elif prop_type == "int":
            if min_val is not None and max_val is not None:
                value_expr = Value(random.randint(int(min_val), int(max_val)))
            else:
                value_expr = Value(random.randint(1, 100))
        elif prop_type == "float":
            if min_val is not None and max_val is not None:
                value_expr = Value(
                    round(random.uniform(float(min_val), float(max_val)), 2)
                )
            else:
                value_expr = Value(round(random.uniform(1.0, 100.0), 2))
        elif prop_type == "bool":
            value_expr = Value(random.choice([True, False]))
        elif is_datetime_type:
            year = random.randint(2020, 2024)
            month = random.randint(1, 12)
            day = random.randint(1, 28)
            date_str = f"{year}-{month:02d}-{day:02d}"
            value_expr = Value(date_str)
        else:
            value_expr = Value("default")
        if is_datetime_type:
            date_str = (
                str(value_expr.value)
                if hasattr(value_expr, "value")
                else str(value_expr)
            )
            if date_str.endswith("Z"):
                date_str = date_str[:-1]
            if gql_type == "nebula":
                if len(date_str) == 10 and "-" in date_str:
                    format_str = "%Y-%m-%d"
                elif "T" in date_str:
                    format_str = "%Y-%m-%dT%H:%M:%S"
                else:
                    format_str = "%Y-%m-%d"
                return FunctionCall(
                    "local_datetime", [Value(date_str), Value(format_str)]
                )
            else:
                return FunctionCall("localdatetime", [Value(date_str)])
        else:
            return value_expr

    @classmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Where"]:
        variants = []
        node_types = schema.get("node_types", [])
        if not node_types:
            return variants
        properties = []
        for node_type in node_types:
            for prop in node_type.get("properties", []):
                properties.append((node_type["name"], prop))
        if not properties:
            return variants
        for (node_name, prop) in properties[:5]:
            identifier = Identifier("n")
            prop_ref = PropertyRef(identifier, prop["name"])
            if prop.get("type") == "string":
                value = Value("'example'")
                op = random.choice(["=", "CONTAINS", "STARTS WITH"])
            elif prop.get("type") in ["int", "float"]:
                value = Value(random.randint(1, 100))
                op = random.choice(["=", ">", "<", ">=", "<="])
            else:
                value = Value(True)
                op = "="
            condition = BinaryOp(prop_ref, op, value)
            variants.append(Where([condition]))
        if len(properties) >= 2:
            conditions = []
            for (node_name, prop) in properties[:2]:
                identifier = Identifier("n")
                prop_ref = PropertyRef(identifier, prop["name"])
                value = Value(
                    random.randint(1, 100)
                    if prop.get("type") in ["int", "float"]
                    else "'test'"
                )
                op = ">" if prop.get("type") in ["int", "float"] else "="
                condition = BinaryOp(prop_ref, op, value)
                conditions.append(condition)
            variants.append(Where(conditions, "AND"))
        if len(properties) >= 2:
            conditions = []
            for (node_name, prop) in properties[:2]:
                identifier = Identifier("n")
                prop_ref = PropertyRef(identifier, prop["name"])
                if prop.get("type") in ["int", "float"]:
                    value = Value(random.randint(1, 100))
                    op = "="
                elif prop.get("type") == "string":
                    value = Value("'test'")
                    op = "CONTAINS"
                else:
                    value = Value(True)
                    op = "="
                condition = BinaryOp(prop_ref, op, value)
                conditions.append(condition)
            variants.append(Where(conditions, "OR"))
        if len(properties) >= 4:
            cond1 = BinaryOp(
                PropertyRef(Identifier("n"), properties[0][1]["name"]), ">", Value(10)
            )
            cond2 = BinaryOp(
                PropertyRef(Identifier("n"), properties[1][1]["name"]),
                "=",
                Value("'active'"),
            )
            cond3 = BinaryOp(
                PropertyRef(Identifier("m"), properties[2][1]["name"]), "<", Value(50)
            )
            prop4_type = properties[3][1].get("type", "string")
            if prop4_type == "string":
                cond4 = BinaryOp(
                    PropertyRef(Identifier("m"), properties[3][1]["name"]),
                    "CONTAINS",
                    Value("'test'"),
                )
            else:
                cond4 = BinaryOp(
                    PropertyRef(Identifier("m"), properties[3][1]["name"]),
                    "=",
                    Value("'test'"),
                )
            nested_and1 = BinaryOp(cond1, "AND", cond2)
            nested_and2 = BinaryOp(cond3, "AND", cond4)
            nested_or = BinaryOp(nested_and1, "OR", nested_and2)
            variants.append(Where([nested_or]))
        return variants

    @classmethod
    def generate_variants_for_match(
        cls,
        match: Match,
        schema: Dict[str, Any],
        data_sampler: DataSampler = None,
        gql_type: str = "cypher",
    ) -> List["Where"]:
        variants: List[Where] = []
        var_to_labels: Dict[str, List[str]] = {}
        for pattern in match.patterns:
            if isinstance(pattern, NodePattern):
                if pattern.variable:
                    var_to_labels.setdefault(pattern.variable, [])
                    for lb in pattern.labels:
                        if lb not in var_to_labels[pattern.variable]:
                            var_to_labels[pattern.variable].append(lb)
            elif isinstance(pattern, PathPattern):
                start = pattern.start
                if start.variable:
                    var_to_labels.setdefault(start.variable, [])
                    for lb in start.labels:
                        if lb not in var_to_labels[start.variable]:
                            var_to_labels[start.variable].append(lb)
                for (_, node) in pattern.segments:
                    if node.variable:
                        var_to_labels.setdefault(node.variable, [])
                        for lb in node.labels:
                            if lb not in var_to_labels[node.variable]:
                                var_to_labels[node.variable].append(lb)
        label_to_props: Dict[str, List[Dict[str, Any]]] = {}
        for node_type in schema.get("node_types", []):
            label_to_props[node_type["name"]] = node_type.get("properties", [])
        candidate_props: List[Tuple[str, Dict[str, Any]]] = []
        for (var, labels) in var_to_labels.items():
            props_seen: set = set()
            for lb in labels or []:
                for prop in label_to_props.get(lb, []):
                    pname = prop.get("name")
                    if pname and pname not in props_seen:
                        candidate_props.append((var, lb, prop))
                        props_seen.add(pname)
        if not candidate_props:
            return variants
        condi_list = []
        for (var, lb, prop) in candidate_props[:5]:
            identifier = Identifier(var)
            prop_ref = PropertyRef(identifier, prop["name"])
            value = cls._generate_value_for_property(prop, data_sampler, lb, gql_type)
            if prop.get("type") == "string":
                op = random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            elif prop.get("type") in ["int", "float"]:
                op = random.choice(["=", ">", "<", ">=", "<=", "<>"])
            else:
                op = "="
            variants.append(Where([BinaryOp(prop_ref, op, value)]))
            condi_list.append(BinaryOp(prop_ref, op, value))
        for (var, lb, prop) in candidate_props[:3]:
            identifier = Identifier(var)
            prop_ref = PropertyRef(identifier, prop["name"])
            variants.append(Where([UnaryOp("IS NULL", prop_ref)]))
            variants.append(Where([UnaryOp("IS NOT NULL", prop_ref)]))
            condi_list.append(UnaryOp("IS NULL", prop_ref))
            condi_list.append(UnaryOp("IS NOT NULL", prop_ref))
        for (var, lb, prop) in candidate_props[:3]:
            identifier = Identifier(var)
            prop_ref = PropertyRef(identifier, prop["name"])
            if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                list_len = random.randint(3, 5)
                sampled_values = []
                for _ in range(list_len):
                    v = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(v, "value"):
                        sampled_values.append(Value(v.value))
                    else:
                        sampled_values.append(v)
                values = sampled_values
            variants.append(Where([InOp(prop_ref, values)]))
            condi_list.append(InOp(prop_ref, values))
        for (var, lb, prop) in candidate_props[:3]:
            identifier = Identifier(var)
            prop_ref = PropertyRef(identifier, prop["name"])
            if prop.get("type") in ["int", "float"]:
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    sampled_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(sampled_value, "value"):
                        sampled_value = Value(sampled_value.value)
                else:
                    sampled_value = Value(50)
                op = random.choice(["=", ">", "<", ">=", "<="])
                condition = BinaryOp(prop_ref, op, sampled_value)
            elif prop.get("type") == "string":
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    sampled_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(sampled_value, "value"):
                        sampled_value = Value(sampled_value.value)
                else:
                    sampled_value = Value("test")
                op = random.choice(["=", "<>", "CONTAINS", "STARTS WITH", "ENDS WITH"])
                condition = BinaryOp(prop_ref, op, sampled_value)
            else:
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    sampled_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(sampled_value, "value"):
                        sampled_value = Value(sampled_value.value)
                else:
                    sampled_value = Value("test")
                op = random.choice(["=", "<>"])
                condition = BinaryOp(prop_ref, op, sampled_value)
            variants.append(Where([UnaryOp("NOT", condition)]))
            condi_list.append(condition)
        for (var, lb, prop) in candidate_props[:2]:
            if prop.get("type") == "string":
                identifier = Identifier(var)
                prop_ref = PropertyRef(identifier, prop["name"])
                trim_expr = StringOp("TRIM", prop_ref)
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    trimmed_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(trimmed_value, "value"):
                        trimmed_value = Value(trimmed_value.value)
                else:
                    trimmed_value = Value("trimmed_value")
                variants.append(Where([BinaryOp(trim_expr, "=", trimmed_value)]))
                condi_list.append(BinaryOp(trim_expr, "=", trimmed_value))
                lower_expr = StringOp("TOLOWER", prop_ref)
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    contains_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(contains_value, "value"):
                        contains_value = Value(contains_value.value)
                else:
                    contains_value = Value("search")
                variants.append(
                    Where([BinaryOp(lower_expr, "CONTAINS", contains_value)])
                )
                condi_list.append(BinaryOp(lower_expr, "CONTAINS", contains_value))
                if gql_type != "nebula":
                    replace_expr = StringOp(
                        "REPLACE", prop_ref, [Value(" "), Value("_")]
                    )
                    if (
                        hasattr(cls, "_generate_value_for_property")
                        and data_sampler
                        and lb
                    ):
                        replace_result = cls._generate_value_for_property(
                            prop, data_sampler, lb, gql_type
                        )
                        if hasattr(replace_result, "value"):
                            replace_result = Value(replace_result.value)
                    else:
                        replace_result = Value("result")
                    variants.append(
                        Where([BinaryOp(replace_expr, "=", replace_result)])
                    )
                    condi_list.append(BinaryOp(replace_expr, "=", replace_result))
                start_idx = random.randint(0, 5)
                sub_len = random.randint(1, 6)
                substring_expr = StringOp(
                    "SUBSTRING", prop_ref, [Value(start_idx), Value(sub_len)]
                )
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    full_sampled_value = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(full_sampled_value, "value"):
                        full_value = full_sampled_value.value
                    else:
                        full_value = str(full_sampled_value)
                    if not isinstance(full_value, str):
                        full_value = str(full_value)
                    if len(full_value) > start_idx:
                        actual_sub_len = min(sub_len, len(full_value) - start_idx)
                        substring_value = Value(
                            full_value[start_idx : start_idx + actual_sub_len]
                        )
                    else:
                        substring_value = Value("pre")
                else:
                    substring_value = Value("pre")
                variants.append(Where([BinaryOp(substring_expr, "=", substring_value)]))
                condi_list.append(BinaryOp(substring_expr, "=", substring_value))
                length_func = FunctionCall("SIZE", [prop_ref])
                length_value = Value(random.randint(3, 10))
                variants.append(Where([BinaryOp(length_func, ">", length_value)]))
                condi_list.append(BinaryOp(length_func, ">", length_value))
                sampled_regex_value = None
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    regex_base = cls._generate_value_for_property(
                        prop, data_sampler, lb, gql_type
                    )
                    if hasattr(regex_base, "value"):
                        regex_base = regex_base.value
                    if isinstance(regex_base, str):
                        regex_base_str = regex_base
                    else:
                        regex_base_str = str(regex_base)
                    regex_templates = [
                        lambda s: f"(?i){s}.*",
                        lambda s: f"^{s}$",
                        lambda s: f".*{s}.*",
                        lambda s: f"{s}[0-9]*",
                        lambda s: f"{s}|{s.upper()}",
                        lambda s: f"(?i).*{s[:2]}.*" if len(s) >= 2 else f"(?i){s}.*",
                    ]
                    regex_pattern = random.choice(regex_templates)(regex_base_str)
                else:
                    regex_pattern = "(?i)default.*"
                variants.append(Where([BinaryOp(prop_ref, "=~", Value(regex_pattern))]))
                condi_list.append(BinaryOp(prop_ref, "=~", Value(regex_pattern)))
        if len(candidate_props) >= 4:
            (var1, lb1, prop1) = candidate_props[0]
            (var2, lb2, prop2) = candidate_props[1]
            (var3, lb3, prop3) = candidate_props[2]
            (var4, lb4, prop4) = candidate_props[3]
            identifier1 = Identifier(var1)
            identifier2 = Identifier(var2)
            identifier3 = Identifier(var3)
            identifier4 = Identifier(var4)
            prop_ref1 = PropertyRef(identifier1, prop1["name"])
            prop_ref2 = PropertyRef(identifier2, prop2["name"])
            prop_ref3 = PropertyRef(identifier3, prop3["name"])
            prop_ref4 = PropertyRef(identifier4, prop4["name"])
            value1 = cls._generate_value_for_property(
                prop1, data_sampler, lb1, gql_type
            )
            value2 = cls._generate_value_for_property(
                prop2, data_sampler, lb2, gql_type
            )
            value3 = cls._generate_value_for_property(
                prop3, data_sampler, lb3, gql_type
            )
            value4 = cls._generate_value_for_property(
                prop4, data_sampler, lb4, gql_type
            )
            if prop1.get("type") in ["int", "float"]:
                op1 = random.choice(["=", ">", "<", ">=", "<="])
            elif prop1.get("type") == "string":
                op1 = random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            else:
                op1 = random.choice(["=", "<>"])
            if prop2.get("type") in ["int", "float"]:
                op2 = random.choice(["=", ">", "<", ">=", "<="])
            elif prop2.get("type") == "string":
                op2 = random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            else:
                op2 = random.choice(["=", "<>"])
            if prop3.get("type") in ["int", "float"]:
                op3 = random.choice(["=", ">", "<", ">=", "<="])
            elif prop3.get("type") == "string":
                op3 = random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            else:
                op3 = random.choice(["=", "<>"])
            if prop4.get("type") in ["int", "float"]:
                op4 = random.choice(["=", ">", "<", ">=", "<="])
            elif prop4.get("type") == "string":
                op4 = random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            else:
                op4 = random.choice(["=", "<>"])
            cond1 = BinaryOp(prop_ref1, op1, value1)
            cond2 = BinaryOp(prop_ref2, op2, value2)
            cond3 = BinaryOp(prop_ref3, op3, value3)
            cond4 = BinaryOp(prop_ref4, op4, value4)
            and1 = BinaryOp(cond1, "AND", cond2)
            and2 = BinaryOp(cond3, "AND", cond4)
            or_cond = BinaryOp(and1, "OR", and2)
            variants.append(Where([or_cond]))
            op1 = (
                random.choice(["=", ">", "<", ">=", "<="])
                if prop1.get("type") in ["int", "float"]
                else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            )
            op2 = (
                random.choice(["=", ">", "<", ">=", "<="])
                if prop2.get("type") in ["int", "float"]
                else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            )
            op3 = (
                random.choice(["=", ">", "<", ">=", "<="])
                if prop3.get("type") in ["int", "float"]
                else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            )
            op4 = (
                random.choice(["=", ">", "<", ">=", "<="])
                if prop4.get("type") in ["int", "float"]
                else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
            )
            or1 = BinaryOp(cond1, "OR", cond2)
            or2 = BinaryOp(cond3, "OR", cond4)
            and_cond = BinaryOp(or1, "AND", or2)
            variants.append(Where([and_cond]))
        if len(candidate_props) >= 2:
            (var1, lb1, prop1) = candidate_props[0]
            (var2, lb2, prop2) = candidate_props[1]
            identifier1 = Identifier(var1)
            identifier2 = Identifier(var2)
            prop_ref1 = PropertyRef(identifier1, prop1["name"])
            prop_ref2 = PropertyRef(identifier2, prop2["name"])
            if prop1.get("type") in ["int", "float"] and prop2.get("type") in [
                "int",
                "float",
            ]:
                cond1 = UnaryOp("IS NOT NULL", prop_ref1)
                value2 = cls()._generate_value_for_property(prop2, data_sampler, lb2)
                cond2 = BinaryOp(prop_ref2, ">", value2)
                variants.append(Where([cond1, cond2], "AND"))
        if len(candidate_props) >= 3:
            (var1, lb1, prop1) = candidate_props[0]
            (var2, lb2, prop2) = candidate_props[1]
            (var3, lb3, prop3) = candidate_props[2]
            identifier1 = Identifier(var1)
            identifier2 = Identifier(var2)
            identifier3 = Identifier(var3)
            prop_ref1 = PropertyRef(identifier1, prop1["name"])
            prop_ref2 = PropertyRef(identifier2, prop2["name"])
            prop_ref3 = PropertyRef(identifier3, prop3["name"])
            if (
                prop1.get("type") in ["int", "float"]
                and prop2.get("type") in ["int", "float"]
                and (prop3.get("type") in ["int", "float"])
            ):
                value1 = cls()._generate_value_for_property(prop1, data_sampler, lb1)
                value2 = cls()._generate_value_for_property(prop2, data_sampler, lb2)
                value3 = cls()._generate_value_for_property(prop3, data_sampler, lb3)
                op1 = (
                    random.choice(["=", ">", "<", ">=", "<="])
                    if prop1.get("type") in ["int", "float"]
                    else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
                )
                op2 = (
                    random.choice(["=", ">", "<", ">=", "<="])
                    if prop2.get("type") in ["int", "float"]
                    else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
                )
                op3 = (
                    random.choice(["=", ">", "<", ">=", "<="])
                    if prop3.get("type") in ["int", "float"]
                    else random.choice(["=", "CONTAINS", "STARTS WITH", "ENDS WITH"])
                )
                cond1 = BinaryOp(prop_ref1, op1, value1)
                cond2 = BinaryOp(prop_ref2, op2, value2)
                cond3 = BinaryOp(prop_ref3, op3, value3)
                nested_and = BinaryOp(cond1, op1, cond2)
                nested_or = BinaryOp(nested_and, op2, cond3)
                variants.append(Where([nested_or]))
        if len(candidate_props) >= 1:
            (var, lb, prop) = candidate_props[0]
            if prop.get("type") in ["int", "float"]:
                identifier = Identifier(var)
                prop_ref = PropertyRef(identifier, prop["name"])
                value = cls._generate_value_for_property(prop, data_sampler, lb)
                case_expr = CaseOp(
                    when_conditions=[(BinaryOp(prop_ref, ">", value), Value("adult"))],
                    else_result=Value("minor"),
                )
                variants.append(Where([BinaryOp(case_expr, "=", Value("adult"))]))
        for (var, lb, prop) in candidate_props[:3]:
            if prop.get("type") == "string":
                identifier = Identifier(var)
                prop_ref = PropertyRef(identifier, prop["name"])
                length_func = FunctionCall("SIZE", [prop_ref])
                random_int = random.randint(2, 15)
                variants.append(Where([BinaryOp(length_func, ">", Value(random_int))]))
                upper_func = StringOp("TOUPPER", prop_ref)
                sampled_str = None
                if data_sampler and lb:
                    sampled_str = data_sampler.sample_property_value(
                        lb, prop["name"], "string"
                    )
                    if (
                        isinstance(sampled_str, str)
                        and sampled_str.startswith("'")
                        and sampled_str.endswith("'")
                    ):
                        sampled_str = sampled_str[1:-1]
                if not sampled_str:
                    sampled_str = "SAMPLE_STR"
                variants.append(
                    Where([BinaryOp(upper_func, "=", Value(sampled_str.upper()))])
                )
                condi_list.append(BinaryOp(upper_func, "=", Value(sampled_str.upper())))
        for (var, lb, prop) in candidate_props[:2]:
            if prop.get("type") in ["int", "float"]:
                identifier = Identifier(var)
                prop_ref = PropertyRef(identifier, prop["name"])
                value = cls._generate_value_for_property(prop, data_sampler, lb)
                rand_int1 = random.randint(2, 10)
                rand_int2 = random.randint(1, 20)
                rand_ops = ["+", "-", "*", "/"]
                rand_op1 = random.choice(rand_ops)
                math_expr_rand = MathOp(prop_ref, rand_op1, Value(rand_int1))
                variants.append(Where([BinaryOp(math_expr_rand, ">", value)]))
                rand_op2 = random.choice(rand_ops)
                nested_math_expr = MathOp(math_expr_rand, rand_op2, Value(rand_int2))
                variants.append(Where([BinaryOp(nested_math_expr, "<", value)]))
                condi_list.append(BinaryOp(math_expr_rand, ">", value))
                condi_list.append(BinaryOp(nested_math_expr, "<", value))
        if len(candidate_props) >= 4:
            (var1, lb1, prop1) = candidate_props[0]
            (var2, lb2, prop2) = candidate_props[1]
            (var3, lb3, prop3) = candidate_props[2]
            (var4, lb4, prop4) = candidate_props[3]
            identifier1 = Identifier(var1)
            identifier2 = Identifier(var2)
            identifier3 = Identifier(var3)
            identifier4 = Identifier(var4)
            prop_ref1 = PropertyRef(identifier1, prop1["name"])
            prop_ref2 = PropertyRef(identifier2, prop2["name"])
            prop_ref3 = PropertyRef(identifier3, prop3["name"])
            prop_ref4 = PropertyRef(identifier4, prop4["name"])
            if all(
                (
                    p.get("type") in ["int", "float"]
                    for p in [prop1, prop2, prop3, prop4]
                )
            ):
                value1 = cls()._generate_value_for_property(prop1, data_sampler, lb1)
                value2 = cls()._generate_value_for_property(prop2, data_sampler, lb2)
                value3 = cls()._generate_value_for_property(prop3, data_sampler, lb3)
                value4 = cls()._generate_value_for_property(prop4, data_sampler, lb4)
                cond1 = BinaryOp(prop_ref1, ">", value1)
                cond2 = BinaryOp(prop_ref2, "<", value2)
                cond3 = BinaryOp(prop_ref3, "=", value3)
                cond4 = BinaryOp(prop_ref4, ">=", value4)
                nested_and1 = BinaryOp(cond1, "AND", cond2)
                nested_and2 = BinaryOp(cond3, "AND", cond4)
                nested_or = BinaryOp(nested_and1, "OR", nested_and2)
                extra_cond = BinaryOp(prop_ref1, "IS NOT NULL", Value(None))
                final_cond = BinaryOp(nested_or, "AND", extra_cond)
                variants.append(Where([final_cond]))
        for (var, lb, prop) in candidate_props[:2]:
            if prop.get("type") == "string":
                identifier = Identifier(var)
                prop_ref = PropertyRef(identifier, prop["name"])
                sampled_value = None
                if hasattr(cls, "_generate_value_for_property") and data_sampler and lb:
                    sampled_val = cls._generate_value_for_property(
                        prop, data_sampler, lb
                    )
                    if hasattr(sampled_val, "value"):
                        sampled_value = sampled_val.value
                    else:
                        sampled_value = str(sampled_val)
                else:
                    sampled_value = random.choice(
                        ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
                    )
                if isinstance(sampled_value, str):
                    str_len = len(sampled_value)
                    if str_len > 0:
                        start_idx = random.randint(0, max(0, str_len - 1))
                        max_sub_len = min(5, str_len - start_idx)
                        sub_len = random.randint(1, max(1, max_sub_len))
                        substr_func = StringOp(
                            "SUBSTRING", prop_ref, [Value(start_idx), Value(sub_len)]
                        )
                        substr_val = sampled_value[start_idx : start_idx + sub_len]
                        variants.append(
                            Where([BinaryOp(substr_func, "=", Value(substr_val))])
                        )
                        condi_list.append(BinaryOp(substr_func, "=", Value(substr_val)))
                if gql_type != "nebula":
                    replace_func = StringOp(
                        "REPLACE", prop_ref, [Value(" "), Value("_")]
                    )
                    if (
                        hasattr(cls, "_generate_value_for_property")
                        and data_sampler
                        and lb
                    ):
                        replace_value = cls._generate_value_for_property(
                            prop, data_sampler, lb
                        )
                        if hasattr(replace_value, "value"):
                            replace_value = Value(replace_value.value)
                        else:
                            replace_value = Value("replace_value")
                    variants.append(
                        Where([BinaryOp(replace_func, "CONTAINS", replace_value)])
                    )
                    condi_list.append(BinaryOp(replace_func, "CONTAINS", replace_value))
        for (var, lb, prop) in candidate_props[:2]:
            identifier = Identifier(var)
            prop_ref = PropertyRef(identifier, prop["name"])
            value = cls._generate_value_for_property(prop, data_sampler, lb)
            inner_cond = BinaryOp(prop_ref, ">", value)
            not_inner = UnaryOp("NOT", inner_cond)
            not_not = UnaryOp("NOT", not_inner)
            variants.append(Where([not_not]))
            condi_list.append(UnaryOp("NOT", inner_cond))
            condi_list.append(UnaryOp("NOT", not_inner))
        if len(condi_list) >= 2:
            for _ in range(3):
                selected_conds = random.sample(condi_list, 2)
                variants.append(Where(selected_conds, "AND"))
            if len(condi_list) >= 3:
                for _ in range(2):
                    selected_conds = random.sample(condi_list, 3)
                    variants.append(Where(selected_conds, "AND"))
        if len(condi_list) >= 2:
            for _ in range(3):
                selected_conds = random.sample(condi_list, 2)
                variants.append(Where(selected_conds, "OR"))
            if len(condi_list) >= 3:
                for _ in range(2):
                    selected_conds = random.sample(condi_list, 3)
                    variants.append(Where(selected_conds, "OR"))
        if len(condi_list) >= 4:
            for _ in range(2):
                conds1 = random.sample(condi_list, 2)
                conds2 = random.sample(condi_list, 2)
                and1 = BinaryOp(conds1[0], "AND", conds1[1])
                and2 = BinaryOp(conds2[0], "AND", conds2[1])
                or_cond = BinaryOp(and1, "OR", and2)
                variants.append(Where([or_cond]))
        return variants


class Return(Clause):
    def __init__(self, expressions: List[Expression], distinct: bool = False):
        self.expressions = expressions
        self.distinct = distinct

    def to_cypher(self) -> str:
        if not self.expressions:
            return "RETURN *"
        distinct_str = "DISTINCT " if self.distinct else ""
        expr_str = ", ".join((expr.to_cypher() for expr in self.expressions))
        return f"RETURN {distinct_str}{expr_str}"

    def to_nebula(self) -> str:
        if not self.expressions:
            return "RETURN *"
        distinct_str = "DISTINCT " if self.distinct else ""
        expr_str = ", ".join(
            (
                expr.to_nebula() if hasattr(expr, "to_nebula") else expr.to_cypher()
                for expr in self.expressions
            )
        )
        return f"RETURN {distinct_str}{expr_str}"

    @classmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Return"]:
        variants = []
        node_types = schema.get("node_types", [])
        if not node_types:
            return variants
        variants.append(Return([]))
        for node_type in node_types[:3]:
            identifier = Identifier("n")
            variants.append(Return([identifier]))
        if len(node_types) >= 2:
            identifiers = [Identifier(f"n{i}") for i in range(min(3, len(node_types)))]
            variants.append(Return(identifiers))
        for node_type in node_types[:2]:
            for prop in node_type.get("properties", [])[:2]:
                identifier = Identifier("n")
                prop_ref = PropertyRef(identifier, prop["name"])
                variants.append(Return([prop_ref]))
        for node_type in node_types[:2]:
            for prop in node_type.get("properties", []):
                if prop.get("type") in ["int", "float"]:
                    identifier = Identifier("n")
                    prop_ref = PropertyRef(identifier, prop["name"])
                    for func in ["COUNT", "SUM", "AVG", "MIN", "MAX"]:
                        func_expr = Identifier(f"{func}(n.{prop['name']})")
                        variants.append(Return([func_expr]))
                    break
        if variants:
            distinct_variant = random.choice(variants[1:])
            distinct_variant.distinct = True
            variants.append(distinct_variant)
        return variants

    @classmethod
    def generate_variants_for_match(
        cls, match: Match, schema: Dict[str, Any], gql_type: str = "cypher"
    ) -> List["Return"]:
        variants: List[Return] = []
        vars_list: List[str] = []
        var_to_labels: Dict[str, List[str]] = {}
        label_to_props: Dict[str, List[Dict[str, Any]]] = {
            nt["name"]: nt.get("properties", []) for nt in schema.get("node_types", [])
        }
        for pattern in match.patterns:
            if isinstance(pattern, NodePattern):
                if pattern.variable and pattern.variable not in vars_list:
                    vars_list.append(pattern.variable)
                    var_to_labels[pattern.variable] = pattern.labels
            elif isinstance(pattern, PathPattern):
                if pattern.start.variable and pattern.start.variable not in vars_list:
                    vars_list.append(pattern.start.variable)
                    var_to_labels[pattern.start.variable] = pattern.start.labels
                for (_, node) in pattern.segments:
                    if node.variable and node.variable not in vars_list:
                        vars_list.append(node.variable)
                        var_to_labels[node.variable] = node.labels
        if not vars_list:
            return variants
        variants.append(Return([]))
        for var in vars_list[:3]:
            variants.append(Return([Identifier(var)]))
        if len(vars_list) >= 2:
            variants.append(Return([Identifier(v) for v in vars_list[:3]]))
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, [])[:3]:
                    variants.append(
                        Return([PropertyRef(Identifier(var), prop["name"])])
                    )
        for (var, labels) in var_to_labels.items():
            props_for_var = []
            for lb in labels or []:
                for prop in label_to_props.get(lb, [])[:2]:
                    props_for_var.append(PropertyRef(Identifier(var), prop["name"]))
            if len(props_for_var) >= 2:
                variants.append(Return(props_for_var[:2]))
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, [])[:2]:
                    variants.append(
                        Return(
                            [
                                Identifier(var),
                                PropertyRef(Identifier(var), prop["name"]),
                            ]
                        )
                    )
        if len(vars_list) >= 2:
            all_props = []
            for (var, labels) in var_to_labels.items():
                for lb in labels or []:
                    for prop in label_to_props.get(lb, [])[:1]:
                        all_props.append(PropertyRef(Identifier(var), prop["name"]))
                        break
            if len(all_props) >= 2:
                variants.append(Return(all_props[:3]))
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, []):
                    if prop.get("type") in ["int", "float"]:
                        identifier = Identifier(var)
                        prop_ref = PropertyRef(identifier, prop["name"])
                        count_func = FunctionCall("COUNT", [identifier])
                        sum_func = FunctionCall("SUM", [prop_ref])
                        avg_func = FunctionCall("AVG", [prop_ref])
                        min_func = FunctionCall("MIN", [prop_ref])
                        max_func = FunctionCall("MAX", [prop_ref])
                        variants.append(Return([count_func]))
                        variants.append(Return([sum_func]))
                        variants.append(Return([avg_func]))
                        variants.append(Return([min_func]))
                        variants.append(Return([max_func]))
                        count_alias = AliasExpr(count_func, "total_count")
                        sum_alias = AliasExpr(sum_func, f"total_{prop['name']}")
                        avg_alias = AliasExpr(avg_func, f"avg_{prop['name']}")
                        variants.append(Return([count_alias]))
                        variants.append(Return([sum_alias]))
                        variants.append(Return([avg_alias]))
                        variants.append(Return([count_alias, sum_alias]))
                        variants.append(Return([avg_alias, min_func, max_func]))
                        break
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, []):
                    if prop.get("type") == "string":
                        identifier = Identifier(var)
                        prop_ref = PropertyRef(identifier, prop["name"])
                        upper_func = StringOp("TOUPPER", prop_ref)
                        lower_func = StringOp("TOLOWER", prop_ref)
                        length_func = FunctionCall("SIZE", [prop_ref])
                        trim_func = StringOp("TRIM", prop_ref)
                        variants.append(Return([upper_func]))
                        variants.append(Return([lower_func]))
                        variants.append(Return([length_func]))
                        variants.append(Return([trim_func]))
                        upper_alias = AliasExpr(upper_func, "upper_name")
                        lower_alias = AliasExpr(lower_func, "lower_name")
                        length_alias = AliasExpr(length_func, "name_length")
                        variants.append(Return([upper_alias]))
                        variants.append(Return([lower_alias]))
                        variants.append(Return([length_alias]))
                        variants.append(Return([upper_alias, length_alias]))
                        variants.append(Return([lower_alias, trim_func]))
                        substr_func = StringOp(
                            "SUBSTRING", prop_ref, [Value(0), Value(3)]
                        )
                        substr_alias = AliasExpr(substr_func, "name_prefix")
                        variants.append(Return([substr_alias]))
                        if gql_type != "nebula":
                            replace_func = StringOp(
                                "REPLACE", prop_ref, [Value(" "), Value("_")]
                            )
                            concat_func = StringOp(
                                "CONCAT", prop_ref, [Value("_suffix")]
                            )
                            replace_alias = AliasExpr(replace_func, "clean_name")
                            concat_alias = AliasExpr(concat_func, "modified_name")
                            variants.append(Return([replace_alias]))
                            variants.append(Return([concat_alias]))
                            variants.append(Return([substr_alias, replace_alias]))
                        break
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, []):
                    if prop.get("type") in ["int", "float"]:
                        identifier = Identifier(var)
                        prop_ref = PropertyRef(identifier, prop["name"])
                        add_expr = MathOp(prop_ref, "+", Value(10))
                        sub_expr = MathOp(prop_ref, "-", Value(5))
                        mul_expr = MathOp(prop_ref, "*", Value(2))
                        div_expr = MathOp(prop_ref, "/", Value(2))
                        add_alias = AliasExpr(add_expr, f"{prop['name']}_plus_10")
                        sub_alias = AliasExpr(sub_expr, f"{prop['name']}_minus_5")
                        mul_alias = AliasExpr(mul_expr, f"{prop['name']}_doubled")
                        div_alias = AliasExpr(div_expr, f"{prop['name']}_halved")
                        variants.append(Return([add_alias]))
                        variants.append(Return([sub_alias]))
                        variants.append(Return([mul_alias]))
                        variants.append(Return([div_alias]))
                        complex_expr = MathOp(
                            MathOp(prop_ref, "*", Value(2)), "+", Value(5)
                        )
                        complex_alias = AliasExpr(
                            complex_expr, f"{prop['name']}_complex"
                        )
                        variants.append(Return([complex_alias]))
                        variants.append(Return([add_alias, mul_alias]))
                        variants.append(Return([sub_alias, div_alias]))
                        break
        for (var, labels) in var_to_labels.items():
            for lb in labels or []:
                for prop in label_to_props.get(lb, []):
                    if prop.get("type") in ["int", "float"]:
                        identifier = Identifier(var)
                        prop_ref = PropertyRef(identifier, prop["name"])
                        age_case = CaseOp(
                            when_conditions=[
                                (BinaryOp(prop_ref, ">=", Value(65)), Value("senior")),
                                (BinaryOp(prop_ref, ">=", Value(18)), Value("adult")),
                                (BinaryOp(prop_ref, ">=", Value(13)), Value("teen")),
                            ],
                            else_result=Value("child"),
                        )
                        age_alias = AliasExpr(age_case, "age_group")
                        variants.append(Return([age_alias]))
                        range_case = CaseOp(
                            when_conditions=[
                                (BinaryOp(prop_ref, ">", Value(100)), Value("high")),
                                (BinaryOp(prop_ref, ">", Value(50)), Value("medium")),
                            ],
                            else_result=Value("low"),
                        )
                        range_alias = AliasExpr(range_case, f"{prop['name']}_level")
                        variants.append(Return([range_alias]))
                        break
                    elif prop.get("type") == "string":
                        identifier = Identifier(var)
                        prop_ref = PropertyRef(identifier, prop["name"])
                        length_case = CaseOp(
                            when_conditions=[
                                (
                                    BinaryOp(
                                        FunctionCall("SIZE", [prop_ref]), ">", Value(10)
                                    ),
                                    Value("long"),
                                ),
                                (
                                    BinaryOp(
                                        FunctionCall("SIZE", [prop_ref]), ">", Value(5)
                                    ),
                                    Value("medium"),
                                ),
                            ],
                            else_result=Value("short"),
                        )
                        length_alias = AliasExpr(length_case, "name_length_category")
                        variants.append(Return([length_alias]))
                        break
        if len(vars_list) >= 2:
            var1 = vars_list[0]
            var2 = vars_list[1] if len(vars_list) > 1 else vars_list[0]
            for (var, labels) in var_to_labels.items():
                for lb in labels or []:
                    for prop in label_to_props.get(lb, []):
                        if prop.get("type") in ["int", "float"]:
                            identifier = Identifier(var)
                            prop_ref = PropertyRef(identifier, prop["name"])
                            math_expr = MathOp(prop_ref, "*", Value(1.1))
                            math_alias = AliasExpr(
                                math_expr, f"{prop['name']}_increased"
                            )
                            count_func = FunctionCall("COUNT", [identifier])
                            count_alias = AliasExpr(count_func, "node_count")
                            variants.append(
                                Return([Identifier(var1), math_alias, count_alias])
                            )
                            break
                    break
        if len(variants) > 1:
            for _ in range(3):
                distinct_variant = random.choice(variants[1:])
                distinct_variant.distinct = True
                variants.append(distinct_variant)
        if len(vars_list) >= 2:
            all_nodes = [Identifier(var) for var in vars_list]
            variants.append(Return(all_nodes))
        for (var, labels) in var_to_labels.items():
            if labels:
                label_expr = Value(labels[0]) if labels else Value("Unknown")
                label_alias = AliasExpr(label_expr, "node_type")
                variants.append(Return([Identifier(var), label_alias]))
        for pattern in match.patterns:
            if isinstance(pattern, PathPattern):
                for (rel, _) in pattern.segments:
                    if rel.types:
                        rel_type_expr = Value(rel.types[0])
                        rel_type_alias = AliasExpr(rel_type_expr, "relationship_type")
                        variants.append(Return([rel_type_alias]))
        return variants


class Limit(Clause):
    def __init__(self, limit_value: Union[int, Expression]):
        self.limit_value = limit_value

    def to_cypher(self) -> str:
        if isinstance(self.limit_value, Expression):
            return f"LIMIT {self.limit_value.to_cypher()}"
        return f"LIMIT {self.limit_value}"

    def to_nebula(self) -> str:
        if isinstance(self.limit_value, Expression):
            return f"LIMIT {(self.limit_value.to_nebula() if hasattr(self.limit_value, 'to_nebula') else self.limit_value.to_cypher())}"
        return f"LIMIT {self.limit_value}"

    @classmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Limit"]:
        variants = []
        for limit in [1, 5, 10, 20, 50, 100]:
            variants.append(Limit(limit))
        for _ in range(3):
            limit = random.randint(1, 100)
            variants.append(Limit(limit))
        return variants


class Order(Clause):
    def __init__(self, expressions: List[Expression], directions: List[str] = None):
        self.expressions = expressions
        self.directions = directions or ["ASC"] * len(expressions)

    def to_cypher(self) -> str:
        if not self.expressions:
            return ""
        order_items = []
        for (expr, direction) in zip(self.expressions, self.directions):
            order_items.append(f"{expr.to_cypher()} {direction}")
        return f"ORDER BY {', '.join(order_items)}"

    def to_nebula(self) -> str:
        if not self.expressions:
            return ""
        order_items = []
        for (expr, direction) in zip(self.expressions, self.directions):
            expr_str = (
                expr.to_nebula() if hasattr(expr, "to_nebula") else expr.to_cypher()
            )
            order_items.append(f"{expr_str} {direction}")
        return f"ORDER BY {', '.join(order_items)}"

    @classmethod
    def generate_variants(cls, schema: Dict[str, Any]) -> List["Order"]:
        variants = []
        node_types = schema.get("node_types", [])
        if not node_types:
            return variants
        sortable_props = []
        for node_type in node_types:
            for prop in node_type.get("properties", []):
                if prop.get("type") in ["int", "float", "string"]:
                    sortable_props.append((node_type["name"], prop))
        if not sortable_props:
            return variants
        for (node_name, prop) in sortable_props[:5]:
            identifier = Identifier("n")
            prop_ref = PropertyRef(identifier, prop["name"])
            variants.append(Order([prop_ref], ["ASC"]))
            variants.append(Order([prop_ref], ["DESC"]))
        if len(sortable_props) >= 2:
            for i in range(min(3, len(sortable_props) - 1)):
                prop1 = sortable_props[i]
                prop2 = sortable_props[i + 1]
                identifier1 = Identifier("n")
                identifier2 = Identifier("m")
                prop_ref1 = PropertyRef(identifier1, prop1[1]["name"])
                prop_ref2 = PropertyRef(identifier2, prop2[1]["name"])
                for (dir1, dir2) in [
                    ("ASC", "ASC"),
                    ("ASC", "DESC"),
                    ("DESC", "ASC"),
                    ("DESC", "DESC"),
                ]:
                    variants.append(Order([prop_ref1, prop_ref2], [dir1, dir2]))
        return variants

    @classmethod
    def generate_variants_for_match(
        cls, match: Match, schema: Dict[str, Any]
    ) -> List["Order"]:
        variants: List[Order] = []
        var_to_labels: Dict[str, List[str]] = {}
        for pattern in match.patterns:
            if isinstance(pattern, NodePattern) and pattern.variable:
                var_to_labels.setdefault(pattern.variable, []).extend(pattern.labels)
            elif isinstance(pattern, PathPattern):
                if pattern.start.variable:
                    var_to_labels.setdefault(pattern.start.variable, []).extend(
                        pattern.start.labels
                    )
                for (_, node) in pattern.segments:
                    if node.variable:
                        var_to_labels.setdefault(node.variable, []).extend(node.labels)
        label_to_props: Dict[str, List[Dict[str, Any]]] = {
            nt["name"]: nt.get("properties", []) for nt in schema.get("node_types", [])
        }
        sortable: List[Tuple[PropertyRef, str]] = []
        for (var, labels) in var_to_labels.items():
            for lb in list(dict.fromkeys(labels)):
                for prop in label_to_props.get(lb, []):
                    if prop.get("type") in ["int", "float", "string"]:
                        sortable.append(
                            (PropertyRef(Identifier(var), prop["name"]), prop["type"])
                        )
        if not sortable:
            return variants
        for (pref, _) in sortable[:5]:
            variants.append(Order([pref], ["ASC"]))
            variants.append(Order([pref], ["DESC"]))
        if len(sortable) >= 2:
            for i in range(min(3, len(sortable) - 1)):
                pref1 = sortable[i][0]
                pref2 = sortable[i + 1][0]
                for (dir1, dir2) in [
                    ("ASC", "ASC"),
                    ("ASC", "DESC"),
                    ("DESC", "ASC"),
                    ("DESC", "DESC"),
                ]:
                    variants.append(Order([pref1, pref2], [dir1, dir2]))
        return variants


class CypherTemplateGenerator:
    def __init__(self, data_dir: str = "./data"):
        self.data_sampler = DataSampler(data_dir)

    def load_schema(self, path: str) -> List[dict]:
        import json

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _collect_match_variables(self, match_clause: Match) -> List[str]:
        vars_list: List[str] = []
        for pattern in match_clause.patterns:
            if isinstance(pattern, NodePattern):
                if pattern.variable and pattern.variable not in vars_list:
                    vars_list.append(pattern.variable)
            elif isinstance(pattern, PathPattern):
                if pattern.start.variable and pattern.start.variable not in vars_list:
                    vars_list.append(pattern.start.variable)
                for (_, node) in pattern.segments:
                    if node.variable and node.variable not in vars_list:
                        vars_list.append(node.variable)
        return vars_list

    def _replace_constants_with_sampled_values(
        self, template: str, schema: dict
    ) -> str:
        import re

        string_pattern = "'([^']+)'"

        def replace_string(match):
            original_value = match.group(1)
            for node_type in schema.get("node_types", []):
                for prop in node_type.get("properties", []):
                    if prop.get("type") == "string":
                        sampled_value = self.data_sampler.sample_property_value(
                            node_type["name"], prop["name"], "string"
                        )
                        return sampled_value
            return self.data_sampler._generate_random_value("string")

        template = re.sub(string_pattern, replace_string, template)
        number_pattern = "\\b(\\d+(?:\\.\\d+)?)\\b"

        def replace_number(match):
            original_value = match.group(1)
            if "." in original_value:
                return self.data_sampler._generate_random_value("float")
            else:
                return self.data_sampler._generate_random_value("int")

        template = re.sub(number_pattern, replace_number, template)
        return template

    def _default_return_for_match(self, match_clause: Match) -> Return:
        vars_list = self._collect_match_variables(match_clause)
        if vars_list:
            return Return([Identifier(v) for v in vars_list])
        return Return([])

    def generate_templates_for_schema(
        self, schema: dict, gql_type: str = "cypher"
    ) -> List[dict]:
        templates = []

        def to_gql(clause):
            if gql_type == "nebula":
                return (
                    clause.to_nebula()
                    if hasattr(clause, "to_nebula")
                    else clause.to_cypher()
                )
            else:
                return clause.to_cypher()

        match_variants = Match.generate_variants(schema)
        selected_match_variants = random.sample(
            match_variants, min(8, len(match_variants))
        )
        print(
            [
                tmp
                for tmp in match_variants
                if hasattr(tmp, "has_optional") and tmp.has_optional
            ]
        )
        print(
            [
                tmp
                for tmp in match_variants
                if hasattr(tmp, "has_optional")
                and tmp.has_optional
                and (tmp not in selected_match_variants)
            ]
        )
        selected_match_variants.extend(
            [
                tmp
                for tmp in match_variants
                if hasattr(tmp, "has_optional")
                and tmp.has_optional
                and (tmp not in selected_match_variants)
            ]
        )
        for match_clause in selected_match_variants:
            ret_clause = self._default_return_for_match(match_clause)
            combined = f"{to_gql(match_clause)}\n{to_gql(ret_clause)}"
            templates.append(
                {
                    "template": combined,
                    "type": "match",
                    "complexity": "basic"
                    if self._count_hops(match_clause) < 2
                    else "medium",
                    "hops": self._count_hops(match_clause),
                }
            )
        for match_clause in selected_match_variants:
            where_variants = Where.generate_variants_for_match(
                match_clause, schema, self.data_sampler, gql_type
            )
            selected_where_variants = random.sample(
                where_variants, min(10, len(where_variants))
            )
            for where_clause in selected_where_variants:
                if not where_clause.conditions:
                    continue
                ret_clause = self._default_return_for_match(match_clause)
                combined = f"{to_gql(match_clause)}\n{to_gql(where_clause)}\n{to_gql(ret_clause)}"
                templates.append(
                    {
                        "template": combined,
                        "type": "match_where",
                        "complexity": "medium",
                        "hops": self._count_hops(match_clause),
                    }
                )
        for match_clause in selected_match_variants:
            where_variants = Where.generate_variants_for_match(
                match_clause, schema, self.data_sampler, gql_type
            )
            return_variants = Return.generate_variants_for_match(
                match_clause, schema, gql_type
            )
            selected_where_variants = random.sample(
                where_variants, min(3, len(where_variants))
            )
            for where_clause in selected_where_variants:
                selected_return_variants = random.sample(
                    return_variants, min(5, len(return_variants))
                )
                for return_clause in selected_return_variants:
                    if not where_clause.conditions:
                        continue
                    combined = f"{to_gql(match_clause)}\n{to_gql(where_clause)}\n{to_gql(return_clause)}"
                    templates.append(
                        {
                            "template": combined,
                            "type": "match_where_return",
                            "complexity": "medium",
                            "hops": self._count_hops(match_clause),
                        }
                    )
        limit_variants = Limit.generate_variants(schema)
        for match_clause in selected_match_variants:
            where_variants = Where.generate_variants_for_match(
                match_clause, schema, self.data_sampler, gql_type
            )
            return_variants = Return.generate_variants_for_match(
                match_clause, schema, gql_type
            )
            order_variants = Order.generate_variants_for_match(match_clause, schema)
            selected_where_variants = random.sample(
                where_variants, min(2, len(where_variants))
            )
            for where_clause in selected_where_variants:
                selected_return_variants = random.sample(
                    return_variants, min(3, len(return_variants))
                )
                for return_clause in selected_return_variants:
                    selected_order_variants = random.sample(
                        order_variants, min(2, len(order_variants))
                    )
                    for order_clause in selected_order_variants:
                        selected_limit_variants = random.sample(
                            limit_variants, min(2, len(limit_variants))
                        )
                        for limit_clause in selected_limit_variants:
                            if (
                                not where_clause.conditions
                                or not order_clause.expressions
                            ):
                                continue
                            combined = f"{to_gql(match_clause)}\n{to_gql(where_clause)}\n{to_gql(order_clause)}\n{to_gql(return_clause)}\n{to_gql(limit_clause)}"
                            templates.append(
                                {
                                    "template": combined,
                                    "type": "complete_query",
                                    "complexity": "high",
                                    "hops": self._count_hops(match_clause),
                                }
                            )
        for match_clause in selected_match_variants:
            where_variants = Where.generate_variants_for_match(
                match_clause, schema, self.data_sampler, gql_type
            )
            return_variants = Return.generate_variants_for_match(
                match_clause, schema, gql_type
            )
            order_variants = Order.generate_variants_for_match(match_clause, schema)
            selected_where_variants = random.sample(
                where_variants, min(2, len(where_variants))
            )
            for where_clause in selected_where_variants:
                selected_return_variants = random.sample(
                    return_variants, min(2, len(return_variants))
                )
                for return_clause in selected_return_variants:
                    selected_order_variants = random.sample(
                        order_variants, min(2, len(order_variants))
                    )
                    for order_clause in selected_order_variants:
                        for limit_clause in limit_variants[:2]:
                            if (
                                not where_clause.conditions
                                or not order_clause.expressions
                            ):
                                continue
                            combined = f"{to_gql(match_clause)}\n{to_gql(where_clause)}\n{to_gql(order_clause)}\n{to_gql(return_clause)}\n{to_gql(limit_clause)}"
                            templates.append(
                                {
                                    "template": combined,
                                    "type": "complete_query_with_order",
                                    "complexity": "high",
                                    "hops": self._count_hops(match_clause),
                                }
                            )
        return templates

    def generate_complex_queries(
        self, schema: dict, gql_type: str = "cypher"
    ) -> List[dict]:
        complex_templates = []

        def to_gql(clause):
            if gql_type == "nebula":
                return (
                    clause.to_nebula()
                    if hasattr(clause, "to_nebula")
                    else clause.to_cypher()
                )
            else:
                return clause.to_cypher()

        node_types = schema.get("node_types", [])
        if node_types:
            for node_type in node_types[:2]:
                for prop in node_type.get("properties", []):
                    if prop.get("type") in ["int", "float"]:
                        node = NodePattern(variable="n", labels=[node_type["name"]])
                        match = Match([node])
                        identifier = Identifier("n")
                        prop_ref = PropertyRef(identifier, prop["name"])
                        count_expr = FunctionCall("COUNT", [identifier])
                        sum_expr = FunctionCall("SUM", [prop_ref])
                        count_alias = AliasExpr(count_expr, "res1")
                        sum_alias = AliasExpr(sum_expr, "res2")
                        return_clause = Return([count_alias, sum_alias])
                        order_by_alias = random.choice(["res1", "res2"])
                        order_direction = random.choice(["ASC", "DESC"])
                        order_clause = Order(
                            [Identifier(order_by_alias)], [order_direction]
                        )
                        limit_clause = Limit(1)
                        combined = f"{to_gql(match)}\n{to_gql(return_clause)}\n{to_gql(order_clause)}\n{to_gql(limit_clause)}"
                        complex_templates.append(
                            {
                                "template": combined,
                                "type": "aggregation",
                                "complexity": "medium",
                                "hops": 0,
                            }
                        )
                        break
        rel_types = schema.get("relationship_types", [])
        if rel_types:
            rel_type = rel_types[0]
            start_node = NodePattern(
                variable="n", labels=[rel_type.get("from_node", "Node")]
            )
            end_node = NodePattern(
                variable="m", labels=[rel_type.get("to_node", "Node")]
            )
            rel = RelationshipPattern(
                variable="r", types=[rel_type["name"]], direction="->"
            )
            path = PathPattern(start=start_node, segments=[(rel, end_node)])
            match = Match([path])
            length_expr = Identifier("LENGTH(p)")
            length_alias = AliasExpr(length_expr, "path_length")
            return_clause = Return([Identifier("n"), Identifier("m"), length_alias])
            limit_clause = Limit(10)
            order_clause = Order([Identifier("path_length")], ["ASC"])
            match_clause = to_gql(match)
            match_clause = match_clause.replace("MATCH ", "MATCH p=")
            combined = f"{match_clause}\n{to_gql(return_clause)}\n{to_gql(order_clause)}\n{to_gql(limit_clause)}"
            complex_templates.append(
                {
                    "template": combined,
                    "type": "path_length",
                    "complexity": "medium",
                    "hops": 1,
                }
            )
        return complex_templates

    def _count_hops(self, match_clause: Match) -> int:
        if not match_clause.patterns:
            return 0
        max_hops = 0
        for pattern in match_clause.patterns:
            if isinstance(pattern, PathPattern):
                hops = len(pattern.segments)
                max_hops = max(max_hops, hops)
            elif isinstance(pattern, NodePattern):
                max_hops = max(max_hops, 0)
        return max_hops

    def save_templates(self, templates: List[dict], output_file: str) -> None:
        import json

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)


def _build_min_demo_schema() -> dict:

    return {
        "name": "demo_system",
        "domain": "演示",
        "node_types": [
            {
                "name": "Customer",
                "properties": [
                    {
                        "name": "customer_id",
                        "type": "string",
                        "enum_values": ["C001", "C002", "C003", "C004", "C005"],
                    },
                    {"name": "age", "type": "int", "min_value": 18, "max_value": 80},
                    {
                        "name": "status",
                        "type": "string",
                        "enum_values": ["active", "inactive", "pending", "suspended"],
                    },
                    {"name": "name", "type": "string"},
                    {"name": "phone", "type": "string"},
                ],
            },
            {
                "name": "Account",
                "properties": [
                    {
                        "name": "account_id",
                        "type": "string",
                        "enum_values": ["A001", "A002", "A003", "A004", "A005"],
                    },
                    {
                        "name": "balance",
                        "type": "float",
                        "min_value": 0.0,
                        "max_value": 100000.0,
                    },
                    {
                        "name": "account_type",
                        "type": "string",
                        "enum_values": ["savings", "checking", "business", "premium"],
                    },
                    {
                        "name": "currency",
                        "type": "string",
                        "enum_values": ["USD", "EUR", "GBP", "JPY"],
                    },
                ],
            },
            {
                "name": "Transaction",
                "properties": [
                    {
                        "name": "amount",
                        "type": "int",
                        "min_value": 1,
                        "max_value": 10000,
                    },
                    {
                        "name": "status",
                        "type": "string",
                        "enum_values": ["completed", "pending", "failed", "cancelled"],
                    },
                    {
                        "name": "transaction_type",
                        "type": "string",
                        "enum_values": ["transfer", "deposit", "withdrawal", "payment"],
                    },
                ],
            },
        ],
        "relationship_types": [
            {
                "name": "OWNS",
                "from_node": "Customer",
                "to_node": "Account",
                "directed": True,
            },
            {
                "name": "TRANSFERS_TO",
                "from_node": "Account",
                "to_node": "Account",
                "directed": True,
            },
            {
                "name": "FROM_ACCOUNT",
                "from_node": "Transaction",
                "to_node": "Account",
                "directed": True,
            },
            {
                "name": "TO_ACCOUNT",
                "from_node": "Transaction",
                "to_node": "Account",
                "directed": True,
            },
        ],
    }


def demo_generate_and_print(limit_count: int = 10) -> None:

    import os, json

    base_dir = os.path.dirname(__file__)
    schemas_dir = os.path.join(base_dir, "schemas")
    template_dir = os.path.join(base_dir, "templates")
    os.makedirs(template_dir, exist_ok=True)
    schema_files = [f for f in os.listdir(schemas_dir) if f.endswith(".json")]
    print(f"找到 {len(schema_files)} 个schema文件")
    all_templates = []
    gen = CypherTemplateGenerator(data_dir="./data")
    for schema_file in schema_files:
        schema_name = schema_file.replace(".json", "")
        print(f"\n处理schema文件: {schema_name}")
        with open(os.path.join(schemas_dir, schema_file), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            schemas = data
            print(f"  文件包含 {len(schemas)} 个schema")
        else:
            schemas = [data]
            print(f"  文件包含 1 个schema")
        for (i, schema) in enumerate(schemas):
            schema_display_name = schema.get("name", f"Unknown_{i + 1}")
            print(f"    处理第 {i + 1} 个schema: {schema_display_name}")
            print(f"      节点类型数量: {len(schema.get('node_types', []))}")
            print(f"      关系类型数量: {len(schema.get('relationship_types', []))}")
            templates_cypher = gen.generate_templates_for_schema(
                schema, gql_type="cypher"
            )
            complex_templates_cypher = gen.generate_complex_queries(
                schema, gql_type="cypher"
            )
            schema_templates_cypher = templates_cypher + complex_templates_cypher
            templates_nebula = gen.generate_templates_for_schema(
                schema, gql_type="nebula"
            )
            complex_templates_nebula = gen.generate_complex_queries(
                schema, gql_type="nebula"
            )
            schema_templates_nebula = templates_nebula + complex_templates_nebula
            print(f"      生成了 {len(schema_templates_cypher)} 个 Cypher 模板")
            print(f"      生成了 {len(schema_templates_nebula)} 个 Nebula 模板")
            domain_en = schema.get(
                "domain", schema_name.replace("_schemas", "").replace("_", "-")
            )
            domain_en = domain_en.replace(" ", "_").replace("-", "_")
            output_filename_cypher = f"templates_cypher_{domain_en}_schemas_{i + 1}_{schema_display_name}.json"
            output_file_cypher = os.path.join(template_dir, output_filename_cypher)
            with open(output_file_cypher, "w", encoding="utf-8") as f:
                json.dump(schema_templates_cypher, f, ensure_ascii=False, indent=2)
            print(f"      Cypher 模板已保存到: {output_file_cypher}")
            output_filename_nebula = f"templates_nebula_{domain_en}_schemas_{i + 1}_{schema_display_name}.json"
            output_file_nebula = os.path.join(template_dir, output_filename_nebula)
            with open(output_file_nebula, "w", encoding="utf-8") as f:
                json.dump(schema_templates_nebula, f, ensure_ascii=False, indent=2)
            print(f"      Nebula 模板已保存到: {output_file_nebula}")
            schema_templates = schema_templates_cypher
            print(
                f"      ==== {schema_display_name} 的模板示例(前{min(5, len(schema_templates))}条) ===="
            )
            for (j, t) in enumerate(schema_templates[:5], 1):
                print(f"        --- Template #{j} ---")
                print(f"        {t.get('template', '')}")
                meta = {k: t[k] for k in ["type", "complexity", "hops"] if k in t}
                if meta:
                    print(f"        [meta] {meta}")
            all_templates.extend(schema_templates)
    print(f"\n总共生成了 {len(all_templates)} 个模板")


if __name__ == "__main__":

    print("=== 基础模板示例 ===")
    demo_generate_and_print(limit_count=1050)
    print("\n" + "=" * 60)
