"""
## Expressions
Adapter from sqlglot

Every AST node in SQLGlot is represented by a subclass of `Expression`.

This module contains the implementation of all supported `Expression` types. Additionally,
it exposes a number of helper functions, which are mainly used to programmatically build
SQL expressions, such as `sqlglot.expressions.select`.

----
"""

from __future__ import annotations

import datetime
import math
import numbers
import re
import textwrap
import typing as t
from collections import deque
from copy import deepcopy
from decimal import Decimal
from enum import auto
from functools import reduce
import copy

from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.helper import (
    AutoName,
    camel_to_snake_case,
    ensure_collection,
    ensure_list,
    seq_get,
    split_num_words,
    to_bool,
)
from sqlglot.tokens import Token, TokenError

if t.TYPE_CHECKING:
    from typing_extensions import Self

    from sqlglot._typing import E, Lit
    from sqlglot.dialects.dialect import DialectType

    Q = t.TypeVar("Q", bound="Query")
    S = t.TypeVar("S", bound="SetOperation")

QUERY_MODIFIERS = {
    "match": False,
    "laterals": False,
    "joins": False,
    "connect": False,
    "pivots": False,
    "prewhere": False,
    "where": False,
    "group": False,
    "having": False,
    "qualify": False,
    "windows": False,
    "distribute": False,
    "sort": False,
    "cluster": False,
    "order": False,
    "limit": False,
    "offset": False,
    "locks": False,
    "sample": False,
    "settings": False,
    "format": False,
    "options": False,
}


class _Expression(type):
    def __new__(cls, clsname, bases, attrs):
        klass = super().__new__(cls, clsname, bases, attrs)

        klass.key = clsname.lower()

        klass.__doc__ = klass.__doc__ or ""

        return klass

class Expression(metaclass=_Expression):
    """
    The base class for all expressions in a syntax tree. Each Expression encapsulates any necessary
    context, such as its child expressions, their names (arg keys), and whether a given child expression
    is optional or not.

    Attributes:
        key: a unique key for each class in the Expression hierarchy. This is useful for hashing
            and representing expressions as strings.
        arg_types: determines the arguments (child nodes) supported by an expression. It maps
            arg keys to booleans that indicate whether the corresponding args are optional.
        parent: a reference to the parent expression (or None, in case of root expressions).
        arg_key: the arg key an expression is associated with, i.e. the name its parent expression
            uses to refer to it.
        index: the index of an expression if it is inside of a list argument in its parent.
        comments: a list of comments that are associated with a given expression. This is used in
            order to preserve comments when transpiling SQL code.
        type: the `sqlglot.expressions.DataType` type of an expression. This is inferred by the
            optimizer, in order to enable some transformations that require type information.
        meta: a dictionary that can be used to store useful metadata for a given expression.

    Example:
        >>> class Foo(Expression):
        ...     arg_types = {"this": True, "expression": False}

        The above definition informs us that Foo is an Expression that requires an argument called
        "this" and may also optionally receive an argument called "expression".

    Args:
        args: a mapping used for retrieving the arguments of an expression, given their arg keys.
    """

    key = "expression"
    arg_types = {"this": True}
    __slots__ = ("args", "parent", "arg_key", "index", "comments", "_type", "_meta", "_hash")

    def __init__(self, **args: t.Any):
        self.args: t.Dict[str, t.Any] = args
        self.parent: t.Optional[Expression] = None
        self.arg_key: t.Optional[str] = None
        self.index: t.Optional[int] = None
        self.comments: t.Optional[t.List[str]] = None
        self._type: t.Optional[DataType] = None
        self._meta: t.Optional[t.Dict[str, t.Any]] = None
        self._hash: t.Optional[int] = None

        for arg_key, value in self.args.items():
            self._set_parent(arg_key, value)

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and hash(self) == hash(other)

    @property
    def hashable_args(self) -> t.Any:
        return frozenset(
            (k, tuple(_norm_arg(a) for a in v) if type(v) is list else _norm_arg(v))
            for k, v in self.args.items()
            if not (v is None or v is False or (type(v) is list and not v))
        )

    def __hash__(self) -> int:
        if self._hash is not None:
            return self._hash

        return hash((self.__class__, self.hashable_args))

    @property
    def this(self) -> t.Any:
        """
        Retrieves the argument with key "this".
        """
        return self.args.get("this")

    @property
    def expression(self) -> t.Any:
        """
        Retrieves the argument with key "expression".
        """
        return self.args.get("expression")

    @property
    def expressions(self) -> t.List[t.Any]:
        """
        Retrieves the argument with key "expressions".
        """
        return self.args.get("expressions") or []

    def text(self, key) -> str:
        """
        Returns a textual representation of the argument corresponding to "key". This can only be used
        for args that are strings or leaf Expression instances, such as identifiers and literals.
        """
        field = self.args.get(key)
        if isinstance(field, str):
            return field
        if isinstance(field, (Identifier, Literal, Var)):
            return field.this
        if isinstance(field, (Star, Null)):
            return field.name
        return ""

    @property
    def is_string(self) -> bool:
        """
        Checks whether a Literal expression is a string.
        """
        return isinstance(self, Literal) and self.args["is_string"]

    @property
    def is_number(self) -> bool:
        """
        Checks whether a Literal expression is a number.
        """
        return (isinstance(self, Literal) and not self.args["is_string"]) or (
            isinstance(self, Neg) and self.this.is_number
        )

    def to_py(self) -> t.Any:
        """
        Returns a Python object equivalent of the SQL node.
        """
        raise ValueError(f"{self} cannot be converted to a Python object.")

    @property
    def is_int(self) -> bool:
        """
        Checks whether an expression is an integer.
        """
        return self.is_number and isinstance(self.to_py(), int)

    @property
    def is_star(self) -> bool:
        """Checks whether an expression is a star."""
        return isinstance(self, Star) or (isinstance(self, Column) and isinstance(self.this, Star))

    @property
    def alias(self) -> str:
        """
        Returns the alias of the expression, or an empty string if it's not aliased.
        """
        if isinstance(self.args.get("alias"), TableAlias):
            return self.args["alias"].name
        return self.text("alias")

    @property
    def alias_column_names(self) -> t.List[str]:
        table_alias = self.args.get("alias")
        if not table_alias:
            return []
        return [c.name for c in table_alias.args.get("columns") or []]

    @property
    def name(self) -> str:
        return self.text("this")

    @property
    def alias_or_name(self) -> str:
        return self.alias or self.name

    @property
    def output_name(self) -> str:
        """
        Name of the output column if this expression is a selection.

        If the Expression has no output name, an empty string is returned.

        Example:
            >>> from sqlglot import parse_one
            >>> parse_one("SELECT a").expressions[0].output_name
            'a'
            >>> parse_one("SELECT b AS c").expressions[0].output_name
            'c'
            >>> parse_one("SELECT 1 + 2").expressions[0].output_name
            ''
        """
        return ""

    @property
    def type(self) -> t.Optional[DataType]:
        return self._type

    @type.setter
    def type(self, dtype: t.Optional[DataType | DataType.Type | str]) -> None:
        if dtype and not isinstance(dtype, DataType):
            dtype = DataType.build(dtype)
        self._type = dtype

    def is_type(self, *dtypes) -> bool:

        return self.type is not None and self.type.is_type(*dtypes)

    def is_leaf(self) -> bool:
        return not any(isinstance(v, (Expression, list)) for v in self.args.values())

    @property
    def meta(self) -> t.Dict[str, t.Any]:
        if self._meta is None:
            self._meta = {}
        return self._meta

    def __deepcopy__(self, memo):
        root = self.__class__()
        stack = [(self, root)]

        while stack:
            node, copy = stack.pop()

            if node.comments is not None:
                copy.comments = deepcopy(node.comments)
            if node._type is not None:
                copy._type = deepcopy(node._type)
            if node._meta is not None:
                copy._meta = deepcopy(node._meta)
            if node._hash is not None:
                copy._hash = node._hash

            for k, vs in node.args.items():
                if hasattr(vs, "parent"):
                    stack.append((vs, vs.__class__()))
                    copy.set(k, stack[-1][-1])
                elif type(vs) is list:
                    copy.args[k] = []

                    for v in vs:
                        if hasattr(v, "parent"):
                            stack.append((v, v.__class__()))
                            copy.append(k, stack[-1][-1])
                        else:
                            copy.append(k, v)
                else:
                    copy.args[k] = vs

        return root

    def copy(self) -> Self:
        """
        Returns a deep copy of the expression.
        """
        return deepcopy(self)

    def add_comments(self, comments: t.Optional[t.List[str]] = None, prepend: bool = False) -> None:
        if self.comments is None:
            self.comments = []

        if comments:
            for comment in comments:
                _, *meta = comment.split(SQLGLOT_META)
                if meta:
                    for kv in "".join(meta).split(","):
                        k, *v = kv.split("=")
                        value = v[0].strip() if v else True
                        self.meta[k.strip()] = to_bool(value)

                if not prepend:
                    self.comments.append(comment)

            if prepend:
                self.comments = comments + self.comments

    def pop_comments(self) -> t.List[str]:
        comments = self.comments or []
        self.comments = None
        return comments

    def append(self, arg_key: str, value: t.Any) -> None:
        """
        Appends value to arg_key if it's a list or sets it as a new list.

        Args:
            arg_key (str): name of the list expression arg
            value (Any): value to append to the list
        """
        if type(self.args.get(arg_key)) is not list:
            self.args[arg_key] = []
        self._set_parent(arg_key, value)
        values = self.args[arg_key]
        if hasattr(value, "parent"):
            value.index = len(values)
        values.append(value)

    def set(
        self,
        arg_key: str,
        value: t.Any,
        index: t.Optional[int] = None,
        overwrite: bool = True,
    ) -> None:
        """
        Sets arg_key to value.

        Args:
            arg_key: name of the expression arg.
            value: value to set the arg to.
            index: if the arg is a list, this specifies what position to add the value in it.
            overwrite: assuming an index is given, this determines whether to overwrite the
                list entry instead of only inserting a new value (i.e., like list.insert).
        """
        if index is not None:
            expressions = self.args.get(arg_key) or []

            if seq_get(expressions, index) is None:
                return
            if value is None:
                expressions.pop(index)
                for v in expressions[index:]:
                    v.index = v.index - 1
                return

            if isinstance(value, list):
                expressions.pop(index)
                expressions[index:index] = value
            elif overwrite:
                expressions[index] = value
            else:
                expressions.insert(index, value)

            value = expressions
        elif value is None:
            self.args.pop(arg_key, None)
            return

        self.args[arg_key] = value
        self._set_parent(arg_key, value, index)

    def _set_parent(self, arg_key: str, value: t.Any, index: t.Optional[int] = None) -> None:
        if hasattr(value, "parent"):
            value.parent = self
            value.arg_key = arg_key
            value.index = index
        elif type(value) is list:
            for index, v in enumerate(value):
                if hasattr(v, "parent"):
                    v.parent = self
                    v.arg_key = arg_key
                    v.index = index

    @property
    def depth(self) -> int:
        """
        Returns the depth of this tree.
        """
        if self.parent:
            return self.parent.depth + 1
        return 0

    def iter_expressions(self, reverse: bool = False) -> t.Iterator[Expression]:
        """Yields the key and expression for all arguments, exploding list args."""
        for vs in reversed(self.args.values()) if reverse else self.args.values():
            if type(vs) is list:
                for v in reversed(vs) if reverse else vs:
                    if hasattr(v, "parent"):
                        yield v
            else:
                if hasattr(vs, "parent"):
                    yield vs

    def find(self, *expression_types: t.Type[E], bfs: bool = True) -> t.Optional[E]:
        """
        Returns the first node in this tree which matches at least one of
        the specified types.

        Args:
            expression_types: the expression type(s) to match.
            bfs: whether to search the AST using the BFS algorithm (DFS is used if false).

        Returns:
            The node which matches the criteria or None if no such node was found.
        """
        return next(self.find_all(*expression_types, bfs=bfs), None)

    def find_all(self, *expression_types: t.Type[E], bfs: bool = True) -> t.Iterator[E]:
        """
        Returns a generator object which visits all nodes in this tree and only
        yields those that match at least one of the specified expression types.

        Args:
            expression_types: the expression type(s) to match.
            bfs: whether to search the AST using the BFS algorithm (DFS is used if false).

        Returns:
            The generator object.
        """
        for expression in self.walk(bfs=bfs):
            if isinstance(expression, expression_types):
                yield expression

    def find_ancestor(self, *expression_types: t.Type[E]) -> t.Optional[E]:
        """
        Returns a nearest parent matching expression_types.

        Args:
            expression_types: the expression type(s) to match.

        Returns:
            The parent node.
        """
        ancestor = self.parent
        while ancestor and not isinstance(ancestor, expression_types):
            ancestor = ancestor.parent
        return ancestor

    @property
    def parent_select(self) -> t.Optional[Select]:
        """
        Returns the parent select statement.
        """
        return self.find_ancestor(Select)

    @property
    def same_parent(self) -> bool:
        """Returns if the parent is the same class as itself."""
        return type(self.parent) is self.__class__

    def root(self) -> Expression:
        """
        Returns the root expression of this tree.
        """
        expression = self
        while expression.parent:
            expression = expression.parent
        return expression

    def walk(
        self, bfs: bool = True, prune: t.Optional[t.Callable[[Expression], bool]] = None
    ) -> t.Iterator[Expression]:
        """
        Returns a generator object which visits all nodes in this tree.

        Args:
            bfs: if set to True the BFS traversal order will be applied,
                otherwise the DFS traversal will be used instead.
            prune: callable that returns True if the generator should stop traversing
                this branch of the tree.

        Returns:
            the generator object.
        """
        if bfs:
            yield from self.bfs(prune=prune)
        else:
            yield from self.dfs(prune=prune)

    def dfs(
        self, prune: t.Optional[t.Callable[[Expression], bool]] = None
    ) -> t.Iterator[Expression]:
        """
        Returns a generator object which visits all nodes in this tree in
        the DFS (Depth-first) order.

        Returns:
            The generator object.
        """
        stack = [self]

        while stack:
            node = stack.pop()

            yield node

            if prune and prune(node):
                continue

            for v in node.iter_expressions(reverse=True):
                stack.append(v)

    def bfs(
        self, prune: t.Optional[t.Callable[[Expression], bool]] = None
    ) -> t.Iterator[Expression]:
        """
        Returns a generator object which visits all nodes in this tree in
        the BFS (Breadth-first) order.

        Returns:
            The generator object.
        """
        queue = deque([self])

        while queue:
            node = queue.popleft()

            yield node

            if prune and prune(node):
                continue

            for v in node.iter_expressions():
                queue.append(v)

    def unnest(self):
        """
        Returns the first non parenthesis child or self.
        """
        expression = self
        while type(expression) is Paren:
            expression = expression.this
        return expression

    def unalias(self):
        """
        Returns the inner expression if this is an Alias.
        """
        if isinstance(self, Alias):
            return self.this
        return self

    def unnest_operands(self):
        """
        Returns unnested operands as a tuple.
        """
        return tuple(arg.unnest() for arg in self.iter_expressions())

    def flatten(self, unnest=True):
        """
        Returns a generator which yields child nodes whose parents are the same class.

        A AND B AND C -> [A, B, C]
        """
        for node in self.dfs(prune=lambda n: n.parent and type(n) is not self.__class__):
            if type(node) is not self.__class__:
                yield node.unnest() if unnest and not isinstance(node, Subquery) else node

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return _to_s(self)

    def to_s(self) -> str:
        """
        Same as __repr__, but includes additional information which can be useful
        for debugging, like empty or missing args and the AST nodes' object IDs.
        """
        return _to_s(self, verbose=True)

    def sql(self, dialect: DialectType = None, **opts) -> str:
        """
        Returns SQL string representation of this tree.

        Args:
            dialect: the dialect of the output SQL string (eg. "spark", "hive", "presto", "mysql").
            opts: other `sqlglot.generator.Generator` options.

        Returns:
            The SQL string.
        """
        from sqlglot.dialects.dialect import Dialect

        return Dialect.get_or_raise(dialect).generate(self, **opts)

    def transform(self, fun: t.Callable, *args: t.Any, copy: bool = True, **kwargs) -> Expression:
        """
        Visits all tree nodes (excluding already transformed ones)
        and applies the given transformation function to each node.

        Args:
            fun: a function which takes a node as an argument and returns a
                new transformed node or the same node without modifications. If the function
                returns None, then the corresponding node will be removed from the syntax tree.
            copy: if set to True a new tree instance is constructed, otherwise the tree is
                modified in place.

        Returns:
            The transformed tree.
        """
        root = None
        new_node = None

        for node in (self.copy() if copy else self).dfs(prune=lambda n: n is not new_node):
            parent, arg_key, index = node.parent, node.arg_key, node.index
            new_node = fun(node, *args, **kwargs)

            if not root:
                root = new_node
            elif parent and arg_key and new_node is not node:
                parent.set(arg_key, new_node, index)

        assert root
        return root.assert_is(Expression)

    @t.overload
    def replace(self, expression: E) -> E: ...

    @t.overload
    def replace(self, expression: None) -> None: ...

    def replace(self, expression):
        """
        Swap out this expression with a new expression.

        For example::

            >>> tree = Select().select("x").from_("tbl")
            >>> tree.find(Column).replace(column("y"))
            Column(
              this=Identifier(this=y, quoted=False))
            >>> tree.sql()
            'SELECT y FROM tbl'

        Args:
            expression: new node

        Returns:
            The new expression or expressions.
        """
        parent = self.parent

        if not parent or parent is expression:
            return expression

        key = self.arg_key
        value = parent.args.get(key)

        if type(expression) is list and isinstance(value, Expression):

            value.parent.replace(expression)
        else:
            parent.set(key, expression, self.index)

        if expression is not self:
            self.parent = None
            self.arg_key = None
            self.index = None

        return expression

    def pop(self: E) -> E:
        """
        Remove this expression from its AST.

        Returns:
            The popped expression.
        """
        self.replace(None)
        return self

    def assert_is(self, type_: t.Type[E]) -> E:
        """
        Assert that this `Expression` is an instance of `type_`.

        If it is NOT an instance of `type_`, this raises an assertion error.
        Otherwise, this returns this expression.

        Examples:
            This is useful for type security in chained expressions:

            >>> import sqlglot
            >>> sqlglot.parse_one("SELECT x from y").assert_is(Select).select("z").sql()
            'SELECT x, z FROM y'
        """
        if not isinstance(self, type_):
            raise AssertionError(f"{self} is not {type_}.")
        return self

    def error_messages(self, args: t.Optional[t.Sequence] = None) -> t.List[str]:
        """
        Checks if this expression is valid (e.g. all mandatory args are set).

        Args:
            args: a sequence of values that were used to instantiate a Func expression. This is used
                to check that the provided arguments don't exceed the function argument limit.

        Returns:
            A list of error messages for all possible errors that were found.
        """
        errors: t.List[str] = []

        for k in self.args:
            if k not in self.arg_types:
                errors.append(f"Unexpected keyword: '{k}' for {self.__class__}")
        for k, mandatory in self.arg_types.items():
            v = self.args.get(k)
            if mandatory and (v is None or (isinstance(v, list) and not v)):
                errors.append(f"Required keyword: '{k}' missing for {self.__class__}")

        if (
            args
            and isinstance(self, Func)
            and len(args) > len(self.arg_types)
            and not self.is_var_len_args
        ):
            errors.append(
                f"The number of provided arguments ({len(args)}) is greater than "
                f"the maximum number of supported arguments ({len(self.arg_types)})"
            )

        return errors

    def dump(self):
        """
        Dump this Expression to a JSON-serializable dict.
        """
        from sqlglot.serde import dump

        return dump(self)

    @classmethod
    def load(cls, obj):
        """
        Load a dict (as returned by `Expression.dump`) into an Expression instance.
        """
        from sqlglot.serde import load

        return load(obj)

    def and_(
        self,
        *expressions: t.Optional[ExpOrStr],
        dialect: DialectType = None,
        copy: bool = True,
        wrap: bool = True,
        **opts,
    ) -> Condition:
        """
        AND this condition with one or multiple expressions.

        Example:
            >>> condition("x=1").and_("y=1").sql()
            'x = 1 AND y = 1'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
            dialect: the dialect used to parse the input expression.
            copy: whether to copy the involved expressions (only applies to Expressions).
            wrap: whether to wrap the operands in `Paren`s. This is true by default to avoid
                precedence issues, but can be turned off when the produced AST is too deep and
                causes recursion-related issues.
            opts: other options to use to parse the input expressions.

        Returns:
            The new And condition.
        """
        return and_(self, *expressions, dialect=dialect, copy=copy, wrap=wrap, **opts)

    def or_(
        self,
        *expressions: t.Optional[ExpOrStr],
        dialect: DialectType = None,
        copy: bool = True,
        wrap: bool = True,
        **opts,
    ) -> Condition:
        """
        OR this condition with one or multiple expressions.

        Example:
            >>> condition("x=1").or_("y=1").sql()
            'x = 1 OR y = 1'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
            dialect: the dialect used to parse the input expression.
            copy: whether to copy the involved expressions (only applies to Expressions).
            wrap: whether to wrap the operands in `Paren`s. This is true by default to avoid
                precedence issues, but can be turned off when the produced AST is too deep and
                causes recursion-related issues.
            opts: other options to use to parse the input expressions.

        Returns:
            The new Or condition.
        """
        return or_(self, *expressions, dialect=dialect, copy=copy, wrap=wrap, **opts)

    def not_(self, copy: bool = True):
        """
        Wrap this condition with NOT.

        Example:
            >>> condition("x=1").not_().sql()
            'NOT x = 1'

        Args:
            copy: whether to copy this object.

        Returns:
            The new Not instance.
        """
        return not_(self, copy=copy)

    def update_positions(
        self: E, other: t.Optional[Token | Expression] = None, **kwargs: t.Any
    ) -> E:
        """
        Update this expression with positions from a token or other expression.

        Args:
            other: a token or expression to update this expression with.

        Returns:
            The updated expression.
        """
        if isinstance(other, Expression):
            self.meta.update({k: v for k, v in other.meta.items() if k in POSITION_META_KEYS})
        elif other is not None:
            self.meta.update(
                {
                    "line": other.line,
                    "col": other.col,
                    "start": other.start,
                    "end": other.end,
                }
            )
        self.meta.update({k: v for k, v in kwargs.items() if k in POSITION_META_KEYS})
        return self

    def as_(
        self,
        alias: str | Identifier,
        quoted: t.Optional[bool] = None,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Alias:
        return alias_(self, alias, quoted=quoted, dialect=dialect, copy=copy, **opts)

    def _binop(self, klass: t.Type[E], other: t.Any, reverse: bool = False) -> E:
        this = self.copy()
        other = convert(other, copy=True)
        if not isinstance(this, klass) and not isinstance(other, klass):
            this = _wrap(this, Binary)
            other = _wrap(other, Binary)
        if reverse:
            return klass(this=other, expression=this)
        return klass(this=this, expression=other)

    def __getitem__(self, other: ExpOrStr | t.Tuple[ExpOrStr]) -> Bracket:
        return Bracket(
            this=self.copy(), expressions=[convert(e, copy=True) for e in ensure_list(other)]
        )

    def __iter__(self) -> t.Iterator:
        if "expressions" in self.arg_types:
            return iter(self.args.get("expressions") or [])

        raise TypeError(f"'{self.__class__.__name__}' object is not iterable")

    def isin(
        self,
        *expressions: t.Any,
        query: t.Optional[ExpOrStr] = None,
        unnest: t.Optional[ExpOrStr] | t.Collection[ExpOrStr] = None,
        copy: bool = True,
        **opts,
    ) -> In:
        subquery = maybe_parse(query, copy=copy, **opts) if query else None
        if subquery and not isinstance(subquery, Subquery):
            subquery = subquery.subquery(copy=False)

        return In(
            this=maybe_copy(self, copy),
            expressions=[convert(e, copy=copy) for e in expressions],
            query=subquery,
            unnest=(
                Unnest(
                    expressions=[
                        maybe_parse(t.cast(ExpOrStr, e), copy=copy, **opts)
                        for e in ensure_list(unnest)
                    ]
                )
                if unnest
                else None
            ),
        )

    def between(self, low: t.Any, high: t.Any, copy: bool = True, **opts) -> Between:
        return Between(
            this=maybe_copy(self, copy),
            low=convert(low, copy=copy, **opts),
            high=convert(high, copy=copy, **opts),
        )

    def is_(self, other: ExpOrStr) -> Is:
        return self._binop(Is, other)

    def like(self, other: ExpOrStr) -> Like:
        return self._binop(Like, other)

    def ilike(self, other: ExpOrStr) -> ILike:
        return self._binop(ILike, other)

    def eq(self, other: t.Any) -> EQ:
        return self._binop(EQ, other)

    def neq(self, other: t.Any) -> NEQ:
        return self._binop(NEQ, other)

    def rlike(self, other: ExpOrStr) -> RegexpLike:
        return self._binop(RegexpLike, other)

    def div(self, other: ExpOrStr, typed: bool = False, safe: bool = False) -> Div:
        div = self._binop(Div, other)
        div.args["typed"] = typed
        div.args["safe"] = safe
        return div

    def asc(self, nulls_first: bool = True) -> Ordered:
        return Ordered(this=self.copy(), nulls_first=nulls_first)

    def desc(self, nulls_first: bool = False) -> Ordered:
        return Ordered(this=self.copy(), desc=True, nulls_first=nulls_first)

    def __lt__(self, other: t.Any) -> LT:
        return self._binop(LT, other)

    def __le__(self, other: t.Any) -> LTE:
        return self._binop(LTE, other)

    def __gt__(self, other: t.Any) -> GT:
        return self._binop(GT, other)

    def __ge__(self, other: t.Any) -> GTE:
        return self._binop(GTE, other)

    def __add__(self, other: t.Any) -> Add:
        return self._binop(Add, other)

    def __radd__(self, other: t.Any) -> Add:
        return self._binop(Add, other, reverse=True)

    def __sub__(self, other: t.Any) -> Sub:
        return self._binop(Sub, other)

    def __rsub__(self, other: t.Any) -> Sub:
        return self._binop(Sub, other, reverse=True)

    def __mul__(self, other: t.Any) -> Mul:
        return self._binop(Mul, other)

    def __rmul__(self, other: t.Any) -> Mul:
        return self._binop(Mul, other, reverse=True)

    def __truediv__(self, other: t.Any) -> Div:
        return self._binop(Div, other)

    def __rtruediv__(self, other: t.Any) -> Div:
        return self._binop(Div, other, reverse=True)

    def __floordiv__(self, other: t.Any) -> IntDiv:
        return self._binop(IntDiv, other)

    def __rfloordiv__(self, other: t.Any) -> IntDiv:
        return self._binop(IntDiv, other, reverse=True)

    def __mod__(self, other: t.Any) -> Mod:
        return self._binop(Mod, other)

    def __rmod__(self, other: t.Any) -> Mod:
        return self._binop(Mod, other, reverse=True)

    def __pow__(self, other: t.Any) -> Pow:
        return self._binop(Pow, other)

    def __rpow__(self, other: t.Any) -> Pow:
        return self._binop(Pow, other, reverse=True)

    def __and__(self, other: t.Any) -> And:
        return self._binop(And, other)

    def __rand__(self, other: t.Any) -> And:
        return self._binop(And, other, reverse=True)

    def __or__(self, other: t.Any) -> Or:
        return self._binop(Or, other)

    def __ror__(self, other: t.Any) -> Or:
        return self._binop(Or, other, reverse=True)

    def __neg__(self) -> Neg:
        return Neg(this=_wrap(self.copy(), Binary))

    def __invert__(self) -> Not:
        return not_(self.copy())

    def flatten_binary(self,target_type) -> t.List[Expression]:
        """
        Flatten nested binary expressions of the given type.
        """
        if not isinstance(self,Binary):
            return self
        if isinstance(self, target_type):
            return self.left.flatten_binary(target_type) + self.right.flatten_binary(target_type)
        else:
            return [self]

    def is_twocol_EQ(self):
        """
            Return True if this is an equality condition between two columns.
        """
        if not isinstance(self,EQ):
            return False

        return isinstance(self.left,Column) and isinstance(self.right,Column)

IntoType = t.Union[
    str,
    t.Type[Expression],
    t.Collection[t.Union[str, t.Type[Expression]]],
]
ExpOrStr = t.Union[str, Expression]

class Condition(Expression):
    """Logical conditions like x AND y, or simply x"""

class Predicate(Condition):
    """Relationships like x = y, x > 1, x >= y."""

class DerivedTable(Expression):
    @property
    def selects(self) -> t.List[Expression]:
        return self.this.selects if isinstance(self.this, Query) else []

    @property
    def named_selects(self) -> t.List[str]:
        return [select.output_name for select in self.selects]

class Query(Expression):
    def subquery(self, alias: t.Optional[ExpOrStr] = None, copy: bool = True) -> Subquery:
        """
        Returns a `Subquery` that wraps around this query.

        Example:
            >>> subquery = Select().select("x").from_("tbl").subquery()
            >>> Select().select("x").from_(subquery).sql()
            'SELECT x FROM (SELECT x FROM tbl)'

        Args:
            alias: an optional alias for the subquery.
            copy: if `False`, modify this expression instance in-place.
        """
        instance = maybe_copy(self, copy)
        if not isinstance(alias, Expression):
            alias = TableAlias(this=to_identifier(alias)) if alias else None

        return Subquery(this=instance, alias=alias)

    def limit(
        self: Q, expression: ExpOrStr | int, dialect: DialectType = None, copy: bool = True, **opts
    ) -> Q:
        """
        Adds a LIMIT clause to this query.

        Example:
            >>> select("1").union(select("1")).limit(1).sql()
            'SELECT 1 UNION SELECT 1 LIMIT 1'

        Args:
            expression: the SQL code string to parse.
                This can also be an integer.
                If a `Limit` instance is passed, it will be used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `Limit`.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            A limited Select expression.
        """
        return _apply_builder(
            expression=expression,
            instance=self,
            arg="limit",
            into=Limit,
            prefix="LIMIT",
            dialect=dialect,
            copy=copy,
            into_arg="expression",
            **opts,
        )

    def offset(
        self: Q, expression: ExpOrStr | int, dialect: DialectType = None, copy: bool = True, **opts
    ) -> Q:
        """
        Set the OFFSET expression.

        Example:
            >>> Select().from_("tbl").select("x").offset(10).sql()
            'SELECT x FROM tbl OFFSET 10'

        Args:
            expression: the SQL code string to parse.
                This can also be an integer.
                If a `Offset` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `Offset`.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_builder(
            expression=expression,
            instance=self,
            arg="offset",
            into=Offset,
            prefix="OFFSET",
            dialect=dialect,
            copy=copy,
            into_arg="expression",
            **opts,
        )

    def order_by(
        self: Q,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Q:
        """
        Set the ORDER BY expression.

        Example:
            >>> Select().from_("tbl").select("x").order_by("x DESC").sql()
            'SELECT x FROM tbl ORDER BY x DESC'

        Args:
            *expressions: the SQL code strings to parse.
                If a `Group` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `Order`.
            append: if `True`, add to any existing expressions.
                Otherwise, this flattens all the `Order` expression into a single expression.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_child_list_builder(
            *expressions,
            instance=self,
            arg="order",
            append=append,
            copy=copy,
            prefix="ORDER BY",
            into=Order,
            dialect=dialect,
            **opts,
        )

    @property
    def ctes(self) -> t.List[CTE]:
        """Returns a list of all the CTEs attached to this query."""
        with_ = self.args.get("with")
        return with_.expressions if with_ else []

    @property
    def selects(self) -> t.List[Expression]:
        """Returns the query's projections."""
        raise NotImplementedError("Query objects must implement `selects`")

    @property
    def named_selects(self) -> t.List[str]:
        """Returns the output names of the query's projections."""
        raise NotImplementedError("Query objects must implement `named_selects`")

    def select(
        self: Q,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Q:
        """
        Append to or set the SELECT expressions.

        Example:
            >>> Select().select("x", "y").sql()
            'SELECT x, y'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
            append: if `True`, add to any existing expressions.
                Otherwise, this resets the expressions.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Query expression.
        """
        raise NotImplementedError("Query objects must implement `select`")

    def where(
        self: Q,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Q:
        """
        Append to or set the WHERE expressions.

        Examples:
            >>> Select().select("x").from_("tbl").where("x = 'a' OR x < 'b'").sql()
            "SELECT x FROM tbl WHERE x = 'a' OR x < 'b'"

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
                Multiple expressions are combined with an AND operator.
            append: if `True`, AND the new expressions to any existing expression.
                Otherwise, this resets the expression.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified expression.
        """
        return _apply_conjunction_builder(
            *[expr.this if isinstance(expr, Where) else expr for expr in expressions],
            instance=self,
            arg="where",
            append=append,
            into=Where,
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def with_(
        self: Q,
        alias: ExpOrStr,
        as_: ExpOrStr,
        recursive: t.Optional[bool] = None,
        materialized: t.Optional[bool] = None,
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        scalar: bool = False,
        **opts,
    ) -> Q:
        """
        Append to or set the common table expressions.

        Example:
            >>> Select().with_("tbl2", as_="SELECT * FROM tbl").select("x").from_("tbl2").sql()
            'WITH tbl2 AS (SELECT * FROM tbl) SELECT x FROM tbl2'

        Args:
            alias: the SQL code string to parse as the table name.
                If an `Expression` instance is passed, this is used as-is.
            as_: the SQL code string to parse as the table expression.
                If an `Expression` instance is passed, it will be used as-is.
            recursive: set the RECURSIVE part of the expression. Defaults to `False`.
            materialized: set the MATERIALIZED part of the expression.
            append: if `True`, add to any existing expressions.
                Otherwise, this resets the expressions.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            scalar: if `True`, this is a scalar common table expression.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified expression.
        """
        return _apply_cte_builder(
            self,
            alias,
            as_,
            recursive=recursive,
            materialized=materialized,
            append=append,
            dialect=dialect,
            copy=copy,
            scalar=scalar,
            **opts,
        )

    def union(
        self, *expressions: ExpOrStr, distinct: bool = True, dialect: DialectType = None, **opts
    ) -> Union:
        """
        Builds a UNION expression.

        Example:
            >>> import sqlglot
            >>> sqlglot.parse_one("SELECT * FROM foo").union("SELECT * FROM bla").sql()
            'SELECT * FROM foo UNION SELECT * FROM bla'

        Args:
            expressions: the SQL code strings.
                If `Expression` instances are passed, they will be used as-is.
            distinct: set the DISTINCT flag if and only if this is true.
            dialect: the dialect used to parse the input expression.
            opts: other options to use to parse the input expressions.

        Returns:
            The new Union expression.
        """
        return union(self, *expressions, distinct=distinct, dialect=dialect, **opts)

    def intersect(
        self, *expressions: ExpOrStr, distinct: bool = True, dialect: DialectType = None, **opts
    ) -> Intersect:
        """
        Builds an INTERSECT expression.

        Example:
            >>> import sqlglot
            >>> sqlglot.parse_one("SELECT * FROM foo").intersect("SELECT * FROM bla").sql()
            'SELECT * FROM foo INTERSECT SELECT * FROM bla'

        Args:
            expressions: the SQL code strings.
                If `Expression` instances are passed, they will be used as-is.
            distinct: set the DISTINCT flag if and only if this is true.
            dialect: the dialect used to parse the input expression.
            opts: other options to use to parse the input expressions.

        Returns:
            The new Intersect expression.
        """
        return intersect(self, *expressions, distinct=distinct, dialect=dialect, **opts)

    def except_(
        self, *expressions: ExpOrStr, distinct: bool = True, dialect: DialectType = None, **opts
    ) -> Except:
        """
        Builds an EXCEPT expression.

        Example:
            >>> import sqlglot
            >>> sqlglot.parse_one("SELECT * FROM foo").except_("SELECT * FROM bla").sql()
            'SELECT * FROM foo EXCEPT SELECT * FROM bla'

        Args:
            expressions: the SQL code strings.
                If `Expression` instance are passed, they will be used as-is.
            distinct: set the DISTINCT flag if and only if this is true.
            dialect: the dialect used to parse the input expression.
            opts: other options to use to parse the input expressions.

        Returns:
            The new Except expression.
        """
        return except_(self, *expressions, distinct=distinct, dialect=dialect, **opts)

class With(Expression):
    arg_types = {"expressions": True, "recursive": False, "search": False}

    @property
    def recursive(self) -> bool:
        return bool(self.args.get("recursive"))

class CTE(DerivedTable):
    """
    WITH sales_summary AS (
    SELECT region, SUM(sales) AS total_sales
    FROM sales
    GROUP BY region
    )
    Each CTE has exactly this and alias.
    """
    arg_types = {
        "this": True,
        "alias": True,
        "scalar": False,
        "materialized": False,
    }

class TableAlias(Expression):
    """
    columns may hold columns belonging to this table alias
    Cypher symbolic name
    Ensure no columns; ensure this is present and is always an Identifier
    """
    arg_types = {"this": False, "columns": False}

    @property
    def columns(self):
        return self.args.get("columns") or []

class Column(Condition):
    arg_types = {"this": True, "table": False, "db": False, "catalog": False, "join_mark": False}

    @property
    def table(self) -> str:
        return self.text("table")

    @property
    def db(self) -> str:
        return self.text("db")

    @property
    def catalog(self) -> str:
        return self.text("catalog")

    @property
    def output_name(self) -> str:
        return self.name

    @property
    def parts(self) -> t.List[Identifier]:
        """Return the parts of a column in order catalog, db, table, name."""
        return [
            t.cast(Identifier, self.args[part])
            for part in ("catalog", "db", "table", "this")
            if self.args.get(part)
        ]

    def to_dot(self, include_dots: bool = True) -> Dot | Identifier:
        """Converts the column into a dot expression."""
        parts = self.parts
        parent = self.parent

        if include_dots:
            while isinstance(parent, Dot):
                parts.append(parent.expression)
                parent = parent.parent

        return Dot.build(deepcopy(parts)) if len(parts) > 1 else parts[0]

class From(Expression):
    """
    Cypher MATCH
    FROM contains only Table or Subquery nodes
    Has exactly this
    After qualify, each Table should have exactly this and alias
    """
    @property
    def name(self) -> str:
        return self.this.name

    @property
    def alias_or_name(self) -> str:
        return self.this.alias_or_name

class Having(Expression):
    """
    Cypher WHERE
    Ensure exactly this is present
    """
    pass

class Identifier(Expression):
    arg_types = {"this": True, "quoted": False, "global": False, "temporary": False}

    @property
    def quoted(self) -> bool:
        return bool(self.args.get("quoted"))

    @property
    def hashable_args(self) -> t.Any:
        return (self.this, self.quoted)

    @property
    def output_name(self) -> str:
        return self.name

class Group(Expression):
    """
    groupby
    this: column name
    table: table name
    Ensure exactly expressions is present
    expressions may contain{<class 'sqlglot.expressions.Div'>, <class 'sqlglot.expressions.Paren'>, <class 'sqlglot.expressions.Substring'>, <class 'sqlglot.expressions.Sub'>, <class 'sqlglot.expressions.Literal'>, <class 'sqlglot.expressions.Column'>, <class 'sqlglot.expressions.TimeToStr'>, <class 'sqlglot.expressions.EQ'>}
    Use WITH in Cypher
    """
    arg_types = {
        "expressions": False,
        "grouping_sets": False,
        "cube": False,
        "rollup": False,
        "totals": False,
        "all": False,
    }

class Limit(Expression):
    """
    Ensure exactly expression is present and it is a Literal
    """
    arg_types = {
        "this": False,
        "expression": True,
        "offset": False,
        "limit_options": False,
        "expressions": False,
    }

class Literal(Condition):
    arg_types = {"this": True, "is_string": True}

    @property
    def hashable_args(self) -> t.Any:
        return (self.this, self.args.get("is_string"))

    @classmethod
    def number(cls, number) -> Literal:
        return cls(this=str(number), is_string=False)

    @classmethod
    def string(cls, string) -> Literal:
        return cls(this=str(string), is_string=True)

    @property
    def output_name(self) -> str:
        return self.name

    def to_py(self) -> int | str | Decimal:
        if self.is_number:
            try:
                return int(self.this)
            except ValueError:
                return Decimal(self.this)
        return self.this

class Join(Expression):
    """
    Cypher relationship edge (if any)
        INNER JOIN maps to MATCH
        JOIN is treated as INNER JOIN
        LEFT JOIN maps to OPTIONAL MATCH
            SELECT *
            FROM users u
            LEFT OUTER JOIN posts p ON u.id = p.user_id; becomes
            MATCH (u:User)
            OPTIONAL MATCH (u)-[:WROTE]->(p:Post)
            RETURN u, p;

    Otherwise only WHERE is available
    At least one of side and kind is empty
    side must be LEFT or RIGHT
    kind must be INNER
    When side is RIGHT, ON must be EQ
    """
    arg_types = {
        "this": True,
        "on": False,
        "side": False,
        "kind": False,
        "using": False,
        "method": False,
        "global": False,
        "hint": False,
        "match_condition": False,
        "expressions": False,
        "pivots": False,
    }

    @property
    def method(self) -> str:
        return self.text("method").upper()

    @property
    def kind(self) -> str:
        return self.text("kind").upper()

    @property
    def side(self) -> str:
        return self.text("side").upper()

    @property
    def hint(self) -> str:
        return self.text("hint").upper()

    @property
    def alias_or_name(self) -> str:
        return self.this.alias_or_name

    @property
    def is_semi_or_anti_join(self) -> bool:
        return self.kind in ("SEMI", "ANTI")

    def on(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Join:
        """
        Append to or set the ON expressions.

        Example:
            >>> import sqlglot
            >>> sqlglot.parse_one("JOIN x", into=Join).on("y = 1").sql()
            'JOIN x ON y = 1'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
                Multiple expressions are combined with an AND operator.
            append: if `True`, AND the new expressions to any existing expression.
                Otherwise, this resets the expression.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Join expression.
        """
        join = _apply_conjunction_builder(
            *expressions,
            instance=self,
            arg="on",
            append=append,
            dialect=dialect,
            copy=copy,
            **opts,
        )

        if join.kind == "CROSS":
            join.set("kind", None)

        return join

    def using(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Join:
        """
        Append to or set the USING expressions.

        Example:
            >>> import sqlglot
            >>> sqlglot.parse_one("JOIN x", into=Join).using("foo", "bla").sql()
            'JOIN x USING (foo, bla)'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
            append: if `True`, concatenate the new expressions to the existing "using" list.
                Otherwise, this resets the expression.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Join expression.
        """
        join = _apply_list_builder(
            *expressions,
            instance=self,
            arg="using",
            append=append,
            dialect=dialect,
            copy=copy,
            **opts,
        )

        if join.kind == "CROSS":
            join.set("kind", None)

        return join

class Offset(Expression):
    """
    Ensure exactly expression is present; each expression is a Literal
    Cypher SKIP (offset)
    """
    arg_types = {"this": False, "expression": True, "expressions": False}

class Order(Expression):
    """
    Has exactly expressions; all entries are Ordered
    """
    arg_types = {"this": False, "expressions": True, "siblings": False}

class Ordered(Expression):
    """
    The expression being ordered, plus ASC/DESC and null ordering rules
    Ensure no with_fill; this has no Alias; if desc is set, nulls_first must differ
    """
    arg_types = {"this": True, "desc": False, "nulls_first": True, "with_fill": False}

    @property
    def name(self) -> str:
        return self.this.name

class GraphPattern(Expression):
    arg_types = {
        "this": True,
        "reverse":True
    }

    @property
    def pattern(self):
        return self.args['this']

    @property
    def reverse(self):
        return self.args['reverse']

class Relation(Expression):
    arg_types = {
        "this": True,
        "alias": True,
        "src": False,
        "dst": False,
    }

class Table(Expression):
    """
    After qualify, should have exactly this and alias; alias should be TableAlias
    """
    arg_types = {
        "this": False,
        "alias": False,
        "db": False,
        "catalog": False,
        "laterals": False,
        "joins": False,
        "pivots": False,
        "hints": False,
        "system_time": False,
        "version": False,
        "format": False,
        "pattern": False,
        "ordinality": False,
        "when": False,
        "only": False,
        "partition": False,
        "changes": False,
        "rows_from": False,
        "sample": False,
    }

    @property
    def name(self) -> str:
        if not self.this or isinstance(self.this, Func):
            return ""
        return self.this.name

    @property
    def db(self) -> str:
        return self.text("db")

    @property
    def catalog(self) -> str:
        return self.text("catalog")

    @property
    def selects(self) -> t.List[Expression]:
        return []

    @property
    def named_selects(self) -> t.List[str]:
        return []

    @property
    def parts(self) -> t.List[Expression]:
        """Return the parts of a table in order catalog, db, table."""
        parts: t.List[Expression] = []

        for arg in ("catalog", "db", "this"):
            part = self.args.get(arg)

            if isinstance(part, Dot):
                parts.extend(part.flatten())
            elif isinstance(part, Expression):
                parts.append(part)

        return parts

    def to_column(self, copy: bool = True) -> Expression:
        parts = self.parts
        last_part = parts[-1]

        if isinstance(last_part, Identifier):
            col: Expression = column(*reversed(parts[0:4]), fields=parts[4:], copy=copy)
        else:

            col = last_part

        alias = self.args.get("alias")
        if alias:
            col = alias_(col, alias.this, copy=copy)

        return col

class SetOperation(Query):
    """
    Set operations; this class is not used directly, only subclasses
    """
    arg_types = {
        "with": False,
        "this": True,
        "expression": True,
        "distinct": False,
        "by_name": False,
        "side": False,
        "kind": False,
        "on": False,
        **QUERY_MODIFIERS,
    }

    def select(
        self: S,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> S:
        this = maybe_copy(self, copy)
        this.this.unnest().select(*expressions, append=append, dialect=dialect, copy=False, **opts)
        this.expression.unnest().select(
            *expressions, append=append, dialect=dialect, copy=False, **opts
        )
        return this

    @property
    def named_selects(self) -> t.List[str]:
        return self.this.unnest().named_selects

    @property
    def is_star(self) -> bool:
        return self.this.is_star or self.expression.is_star

    @property
    def selects(self) -> t.List[Expression]:
        return self.this.unnest().selects

    @property
    def left(self) -> Query:
        return self.this

    @property
    def right(self) -> Query:
        return self.expression

    @property
    def kind(self) -> str:
        return self.text("kind").upper()

    @property
    def side(self) -> str:
        return self.text("side").upper()

class Union(SetOperation):
    """
    At most this, expression, distinct, order, limit
    Ensure distinct is not None
    this and expression must be Select or Union
    """
    """
    In Cypher UNION, RETURN aliases must match
    """
    pass

class Except(SetOperation):
    """
    At most distinct, this, expression
    distinct is always True
    this and expression are always Select or Union
    """
    pass

class Intersect(SetOperation):
    """
    this and expression are both Select
    """
    pass

class Var(Expression):
    """
    Variance
    Must be computed manually; subquery fallback if needed?
    """
    pass

class Select(Query):
    """
    Cypher RETURN
    At most {'from', 'where', 'joins', 'distinct', 'with', 'expressions', 'group', 'order', 'having', 'limit', 'offset'}
    Each distinct has no arguments; deduplicates the full column tuple
    with must be a With node
    expressions may be Alias, Star, or Subquery
        Star can be expanded away via qualify
        Subquery.this is always SELECT (verified by EDA); that SELECT must be scalar (1 row, 1 column) per SQL grammar
        Subquery has exactly this and alias
    where must be WHERE nodes

    """
    arg_types = {
        "with": False,
        "kind": False,
        "expressions": False,
        "hint": False,
        "distinct": False,
        "into": False,
        "from": False,
        "operation_modifiers": False,
        **QUERY_MODIFIERS,
    }

    def generate_match(self,all_edges:dict,tablealias2table:dict,all_JoinTables:list,all_alias:list,allTables:list) -> t.List[t.List[Table | Relation | From]]:
        """
            Return self.args['match'], the MATCH pattern
        """

        From_stat = self.args.get("from",None)

        Join_stats = self.args.get("joins",None)

        if From_stat is None and Join_stats is None:
            return

        if From_stat is not None and Join_stats is None:
            self.args['match'] = [self.from2Match_no_Join(all_edges,tablealias2table,From_stat,all_JoinTables,all_alias,allTables)]
            return

        graph_pattern, optional_graph_pattern, match_where,optional_match_where = self.Join2Match(all_edges,tablealias2table,Join_stats,all_alias)

        graph_pattern = self.merge_graph_pattern(graph_pattern)

        optional_graph_pattern = self.merge_graph_pattern(optional_graph_pattern)

        if len(graph_pattern) > 0:
            self.args.setdefault('match',[]).extend(graph_pattern)
        if len(match_where) > 0:
            self.args['match_where'] = match_where
        if len(optional_graph_pattern) > 0:
            self.args.setdefault('optional_match',[]).extend(optional_graph_pattern)
        if len(optional_match_where) > 0:
            self.args['optional_match_where'] = optional_match_where

    def from2Match_no_Join(self,all_edges:dict,tablealias2table:dict,From_stat:From,all_JoinTables:list,all_alias:list[Identifier],allTables:list):
        """
            Convert a FROM clause without JOIN into MATCH
            The return value is equivalent to graph_pattern
        """

        from_table = From_stat.args['this']
        if isinstance(from_table,Subquery):
            return graphpattern([copy.deepcopy(from_table)],False)
        elif isinstance(from_table,Table):
            if from_table.name.lower() in [tmp.lower() for tmp in all_JoinTables]:
                for (src,dst),edges in all_edges['jt'].items():
                    for edge in edges:
                        if edge['related_jt'].lower() == from_table.name.lower():

                            rel = relation(this=edge['edge_label'].lower(),alias=from_table.args['alias'])

                            alias_num = 0
                            while(True):
                                if f"{src}_{alias_num}" not in all_alias and f"{dst}_{alias_num+1}" not in all_alias:
                                    break
                                else:
                                    alias_num += 1

                            return graphpattern([rel],False)
            elif from_table.name.lower() in [tmp.lower() for tmp in allTables]:
                return graphpattern([copy.deepcopy(from_table)],False)
            else:
                return graphpattern([],False)
        else:
            raise NotImplementedError("From must be Table or Subquery.")

    def Join2Match(self,all_edges:dict,tablealias2table:dict,Join_stats:list,all_alias:list[Identifier]) :
        """
        Convert JOIN clauses into MATCH
        Return graph_pattern, optional_graph_pattern, match_where
        """
        graph_pattern = []
        optional_graph_pattern = []
        match_where = []
        optional_match_where = []

        for Join_stat in Join_stats:
            Join_condi = Join_stat.args.get("on",None)
            has_side = Join_stat.args.get('side') is not None

            if Join_condi is not None:

                if isinstance(Join_condi,EQ):
                    if isinstance(Join_condi.args.get('this',None),Column) and isinstance(Join_condi.args.get('expression',None),Column):

                        is_found, new_pattern = self.Join_On_twocols2match(all_edges,tablealias2table,Join_condi,all_alias)

                        left_table, right_table = Join_condi.left.args['table'], Join_condi.right.args['table']
                        FROM_table = self.args.get('from',None).this
                        if FROM_table not in [left_table,right_table] and left_table==right_table:

                            new_pattern.append(GraphPattern(this=[FROM_table],reverse=False))

                        if not has_side:
                            appendOrExtend(graph_pattern,new_pattern)
                            match_where.append(Join_condi)

                        else:

                            actual_right_table = Join_stat.args['this'].alias_or_name
                            if right_table.name != actual_right_table:
                                left_table, right_table = right_table, left_table

                            assert right_table.name == actual_right_table

                            must_reserve_all_table = tablealias2table[left_table] if Join_stat.args['side']=="LEFT" else tablealias2table[right_table]
                            can_null_table = tablealias2table[right_table] if Join_stat.args['side']=="LEFT" else tablealias2table[left_table]
                            if is_found:
                                optional_graph_pattern.append(new_pattern)
                                optional_match_where.append(Join_condi)
                            else:
                                optional_graph_pattern.append(graphpattern([can_null_table],False))
                                optional_match_where.append(Join_condi)

                            graph_pattern.append(graphpattern([must_reserve_all_table],False))

                    elif isinstance(Join_condi.args.get('this'),Lower) and isinstance(Join_condi.args['this'].args.get('this'),Column):
                        is_found, new_pattern = self.Join_On_twocols2match(all_edges,tablealias2table,Join_condi,all_alias)

                        appendOrExtend(graph_pattern,new_pattern)
                        match_where.append(Join_condi)
                    elif isinstance(Join_condi.args.get('this'),EQ) and isinstance(Join_condi.args.get('expression'),Column):

                        tmp_where = Boolean()
                        tmp_where.args['this'] = False
                        match_where.append(tmp_where)
                    else:
                        graph_pattern.append(graphpattern([Join_stat.args.get('this')],False))
                        match_where.append(Join_condi)

                elif isinstance(Join_condi,NEQ):

                    if len(graph_pattern) == 0:
                        FROM_table = self.args.get('from',None)
                        if FROM_table is not None and FROM_table.args.get('this') is not None:
                            from_table = FROM_table.args.get('this')
                            graph_pattern.append(graphpattern([from_table],False))
                    graph_pattern.append(graphpattern([Join_stat.args.get('this')],False))
                    match_where.append(Join_condi)

                elif isinstance(Join_condi,Column):
                    """
                        Equivalent to the column being non-zero
                    """
                    graph_pattern.append(graphpattern([Join_stat.args.get('this')],False))
                    tmp_where = Where()
                    neq = NEQ()
                    neq.args['this'] = Join_condi
                    neq.args['expression'] = Literal.number(0)
                    tmp_where.args['this'] = neq
                    match_where.append(tmp_where)
                elif isinstance(Join_condi,And):
                    flattened_Join_condis = Join_condi.flatten_binary(And)
                    twocols_EQs = [flattened_Join_condi for flattened_Join_condi in flattened_Join_condis if flattened_Join_condi.is_twocol_EQ()]
                    EQs_with_same_src_and_dst = self.merge_twocols_EQ_with_same_src_and_dst(twocols_EQs)

                    for src_dst_tuple, EQs in EQs_with_same_src_and_dst.items():
                        is_found, new_pattern = self.Join_On_multi_twocols2match(all_edges,tablealias2table,EQs,src_dst_tuple,all_alias)

                        if isinstance(new_pattern,GraphPattern) and new_pattern not in graph_pattern:
                            graph_pattern.append(new_pattern)
                        elif isinstance(new_pattern,list):
                            for new_ in new_pattern:
                                if new_ not in graph_pattern:
                                    graph_pattern.append(new_)

                    match_where.append(Join_condi)
                elif isinstance(Join_condi,Or):

                    is_found, pattern1 = self.Join_On_twocols2match(all_edges,tablealias2table,Join_condi.left,all_alias)
                    is_found, pattern2 = self.Join_On_twocols2match(all_edges,tablealias2table,Join_condi.right,all_alias)

                    tmp_or = Graph_Or()
                    tmp_or.args['this'], tmp_or.args['expression'] = pattern1, pattern2
                    graph_pattern.append(tmp_or)
                    match_where.append(Join_condi)

            else:

                if len(graph_pattern) == 0:
                    FROM_table = self.args.get('from',None)
                    if FROM_table is not None and FROM_table.args.get('this') is not None:
                        from_table = FROM_table.args.get('this')

                        if isinstance(from_table, Table):
                            found_jt = False
                            if 'jt' in all_edges:
                                for (src,dst), edges in all_edges['jt'].items():
                                    for edge in edges:
                                        if check_lower_eq(from_table.name, edge.get('related_jt')):

                                            rel = relation(this=edge['edge_label'].lower(),alias=from_table.args['alias'])
                                            graph_pattern.append(graphpattern([rel],False))
                                            found_jt = True
                                            break
                                    if found_jt:
                                        break
                            if not found_jt:

                                graph_pattern.append(graphpattern([from_table],False))
                        else:

                            graph_pattern.append(graphpattern([from_table],False))

                joined_table = Join_stat.args.get('this')
                if joined_table is not None:

                    if isinstance(joined_table, Table):
                        found_jt = False
                        if 'jt' in all_edges:
                            for (src,dst), edges in all_edges['jt'].items():
                                for edge in edges:
                                    if check_lower_eq(joined_table.name, edge.get('related_jt')):

                                        rel = relation(this=edge['edge_label'].lower(),alias=joined_table.args['alias'])
                                        graph_pattern.append(graphpattern([rel],False))
                                        found_jt = True
                                        break
                                if found_jt:
                                    break
                        if not found_jt:

                            graph_pattern.append(graphpattern([joined_table],False))
                    else:

                        graph_pattern.append(graphpattern([joined_table],False))

        return graph_pattern,optional_graph_pattern,match_where, optional_match_where

    def Join_On_twocols2match(self,all_edges:dict,tablealias2table:dict,Join_condi:EQ,all_alias:list[Identifier]):
        """
        In JOIN ON, convert two Column equality to MATCH, trying both column orders
        """
        flag,pattern = self.Join_On_twocols2match_inorder(all_edges,tablealias2table,Join_condi,False,all_alias)

        if flag:
            return flag, pattern
        flag , pattern = self.Join_On_twocols2match_inorder(all_edges,tablealias2table,Join_condi,True,all_alias)
        if flag:
            return flag, pattern

        return self.Join_On_twocols2match_with_single_jt(all_edges,tablealias2table,Join_condi)

    def Join_On_twocols2match_with_single_jt(self,all_edges:dict,tablealias2table:dict,Join_condi:EQ):

        src_in_gql, dst_in_gql, src_col_in_gql, dst_col_in_gql, src_tbl_in_gql, dst_tbl_in_gql =        self.Parse_EQ_in_Join_on(Join_condi,tablealias2table,reverse_order_in_condi=False)

        tmp_tbls = []
        return_flag = False
        for tmp_tbl in [src_tbl_in_gql, dst_tbl_in_gql]:
            found_edge = False
            for single_source_edges in all_edges.values():
                for (src,dst), edges in single_source_edges.items():
                    for edge in edges:
                        if check_lower_eq(tmp_tbl.name,edge.get('related_jt')):

                            rel = relation(this=edge['edge_label'].lower(),alias=tmp_tbl.args['alias'])
                            tmp_tbls.append(graphpattern([rel]))
                            return_flag = True
                            found_edge = True
                            break
                    if found_edge:
                        break
                if found_edge:
                    break
            if not found_edge:

                tmp_tbls.append(graphpattern([tmp_tbl]))

        if return_flag:

            return True, tmp_tbls

        return False, tmp_tbls

    def Join_On_twocols2match_inorder(self,all_edges:dict,tablealias2table:dict,Join_condi:EQ,reverse_order_in_condi:bool=False,all_alias:list[Identifier]=None):
        """
        In JOIN ON, convert two Column equality to MATCH for a single column order
        """
        src_in_gql, dst_in_gql, src_col_in_gql, dst_col_in_gql, src_tbl_in_gql, dst_tbl_in_gql =        self.Parse_EQ_in_Join_on(Join_condi,tablealias2table,reverse_order_in_condi)

        src_col_in_gql,dst_col_in_gql = [src_col_in_gql],[dst_col_in_gql]

        return self.find_edge(all_edges,tablealias2table,src_tbl_in_gql,dst_tbl_in_gql,src_col_in_gql,dst_col_in_gql,all_alias)

    def Join_On_multi_twocols2match(self,all_edges:dict,tablealias2table:dict,Join_condis:EQ,src_and_dst:tuple[str],all_alias:list[Identifier]):
        """
        In JOIN ON, convert multi-column equality to MATCH, trying both orders
        """
        flag,pattern = self.Join_On_multi_twocols2match_inorder(all_edges,tablealias2table,Join_condis,src_and_dst,all_alias)
        if flag:
            return flag, pattern
        flag , pattern = self.Join_On_multi_twocols2match_inorder(all_edges,tablealias2table,Join_condis,src_and_dst[::-1],all_alias)
        if flag:
            return flag, pattern
        return self.Join_On_multi_twocols2match_with_single_jt(all_edges,tablealias2table,Join_condis)
    def Join_On_multi_twocols2match_inorder(self,all_edges:dict,tablealias2table:dict,Join_condis:t.List[EQ],restrict_order:tuple[str],all_alias:list[Identifier]):
        """
            Multi-filter-column variant of Join_On_twocols2match_inorder for AND in ON; single order only
            Order is fixed by restrict_order (src: str, dst: str)
        """
        all_src_col_in_gql = set()
        all_dst_col_in_gql = set()
        for Join_condi in Join_condis:
            _,_,src_col_in_gql, dst_col_in_gql, src_tbl_in_gql, dst_tbl_in_gql =                self.Parse_EQ_in_Join_on(Join_condi,tablealias2table,restrict_order=restrict_order)
            all_src_col_in_gql.add(src_col_in_gql)
            all_dst_col_in_gql.add(dst_col_in_gql)
        all_src_col_in_gql, all_dst_col_in_gql = list(all_src_col_in_gql), list(all_dst_col_in_gql)

        return self.find_edge(all_edges,tablealias2table,src_tbl_in_gql,dst_tbl_in_gql,all_src_col_in_gql,all_dst_col_in_gql,all_alias)

    def Join_On_multi_twocols2match_with_single_jt(self,all_edges:dict,tablealias2table:dict,Join_condis:t.List[EQ]):
        """
            No edge but jointable exists; multi-column variant of Join_On_twocols2match_with_single_jt
        """

        return self.Join_On_twocols2match_with_single_jt(all_edges,tablealias2table,Join_condis[0])

    def find_edge(self,all_edges:dict,tablealias2table:dict,src_tbl_in_gql:Table|Subquery,dst_tbl_in_gql:Table|Subquery,src_col_in_gql:list[str],dst_col_in_gql:list[str],all_alias:list[Identifier]):
        """
        Find a matching edge
        """
        for single_source_edges in all_edges.values():
            for (src,dst), edges in single_source_edges.items():
                for edge in edges:

                    src_col, dst_col = edge['source_filter_columns'], edge['target_filter_columns']
                    if edge.get('related_jt'):

                        src_col_align, dst_col_align = edge['source_filter_columns_align'], edge['target_filter_columns_align']

                    if check_lower_eq(src,src_tbl_in_gql.name) and check_lower_eq(dst,dst_tbl_in_gql.name):

                        if check_lower_eq(src_col,src_col_in_gql) and check_lower_eq(dst_col,dst_col_in_gql):
                            edge_label_name = edge['edge_label'].lower()
                            rel_alias = create_an_alias(edge_label_name,all_alias)
                            rel = relation(this=edge_label_name,alias=rel_alias)
                            tablealias2table[rel_alias] = rel

                            return True, graphpattern([src_tbl_in_gql,rel,dst_tbl_in_gql],False)
                    elif check_lower_eq(src,src_tbl_in_gql.name):

                        if check_lower_eq(dst_tbl_in_gql.name,edge.get('related_jt')):

                            if check_lower_eq(src_col_align,src_col_in_gql):
                                rel = relation(this=edge['edge_label'].lower(),alias=dst_tbl_in_gql.args['alias'])

                                return True,graphpattern([src_tbl_in_gql,rel],False)
                    elif check_lower_eq(dst,dst_tbl_in_gql.name):
                        if check_lower_eq(src_tbl_in_gql.name,edge.get('related_jt')):
                            if check_lower_eq(dst_col_align,dst_col_in_gql):
                                rel = relation(this=edge['edge_label'].lower(),alias=src_tbl_in_gql.args['alias'])
                                return True,graphpattern([rel,dst_tbl_in_gql],False)

        return False, graphpattern([src_tbl_in_gql,dst_tbl_in_gql],False)

    def Parse_EQ_in_Join_on(self,Join_condi:EQ,tablealias2table:dict,reverse_order_in_condi:bool=False,restrict_order:t.Optional[tuple[str]]=None):
        """
            Parse EQ in JOIN ON; ON must be EQ
        """

        if isinstance(Join_condi,list):
            return 0,0,0,0,0,0

        src_in_gql,dst_in_gql = Join_condi.args['this'], Join_condi.args['expression']

        if reverse_order_in_condi:
            src_in_gql,dst_in_gql = dst_in_gql,src_in_gql

        if restrict_order and src_in_gql.table.lower() != restrict_order[0].lower():
            src_in_gql,dst_in_gql = dst_in_gql,src_in_gql
            assert src_in_gql.table.lower() == restrict_order[0].lower()

        if isinstance(src_in_gql,Lower):
            src_in_gql = src_in_gql.args['this']
        if isinstance(dst_in_gql,Lower):
            dst_in_gql = dst_in_gql.args['this']

        src_col_in_gql, dst_col_in_gql = src_in_gql.name, dst_in_gql.name
        src_tbl_in_gql, dst_tbl_in_gql = tablealias2table[src_in_gql.args.get("table")], tablealias2table[dst_in_gql.args.get("table")]
        return src_in_gql, dst_in_gql, src_col_in_gql, dst_col_in_gql, src_tbl_in_gql, dst_tbl_in_gql

    def merge_twocols_EQ_with_same_src_and_dst(self,EQ_list:t.List[EQ]):
        """
        Merge EQ conditions with the same source and destination
        res: key :(src:str,dst:str) value:[EQ1,EQ2,...]
        """
        res = {}
        for single_eq in EQ_list:
            src_dst_key = tuple(sorted((single_eq.left.table,single_eq.right.table)))
            res.setdefault(src_dst_key,[]).append(single_eq)

        return res

    def merge_graph_pattern(self,graph_pattern:list[GraphPattern])->list[GraphPattern]:

        all_nodes = [single_pattern for single_pattern in graph_pattern if GraphPattern_Utils.is_all_node(single_pattern)]
        all_paths = [single_pattern for single_pattern in graph_pattern if GraphPattern_Utils.is_a_path(single_pattern)]

        all_nodes = list(set(all_nodes))
        all_paths = GraphPattern_Utils.merge_all_paths(all_paths)

        nodes_in_paths = sum([path.this for path in all_paths],[])
        for i,node in enumerate(all_nodes):
            all_nodes[i].args['this'] = [node_ for node_ in node.this if node_ not in nodes_in_paths]

        single_relation = []
        not_single_relation_alias = []
        for path in all_paths:
            if len(path.this) == 1 and isinstance(path.this[0],Relation):
                single_relation.append(path)
            else:
                not_single_relation_alias.extend([tmp.alias for tmp in path.this if isinstance(tmp,Relation)])

        all_paths = [path for path in all_paths if not (path in single_relation and path.this[0].alias in not_single_relation_alias)]

        return all_nodes + all_paths

    def from_(
        self, expression: ExpOrStr, dialect: DialectType = None, copy: bool = True, **opts
    ) -> Select:
        """
        Set the FROM expression.

        Example:
            >>> Select().from_("tbl").select("x").sql()
            'SELECT x FROM tbl'

        Args:
            expression : the SQL code strings to parse.
                If a `From` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `From`.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_builder(
            expression=expression,
            instance=self,
            arg="from",
            into=From,
            prefix="FROM",
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def group_by(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Set the GROUP BY expression.

        Example:
            >>> Select().from_("tbl").select("x", "COUNT(1)").group_by("x").sql()
            'SELECT x, COUNT(1) FROM tbl GROUP BY x'

        Args:
            *expressions: the SQL code strings to parse.
                If a `Group` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `Group`.
                If nothing is passed in then a group by is not applied to the expression
            append: if `True`, add to any existing expressions.
                Otherwise, this flattens all the `Group` expression into a single expression.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        if not expressions:
            return self if not copy else self.copy()

        return _apply_child_list_builder(
            *expressions,
            instance=self,
            arg="group",
            append=append,
            copy=copy,
            prefix="GROUP BY",
            into=Group,
            dialect=dialect,
            **opts,
        )

    def sort_by(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Set the SORT BY expression.

        Example:
            >>> Select().from_("tbl").select("x").sort_by("x DESC").sql(dialect="hive")
            'SELECT x FROM tbl SORT BY x DESC'

        Args:
            *expressions: the SQL code strings to parse.
                If a `Group` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `SORT`.
            append: if `True`, add to any existing expressions.
                Otherwise, this flattens all the `Order` expression into a single expression.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_child_list_builder(
            *expressions,
            instance=self,
            arg="sort",
            append=append,
            copy=copy,
            prefix="SORT BY",
            into=Sort,
            dialect=dialect,
            **opts,
        )

    def cluster_by(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Set the CLUSTER BY expression.

        Example:
            >>> Select().from_("tbl").select("x").cluster_by("x DESC").sql(dialect="hive")
            'SELECT x FROM tbl CLUSTER BY x DESC'

        Args:
            *expressions: the SQL code strings to parse.
                If a `Group` instance is passed, this is used as-is.
                If another `Expression` instance is passed, it will be wrapped in a `Cluster`.
            append: if `True`, add to any existing expressions.
                Otherwise, this flattens all the `Order` expression into a single expression.
            dialect: the dialect used to parse the input expression.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_child_list_builder(
            *expressions,
            instance=self,
            arg="cluster",
            append=append,
            copy=copy,
            prefix="CLUSTER BY",
            into=Cluster,
            dialect=dialect,
            **opts,
        )

    def select(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        return _apply_list_builder(
            *expressions,
            instance=self,
            arg="expressions",
            append=append,
            dialect=dialect,
            into=Expression,
            copy=copy,
            **opts,
        )

    def lateral(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Append to or set the LATERAL expressions.

        Example:
            >>> Select().select("x").lateral("OUTER explode(y) tbl2 AS z").from_("tbl").sql()
            'SELECT x FROM tbl LATERAL VIEW OUTER EXPLODE(y) tbl2 AS z'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
            append: if `True`, add to any existing expressions.
                Otherwise, this resets the expressions.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_list_builder(
            *expressions,
            instance=self,
            arg="laterals",
            append=append,
            into=Lateral,
            prefix="LATERAL VIEW",
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def join(
        self,
        expression: ExpOrStr,
        on: t.Optional[ExpOrStr] = None,
        using: t.Optional[ExpOrStr | t.Collection[ExpOrStr]] = None,
        append: bool = True,
        join_type: t.Optional[str] = None,
        join_alias: t.Optional[Identifier | str] = None,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Append to or set the JOIN expressions.

        Example:
            >>> Select().select("*").from_("tbl").join("tbl2", on="tbl1.y = tbl2.y").sql()
            'SELECT * FROM tbl JOIN tbl2 ON tbl1.y = tbl2.y'

            >>> Select().select("1").from_("a").join("b", using=["x", "y", "z"]).sql()
            'SELECT 1 FROM a JOIN b USING (x, y, z)'

            Use `join_type` to change the type of join:

            >>> Select().select("*").from_("tbl").join("tbl2", on="tbl1.y = tbl2.y", join_type="left outer").sql()
            'SELECT * FROM tbl LEFT OUTER JOIN tbl2 ON tbl1.y = tbl2.y'

        Args:
            expression: the SQL code string to parse.
                If an `Expression` instance is passed, it will be used as-is.
            on: optionally specify the join "on" criteria as a SQL string.
                If an `Expression` instance is passed, it will be used as-is.
            using: optionally specify the join "using" criteria as a SQL string.
                If an `Expression` instance is passed, it will be used as-is.
            append: if `True`, add to any existing expressions.
                Otherwise, this resets the expressions.
            join_type: if set, alter the parsed join type.
            join_alias: an optional alias for the joined source.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            Select: the modified expression.
        """
        parse_args: t.Dict[str, t.Any] = {"dialect": dialect, **opts}

        try:
            expression = maybe_parse(expression, into=Join, prefix="JOIN", **parse_args)
        except ParseError:
            expression = maybe_parse(expression, into=(Join, Expression), **parse_args)

        join = expression if isinstance(expression, Join) else Join(this=expression)

        if isinstance(join.this, Select):
            join.this.replace(join.this.subquery())

        if join_type:
            method: t.Optional[Token]
            side: t.Optional[Token]
            kind: t.Optional[Token]

            method, side, kind = maybe_parse(join_type, into="JOIN_TYPE", **parse_args)

            if method:
                join.set("method", method.text)
            if side:
                join.set("side", side.text)
            if kind:
                join.set("kind", kind.text)

        if on:
            on = and_(*ensure_list(on), dialect=dialect, copy=copy, **opts)
            join.set("on", on)

        if using:
            join = _apply_list_builder(
                *ensure_list(using),
                instance=join,
                arg="using",
                append=append,
                copy=copy,
                into=Identifier,
                **opts,
            )

        if join_alias:
            join.set("this", alias_(join.this, join_alias, table=True))

        return _apply_list_builder(
            join,
            instance=self,
            arg="joins",
            append=append,
            copy=copy,
            **opts,
        )

    def having(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        """
        Append to or set the HAVING expressions.

        Example:
            >>> Select().select("x", "COUNT(y)").from_("tbl").group_by("x").having("COUNT(y) > 3").sql()
            'SELECT x, COUNT(y) FROM tbl GROUP BY x HAVING COUNT(y) > 3'

        Args:
            *expressions: the SQL code strings to parse.
                If an `Expression` instance is passed, it will be used as-is.
                Multiple expressions are combined with an AND operator.
            append: if `True`, AND the new expressions to any existing expression.
                Otherwise, this resets the expression.
            dialect: the dialect used to parse the input expressions.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input expressions.

        Returns:
            The modified Select expression.
        """
        return _apply_conjunction_builder(
            *expressions,
            instance=self,
            arg="having",
            append=append,
            into=Having,
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def window(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        return _apply_list_builder(
            *expressions,
            instance=self,
            arg="windows",
            append=append,
            into=Window,
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def qualify(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Select:
        return _apply_conjunction_builder(
            *expressions,
            instance=self,
            arg="qualify",
            append=append,
            into=Qualify,
            dialect=dialect,
            copy=copy,
            **opts,
        )

    def distinct(
        self, *ons: t.Optional[ExpOrStr], distinct: bool = True, copy: bool = True
    ) -> Select:
        """
        Set the OFFSET expression.

        Example:
            >>> Select().from_("tbl").select("x").distinct().sql()
            'SELECT DISTINCT x FROM tbl'

        Args:
            ons: the expressions to distinct on
            distinct: whether the Select should be distinct
            copy: if `False`, modify this expression instance in-place.

        Returns:
            Select: the modified expression.
        """
        instance = maybe_copy(self, copy)
        on = Tuple(expressions=[maybe_parse(on, copy=copy) for on in ons if on]) if ons else None
        instance.set("distinct", Distinct(on=on) if distinct else None)
        return instance

    def ctas(
        self,
        table: ExpOrStr,
        properties: t.Optional[t.Dict] = None,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Create:
        """
        Convert this expression to a CREATE TABLE AS statement.

        Example:
            >>> Select().select("*").from_("tbl").ctas("x").sql()
            'CREATE TABLE x AS SELECT * FROM tbl'

        Args:
            table: the SQL code string to parse as the table name.
                If another `Expression` instance is passed, it will be used as-is.
            properties: an optional mapping of table properties
            dialect: the dialect used to parse the input table.
            copy: if `False`, modify this expression instance in-place.
            opts: other options to use to parse the input table.

        Returns:
            The new Create expression.
        """
        instance = maybe_copy(self, copy)
        table_expression = maybe_parse(table, into=Table, dialect=dialect, **opts)

        properties_expression = None
        if properties:
            properties_expression = Properties.from_dict(properties)

        return Create(
            this=table_expression,
            kind="TABLE",
            expression=instance,
            properties=properties_expression,
        )

    def lock(self, update: bool = True, copy: bool = True) -> Select:
        """
        Set the locking read mode for this expression.

        Examples:
            >>> Select().select("x").from_("tbl").where("x = 'a'").lock().sql("mysql")
            "SELECT x FROM tbl WHERE x = 'a' FOR UPDATE"

            >>> Select().select("x").from_("tbl").where("x = 'a'").lock(update=False).sql("mysql")
            "SELECT x FROM tbl WHERE x = 'a' FOR SHARE"

        Args:
            update: if `True`, the locking type will be `FOR UPDATE`, else it will be `FOR SHARE`.
            copy: if `False`, modify this expression instance in-place.

        Returns:
            The modified expression.
        """
        inst = maybe_copy(self, copy)
        inst.set("locks", [Lock(update=update)])

        return inst

    def hint(self, *hints: ExpOrStr, dialect: DialectType = None, copy: bool = True) -> Select:
        """
        Set hints for this expression.

        Examples:
            >>> Select().select("x").from_("tbl").hint("BROADCAST(y)").sql(dialect="spark")
            'SELECT /*+ BROADCAST(y) */ x FROM tbl'

        Args:
            hints: The SQL code strings to parse as the hints.
                If an `Expression` instance is passed, it will be used as-is.
            dialect: The dialect used to parse the hints.
            copy: If `False`, modify this expression instance in-place.

        Returns:
            The modified expression.
        """
        inst = maybe_copy(self, copy)
        inst.set(
            "hint", Hint(expressions=[maybe_parse(h, copy=copy, dialect=dialect) for h in hints])
        )

        return inst

    @property
    def named_selects(self) -> t.List[str]:
        return [e.output_name for e in self.expressions if e.alias_or_name]

    @property
    def is_star(self) -> bool:
        return any(expression.is_star for expression in self.expressions)

    @property
    def selects(self) -> t.List[Expression]:
        return self.expressions

UNWRAPPED_QUERIES = (Select, SetOperation)

class Subquery(DerivedTable, Query):
    """
    Subquery
    Unlike CTE, apparently not preceded by WITH?
    Nested Subquery nodes are allowed

    this must be Select, Union, Intersect, or Except
        When this is Select and parent is not From/Join, expressions length is 1 (Star unlikely; handle later if seen)

    alias is always TableAlias
    If alias is present, parent must not be Alias

    Implemented in Cypher via CALL
    At most this and alias
    """
    arg_types = {
        "this": True,
        "alias": False,
        "with": False,
        **QUERY_MODIFIERS,
    }

    def unnest(self):
        """Returns the first non subquery."""
        expression = self
        while isinstance(expression, Subquery):
            expression = expression.this
        return expression

    def unwrap(self) -> Subquery:
        expression = self
        while expression.same_parent and expression.is_wrapper:
            expression = t.cast(Subquery, expression.parent)
        return expression

    def select(
        self,
        *expressions: t.Optional[ExpOrStr],
        append: bool = True,
        dialect: DialectType = None,
        copy: bool = True,
        **opts,
    ) -> Subquery:
        this = maybe_copy(self, copy)
        this.unnest().select(*expressions, append=append, dialect=dialect, copy=False, **opts)
        return this

    @property
    def is_wrapper(self) -> bool:
        """
        Whether this Subquery acts as a simple wrapper around another expression.

        SELECT * FROM (((SELECT * FROM t)))
                      ^
                      This corresponds to a "wrapper" Subquery node
        """
        return all(v is None for k, v in self.args.items() if k != "this")

    @property
    def is_star(self) -> bool:
        return self.this.is_star

    @property
    def output_name(self) -> str:
        return self.alias

class Window(Condition):
    """
    No direct Cypher equivalent; needs collect and other complex ops
    over is always OVER; not meaningful here
    Any of ('order', 'over', 'this'), ('order', 'over', 'partition_by', 'this'), ('over', 'partition_by', 'this') may appear
    When this is Anonymous with this=='RANK', order must be present
    """
    arg_types = {
        "this": True,
        "partition_by": False,
        "order": False,
        "spec": False,
        "alias": False,
        "over": False,
        "first": False,
    }

class Where(Expression):
    """
    Ensure exactly this is present
    this may only be one of the following types
    {<class 'sqlglot.expressions.Like'>, <class 'sqlglot.expressions.Between'>, <class 'sqlglot.expressions.Is'>,
      <class 'sqlglot.expressions.Exists'>, <class 'sqlglot.expressions.GTE'>, <class 'sqlglot.expressions.Paren'>,
      <class 'sqlglot.expressions.And'>, <class 'sqlglot.expressions.LTE'>, <class 'sqlglot.expressions.In'>,
      <class 'sqlglot.expressions.NEQ'>, <class 'sqlglot.expressions.EQ'>, <class 'sqlglot.expressions.Or'>,
        <class 'sqlglot.expressions.GT'>, <class 'sqlglot.expressions.Not'>, <class 'sqlglot.expressions.LT'>}

    nl2sql_benchmark has no Tuple/Array types, so no (a,b) = (SELECT ...) style multi-value equality

    """
    pass

class Star(Expression):
    """
    Expand to all columns
    After qualify, Star is expanded automatically; schema is required for qualify
    """
    arg_types = {"except": False, "replace": False, "rename": False}

    @property
    def name(self) -> str:
        return "*"

    @property
    def output_name(self) -> str:
        return self.name

class Null(Condition):
    arg_types: t.Dict[str, t.Any] = {}

    @property
    def name(self) -> str:
        return "NULL"

    def to_py(self) -> Lit[None]:
        return None

class Boolean(Condition):
    def to_py(self) -> bool:
        return self.this

class DataTypeParam(Expression):
    arg_types = {"this": True, "expression": False}

    @property
    def name(self) -> str:
        return self.this.name

class DataType(Expression):
    """
    e.g. FLOAT

    In SQLite, REL is invalid but may appear; ignored or treated as NUMERIC
    Exactly 2 args: this and nested, or this and kind (only REL seen; likely a typo)
    If nested is present, it must be False

    """
    arg_types = {
        "this": True,
        "expressions": False,
        "nested": False,
        "values": False,
        "prefix": False,
        "kind": False,
        "nullable": False,
    }

    class Type(AutoName):
        ARRAY = auto()
        AGGREGATEFUNCTION = auto()
        SIMPLEAGGREGATEFUNCTION = auto()
        BIGDECIMAL = auto()
        BIGINT = auto()
        BIGSERIAL = auto()
        BINARY = auto()
        BIT = auto()
        BLOB = auto()
        BOOLEAN = auto()
        BPCHAR = auto()
        CHAR = auto()
        DATE = auto()
        DATE32 = auto()
        DATEMULTIRANGE = auto()
        DATERANGE = auto()
        DATETIME = auto()
        DATETIME2 = auto()
        DATETIME64 = auto()
        DECIMAL = auto()
        DECIMAL32 = auto()
        DECIMAL64 = auto()
        DECIMAL128 = auto()
        DECIMAL256 = auto()
        DOUBLE = auto()
        DYNAMIC = auto()
        ENUM = auto()
        ENUM8 = auto()
        ENUM16 = auto()
        FIXEDSTRING = auto()
        FLOAT = auto()
        GEOGRAPHY = auto()
        GEOMETRY = auto()
        POINT = auto()
        RING = auto()
        LINESTRING = auto()
        MULTILINESTRING = auto()
        POLYGON = auto()
        MULTIPOLYGON = auto()
        HLLSKETCH = auto()
        HSTORE = auto()
        IMAGE = auto()
        INET = auto()
        INT = auto()
        INT128 = auto()
        INT256 = auto()
        INT4MULTIRANGE = auto()
        INT4RANGE = auto()
        INT8MULTIRANGE = auto()
        INT8RANGE = auto()
        INTERVAL = auto()
        IPADDRESS = auto()
        IPPREFIX = auto()
        IPV4 = auto()
        IPV6 = auto()
        JSON = auto()
        JSONB = auto()
        LIST = auto()
        LONGBLOB = auto()
        LONGTEXT = auto()
        LOWCARDINALITY = auto()
        MAP = auto()
        MEDIUMBLOB = auto()
        MEDIUMINT = auto()
        MEDIUMTEXT = auto()
        MONEY = auto()
        NAME = auto()
        NCHAR = auto()
        NESTED = auto()
        NOTHING = auto()
        NULL = auto()
        NUMMULTIRANGE = auto()
        NUMRANGE = auto()
        NVARCHAR = auto()
        OBJECT = auto()
        RANGE = auto()
        ROWVERSION = auto()
        SERIAL = auto()
        SET = auto()
        SMALLDATETIME = auto()
        SMALLINT = auto()
        SMALLMONEY = auto()
        SMALLSERIAL = auto()
        STRUCT = auto()
        SUPER = auto()
        TEXT = auto()
        TINYBLOB = auto()
        TINYTEXT = auto()
        TIME = auto()
        TIMETZ = auto()
        TIMESTAMP = auto()
        TIMESTAMPNTZ = auto()
        TIMESTAMPLTZ = auto()
        TIMESTAMPTZ = auto()
        TIMESTAMP_S = auto()
        TIMESTAMP_MS = auto()
        TIMESTAMP_NS = auto()
        TINYINT = auto()
        TSMULTIRANGE = auto()
        TSRANGE = auto()
        TSTZMULTIRANGE = auto()
        TSTZRANGE = auto()
        UBIGINT = auto()
        UINT = auto()
        UINT128 = auto()
        UINT256 = auto()
        UMEDIUMINT = auto()
        UDECIMAL = auto()
        UDOUBLE = auto()
        UNION = auto()
        UNKNOWN = auto()
        USERDEFINED = "USER-DEFINED"
        USMALLINT = auto()
        UTINYINT = auto()
        UUID = auto()
        VARBINARY = auto()
        VARCHAR = auto()
        VARIANT = auto()
        VECTOR = auto()
        XML = auto()
        YEAR = auto()
        TDIGEST = auto()

    STRUCT_TYPES = {
        Type.NESTED,
        Type.OBJECT,
        Type.STRUCT,
        Type.UNION,
    }

    ARRAY_TYPES = {
        Type.ARRAY,
        Type.LIST,
    }

    NESTED_TYPES = {
        *STRUCT_TYPES,
        *ARRAY_TYPES,
        Type.MAP,
    }

    TEXT_TYPES = {
        Type.CHAR,
        Type.NCHAR,
        Type.NVARCHAR,
        Type.TEXT,
        Type.VARCHAR,
        Type.NAME,
    }

    SIGNED_INTEGER_TYPES = {
        Type.BIGINT,
        Type.INT,
        Type.INT128,
        Type.INT256,
        Type.MEDIUMINT,
        Type.SMALLINT,
        Type.TINYINT,
    }

    UNSIGNED_INTEGER_TYPES = {
        Type.UBIGINT,
        Type.UINT,
        Type.UINT128,
        Type.UINT256,
        Type.UMEDIUMINT,
        Type.USMALLINT,
        Type.UTINYINT,
    }

    INTEGER_TYPES = {
        *SIGNED_INTEGER_TYPES,
        *UNSIGNED_INTEGER_TYPES,
        Type.BIT,
    }

    FLOAT_TYPES = {
        Type.DOUBLE,
        Type.FLOAT,
    }

    REAL_TYPES = {
        *FLOAT_TYPES,
        Type.BIGDECIMAL,
        Type.DECIMAL,
        Type.DECIMAL32,
        Type.DECIMAL64,
        Type.DECIMAL128,
        Type.DECIMAL256,
        Type.MONEY,
        Type.SMALLMONEY,
        Type.UDECIMAL,
        Type.UDOUBLE,
    }

    NUMERIC_TYPES = {
        *INTEGER_TYPES,
        *REAL_TYPES,
    }

    TEMPORAL_TYPES = {
        Type.DATE,
        Type.DATE32,
        Type.DATETIME,
        Type.DATETIME2,
        Type.DATETIME64,
        Type.SMALLDATETIME,
        Type.TIME,
        Type.TIMESTAMP,
        Type.TIMESTAMPNTZ,
        Type.TIMESTAMPLTZ,
        Type.TIMESTAMPTZ,
        Type.TIMESTAMP_MS,
        Type.TIMESTAMP_NS,
        Type.TIMESTAMP_S,
        Type.TIMETZ,
    }

    def is_type(self,dtype):
        return self.this.value == dtype.value

class SubqueryPredicate(Predicate):
    """
    Only EXISTS
    """
    pass

class Binary(Condition):
    """
    Binary operators such as LT
    """
    arg_types = {"this": True, "expression": True}

    @property
    def left(self) -> Expression:
        return self.this

    @property
    def right(self) -> Expression:
        return self.expression

class Add(Binary):
    pass

class Connector(Binary):
    """
    Connectors such as And and Or
    """
    pass

class Div(Binary):

    arg_types = {"this": True, "expression": True, "typed": False, "safe": False}

COLUMN_PARTS = ("this", "table", "db", "catalog")

class Dot(Binary):
    @property
    def is_star(self) -> bool:
        return self.expression.is_star

    @property
    def name(self) -> str:
        return self.expression.name

    @property
    def output_name(self) -> str:
        return self.name

    @classmethod
    def build(self, expressions: t.Sequence[Expression]) -> Dot:
        """Build a Dot object with a sequence of expressions."""
        if len(expressions) < 2:
            raise ValueError("Dot requires >= 2 expressions.")

        return t.cast(Dot, reduce(lambda x, y: Dot(this=x, expression=y), expressions))

    @property
    def parts(self) -> t.List[Expression]:
        """Return the parts of a table / column in order catalog, db, table."""
        this, *parts = self.flatten()

        parts.reverse()

        for arg in COLUMN_PARTS:
            part = this.args.get(arg)

            if isinstance(part, Expression):
                parts.append(part)

        parts.reverse()
        return parts

DATA_TYPE = t.Union[str, Identifier, Dot, DataType, DataType.Type]

class DPipe(Binary):
    """
        || concatenates strings
    """
    arg_types = {"this": True, "expression": True, "safe": False}

class EQ(Binary, Predicate):
    def swap(self):
        self.args['this'], self.args['expression'] =        self.args['expression'], self.args['this']

class GT(Binary, Predicate):
    pass

class GTE(Binary, Predicate):
    pass

class Is(Binary, Predicate):
    """
    Ensure exactly this and expression
    expression must be NULL or an empty Literal string
    """
    pass

class Like(Binary, Predicate):
    """
    Ensure exactly this and expression

    left must be Substring or Column
    right must be Literal or Column
    (Column appears because double quotes are parsed as columns; should be Literal. SQLite may treat it as a column at runtime, but qualify fails because the column is missing.)
    Could wrap qualify in try/except and rewrite double quotes to single quotes on failure
    """
    pass

class LT(Binary, Predicate):
    """
    Ensure exactly this and expression
    """
    pass

class LTE(Binary, Predicate):
    pass

class Mul(Binary):
    pass

class NEQ(Binary, Predicate):
    """
    Not equal
    """
    pass

class Sub(Binary):
    pass

class Unary(Condition):
    pass

class Not(Unary):
    pass

class Paren(Unary):
    """
    Parentheses
    """
    @property
    def output_name(self) -> str:
        return self.this.name

class Neg(Unary):
    """
    Ensure exactly this is present
    this must be Literal
    """
    def to_py(self) -> int | Decimal:
        if self.is_number:
            return self.this.to_py() * -1
        return super().to_py()

class Alias(Expression):
    """
    Exactly this and alias; this may be a column or derived expression
    If arg count is 2, that means exactly this and alias
    Only appears in Select.expressions
    """
    arg_types = {"this": True, "alias": False}

    @property
    def output_name(self) -> str:
        return self.alias

class Between(Predicate):
    """
        Ensure exactly this is present low high
    """
    arg_types = {"this": True, "low": True, "high": True}

class Distinct(Expression):
    """
    Ensure no on
    """
    arg_types = {"expressions": False, "on": False}

class In(Predicate):
    """
    Either this+expressions or this+query
    this must be Substring or Column
    expressions is a list containing only Literal nodes
    query must be Subquery without alias
    """
    arg_types = {
        "this": True,
        "expressions": False,
        "query": False,
        "unnest": False,
        "field": False,
        "is_global": False,
    }

class TimeUnit(Expression):
    """
    Time operations
    """
    """Automatically converts unit arg into a var."""

    arg_types = {"unit": False}

    UNABBREVIATED_UNIT_NAME = {
        "D": "DAY",
        "H": "HOUR",
        "M": "MINUTE",
        "MS": "MILLISECOND",
        "NS": "NANOSECOND",
        "Q": "QUARTER",
        "S": "SECOND",
        "US": "MICROSECOND",
        "W": "WEEK",
        "Y": "YEAR",
    }

    VAR_LIKE = (Column, Literal, Var)

    def __init__(self, **args):
        unit = args.get("unit")
        if isinstance(unit, self.VAR_LIKE):
            args["unit"] = Var(
                this=(self.UNABBREVIATED_UNIT_NAME.get(unit.name) or unit.name).upper()
            )
        elif isinstance(unit, Week):
            unit.set("this", Var(this=unit.this.name.upper()))

        super().__init__(**args)

    @property
    def unit(self) -> t.Optional[Var | IntervalSpan]:
        return self.args.get("unit")

class Func(Condition):
    """
    Functions such as IF (Cypher CASE), CAST (Cypher toFloat), etc.
    """
    """
    The base class for all function expressions.

    Attributes:
        is_var_len_args (bool): if set to True the last argument defined in arg_types will be
            treated as a variable length argument and the argument's value will be stored as a list.
        _sql_names (list): the SQL name (1st item in the list) and aliases (subsequent items) for this
            function expression. These values are used to map this node to a name during parsing as
            well as to provide the function's name during SQL string generation. By default the SQL
            name is set to the expression's class name transformed to snake case.
    """

    is_var_len_args = False

    @classmethod
    def from_arg_list(cls, args):
        if cls.is_var_len_args:
            all_arg_keys = list(cls.arg_types)

            non_var_len_arg_keys = all_arg_keys[:-1] if cls.is_var_len_args else all_arg_keys
            num_non_var = len(non_var_len_arg_keys)

            args_dict = {arg_key: arg for arg, arg_key in zip(args, non_var_len_arg_keys)}
            args_dict[all_arg_keys[-1]] = args[num_non_var:]
        else:
            args_dict = {arg_key: arg for arg, arg_key in zip(args, cls.arg_types)}

        return cls(**args_dict)

    @classmethod
    def sql_names(cls):
        if cls is Func:
            raise NotImplementedError(
                "SQL name is only supported by concrete function implementations"
            )
        if "_sql_names" not in cls.__dict__:
            cls._sql_names = [camel_to_snake_case(cls.__name__)]
        return cls._sql_names

    @classmethod
    def sql_name(cls):
        return cls.sql_names()[0]

    @classmethod
    def default_parser_mappings(cls):
        return {name: cls.from_arg_list for name in cls.sql_names()}

class AggFunc(Func):
    pass

class Abs(Func):
    pass

class Anonymous(Func):
    """
    Anonymous functions
    Includes RANK, JULIANDAY, etc.
    Must have this (str); may have expressions as a list of columns
    If this=='RANK', parent must be Window
    """
    arg_types = {"this": True, "expressions": False}
    is_var_len_args = True

    @property
    def name(self) -> str:
        return self.this if isinstance(self.this, str) else self.this.name

class Avg(AggFunc):
    pass

class Case(Func):
    arg_types = {"this": False, "ifs": True, "default": False}

    def when(self, condition: ExpOrStr, then: ExpOrStr, copy: bool = True, **opts) -> Case:
        instance = maybe_copy(self, copy)
        instance.append(
            "ifs",
            If(
                this=maybe_parse(condition, copy=copy, **opts),
                true=maybe_parse(then, copy=copy, **opts),
            ),
        )
        return instance

    def else_(self, condition: ExpOrStr, copy: bool = True, **opts) -> Case:
        instance = maybe_copy(self, copy)
        instance.set("default", maybe_parse(condition, copy=copy, **opts))
        return instance

class Cast(Func):
    """
    """
    arg_types = {
        "this": True,
        "to": True,
        "format": False,
        "safe": False,
        "action": False,
        "default": False,
    }

    @property
    def name(self) -> str:
        return self.this.name

    @property
    def to(self) -> DataType:
        return self.args["to"]

    @property
    def output_name(self) -> str:
        return self.name

    def is_type(self, *dtypes: DATA_TYPE) -> bool:
        """
        Checks whether this Cast's DataType matches one of the provided data types. Nested types
        like arrays or structs will be compared using "structural equivalence" semantics, so e.g.
        array<int> != array<float>.

        Args:
            dtypes: the data types to compare this Cast's DataType to.

        Returns:
            True, if and only if there is a type in `dtypes` which is equal to this Cast's DataType.
        """
        return self.to.is_type(*dtypes)

class Count(AggFunc):
    """
    Ensure exactly these 3 arguments
    expressions is a list of length 0
    big_int must be True; default big_int=True needs no extra representation
    this must not be None
    this must not be Subquery; if this is Distinct, Distinct.this must not be Subquery
    """
    arg_types = {"this": False, "expressions": False, "big_int": False}
    is_var_len_args = True

class CurrentTimestamp(Func):
    arg_types = {"this": False, "sysdate": False}

class Week(Func):
    arg_types = {"this": True, "mode": False}

class DateDiff(Func, TimeUnit):
    _sql_names = ["DATEDIFF", "DATE_DIFF"]
    arg_types = {"this": True, "expression": True, "unit": False, "zone": False}

class Exists(Func, SubqueryPredicate):
    arg_types = {"this": True, "expression": False}

class TimestampDiff(Func, TimeUnit):
    _sql_names = ["TIMESTAMPDIFF", "TIMESTAMP_DIFF"]
    arg_types = {"this": True, "expression": True, "unit": False}

class Date(Func):
    arg_types = {"this": False, "zone": False, "expressions": False}
    is_var_len_args = True

class GroupConcat(AggFunc):
    """
    GROUP_CONCAT is a SQL aggregate that concatenates values in a group into one string, usually comma-separated.
    """
    arg_types = {"this": True, "separator": False, "on_overflow": False}

class And(Connector, Func):
    pass

class Or(Connector, Func):
    pass

class Graph_Or(Connector, Func, GraphPattern):
    pass

class If(Func):
    arg_types = {"this": True, "true": True, "false": False}
    _sql_names = ["IF", "IIF"]

class Length(Func):
    arg_types = {"this": True, "binary": False, "encoding": False}
    _sql_names = ["LENGTH", "LEN", "CHAR_LENGTH", "CHARACTER_LENGTH"]

class Lower(Func):
    _sql_names = ["LOWER", "LCASE"]

class Max(AggFunc):
    arg_types = {"this": True, "expressions": False}
    is_var_len_args = True

class Min(AggFunc):
    arg_types = {"this": True, "expressions": False}
    is_var_len_args = True

class Replace(Func):
    """
    String replacement
    """
    arg_types = {"this": True, "expression": True, "replacement": False}

class Round(Func):
    arg_types = {"this": True, "decimals": False, "truncate": False}

class RowNumber(Func):
    """
    Row number; no direct Cypher equivalent
    """
    arg_types = {"this": False}

class Substring(Func):
    """
    Must have this and start; length is optional
    this must be one of
        {<class 'sqlglot.expressions.Literal'>, <class 'sqlglot.expressions.Substring'>, <class 'sqlglot.expressions.Cast'>, <class 'sqlglot.expressions.Column'>}
    start must be one of
        {<class 'sqlglot.expressions.Add'>, <class 'sqlglot.expressions.Literal'>, <class 'sqlglot.expressions.StrPosition'>, <class 'sqlglot.expressions.Sub'>, <class 'sqlglot.expressions.Neg'>}
    length must be one of
        {<class 'sqlglot.expressions.Sub'>, <class 'sqlglot.expressions.Literal'>, <class 'sqlglot.expressions.Length'>, <class 'sqlglot.expressions.Neg'>}

    """
    _sql_names = ["SUBSTRING", "SUBSTR"]
    arg_types = {"this": True, "start": False, "length": False}

class StrPosition(Func):
    """
    Index of first occurrence of substring in string
    Ensure exactly this and substr
    this must be Column or Substring
    substr must be Literal
    """

    arg_types = {
        "this": True,
        "substr": True,
        "position": False,
        "occurrence": False,
    }

class Sum(AggFunc):
    pass

class TimeToStr(Func):
    arg_types = {"this": True, "format": True, "culture": False, "zone": False}

class Trim(Func):
    arg_types = {
        "this": True,
        "expression": False,
        "position": False,
        "collation": False,
    }

class TsOrDsToTimestamp(Func):
    pass

def _norm_arg(arg):
    return arg.lower() if type(arg) is str else arg

@t.overload
def maybe_parse(
    sql_or_expression: ExpOrStr,
    *,
    into: t.Type[E],
    dialect: DialectType = None,
    prefix: t.Optional[str] = None,
    copy: bool = False,
    **opts,
) -> E: ...

@t.overload
def maybe_parse(
    sql_or_expression: str | E,
    *,
    into: t.Optional[IntoType] = None,
    dialect: DialectType = None,
    prefix: t.Optional[str] = None,
    copy: bool = False,
    **opts,
) -> E: ...

def maybe_parse(
    sql_or_expression: ExpOrStr,
    *,
    into: t.Optional[IntoType] = None,
    dialect: DialectType = None,
    prefix: t.Optional[str] = None,
    copy: bool = False,
    **opts,
) -> Expression:
    """Gracefully handle a possible string or expression.

    Example:
        >>> maybe_parse("1")
        Literal(this=1, is_string=False)
        >>> maybe_parse(to_identifier("x"))
        Identifier(this=x, quoted=False)

    Args:
        sql_or_expression: the SQL code string or an expression
        into: the SQLGlot Expression to parse into
        dialect: the dialect used to parse the input expressions (in the case that an
            input expression is a SQL string).
        prefix: a string to prefix the sql with before it gets parsed
            (automatically includes a space)
        copy: whether to copy the expression.
        **opts: other options to use to parse the input expressions (again, in the case
            that an input expression is a SQL string).

    Returns:
        Expression: the parsed or given expression.
    """
    if isinstance(sql_or_expression, Expression):
        if copy:
            return sql_or_expression.copy()
        return sql_or_expression

    if sql_or_expression is None:
        raise ParseError("SQL cannot be None")

    import sqlglot

    sql = str(sql_or_expression)
    if prefix:
        sql = f"{prefix} {sql}"

    return sqlglot.parse_one(sql, read=dialect, into=into, **opts)

@t.overload
def maybe_copy(instance: None, copy: bool = True) -> None: ...

@t.overload
def maybe_copy(instance: E, copy: bool = True) -> E: ...

def maybe_copy(instance, copy=True):
    return instance.copy() if copy and instance else instance

def _to_s(node: t.Any, verbose: bool = False, level: int = 0, repr_str: bool = False) -> str:
    """Generate a textual representation of an Expression tree"""
    indent = "\n" + ("  " * (level + 1))
    delim = f",{indent}"

    if isinstance(node, Expression):
        args = {k: v for k, v in node.args.items() if (v is not None and v != []) or verbose}

        if (node.type or verbose) and not isinstance(node, DataType):
            args["_type"] = node.type
        if node.comments or verbose:
            args["_comments"] = node.comments

        if verbose:
            args["_id"] = id(node)

        if node.is_leaf():
            indent = ""
            delim = ", "

        repr_str = node.is_string or (isinstance(node, Identifier) and node.quoted)
        items = delim.join(
            [f"{k}={_to_s(v, verbose, level + 1, repr_str=repr_str)}" for k, v in args.items()]
        )
        return f"{node.__class__.__name__}({indent}{items})"

    if isinstance(node, list):
        items = delim.join(_to_s(i, verbose, level + 1) for i in node)
        items = f"{indent}{items}" if items else ""
        return f"[{items}]"

    if repr_str and isinstance(node, str):
        node = repr(node)

    return indent.join(textwrap.dedent(str(node).strip("\n")).splitlines())

def _is_wrong_expression(expression, into):
    return isinstance(expression, Expression) and not isinstance(expression, into)

def _apply_builder(
    expression,
    instance,
    arg,
    copy=True,
    prefix=None,
    into=None,
    dialect=None,
    into_arg="this",
    **opts,
):
    if _is_wrong_expression(expression, into):
        expression = into(**{into_arg: expression})
    instance = maybe_copy(instance, copy)
    expression = maybe_parse(
        sql_or_expression=expression,
        prefix=prefix,
        into=into,
        dialect=dialect,
        **opts,
    )
    instance.set(arg, expression)
    return instance

def _apply_child_list_builder(
    *expressions,
    instance,
    arg,
    append=True,
    copy=True,
    prefix=None,
    into=None,
    dialect=None,
    properties=None,
    **opts,
):
    instance = maybe_copy(instance, copy)
    parsed = []
    properties = {} if properties is None else properties

    for expression in expressions:
        if expression is not None:
            if _is_wrong_expression(expression, into):
                expression = into(expressions=[expression])

            expression = maybe_parse(
                expression,
                into=into,
                dialect=dialect,
                prefix=prefix,
                **opts,
            )
            for k, v in expression.args.items():
                if k == "expressions":
                    parsed.extend(v)
                else:
                    properties[k] = v

    existing = instance.args.get(arg)
    if append and existing:
        parsed = existing.expressions + parsed

    child = into(expressions=parsed)
    for k, v in properties.items():
        child.set(k, v)
    instance.set(arg, child)

    return instance

def _apply_list_builder(
    *expressions,
    instance,
    arg,
    append=True,
    copy=True,
    prefix=None,
    into=None,
    dialect=None,
    **opts,
):
    inst = maybe_copy(instance, copy)

    expressions = [
        maybe_parse(
            sql_or_expression=expression,
            into=into,
            prefix=prefix,
            dialect=dialect,
            **opts,
        )
        for expression in expressions
        if expression is not None
    ]

    existing_expressions = inst.args.get(arg)
    if append and existing_expressions:
        expressions = existing_expressions + expressions

    inst.set(arg, expressions)
    return inst

def _apply_conjunction_builder(
    *expressions,
    instance,
    arg,
    into=None,
    append=True,
    copy=True,
    dialect=None,
    **opts,
):
    expressions = [exp for exp in expressions if exp is not None and exp != ""]
    if not expressions:
        return instance

    inst = maybe_copy(instance, copy)

    existing = inst.args.get(arg)
    if append and existing is not None:
        expressions = [existing.this if into else existing] + list(expressions)

    node = and_(*expressions, dialect=dialect, copy=copy, **opts)

    inst.set(arg, into(this=node) if into else node)
    return inst

def _apply_cte_builder(
    instance: E,
    alias: ExpOrStr,
    as_: ExpOrStr,
    recursive: t.Optional[bool] = None,
    materialized: t.Optional[bool] = None,
    append: bool = True,
    dialect: DialectType = None,
    copy: bool = True,
    scalar: bool = False,
    **opts,
) -> E:
    alias_expression = maybe_parse(alias, dialect=dialect, into=TableAlias, **opts)
    as_expression = maybe_parse(as_, dialect=dialect, copy=copy, **opts)
    if scalar and not isinstance(as_expression, Subquery):

        as_expression = Subquery(this=as_expression)
    cte = CTE(this=as_expression, alias=alias_expression, materialized=materialized, scalar=scalar)
    return _apply_child_list_builder(
        cte,
        instance=instance,
        arg="with",
        append=append,
        copy=copy,
        into=With,
        properties={"recursive": recursive or False},
    )

def _combine(
    expressions: t.Sequence[t.Optional[ExpOrStr]],
    operator: t.Type[Connector],
    dialect: DialectType = None,
    copy: bool = True,
    wrap: bool = True,
    **opts,
) -> Expression:
    conditions = [
        condition(expression, dialect=dialect, copy=copy, **opts)
        for expression in expressions
        if expression is not None
    ]

    this, *rest = conditions
    if rest and wrap:
        this = _wrap(this, Connector)
    for expression in rest:
        this = operator(this=this, expression=_wrap(expression, Connector) if wrap else expression)

    return this

@t.overload
def _wrap(expression: None, kind: t.Type[Expression]) -> None: ...

@t.overload
def _wrap(expression: E, kind: t.Type[Expression]) -> E | Paren: ...

def _wrap(expression: t.Optional[E], kind: t.Type[Expression]) -> t.Optional[E] | Paren:
    return Paren(this=expression) if isinstance(expression, kind) else expression

def _apply_set_operation(
    *expressions: ExpOrStr,
    set_operation: t.Type[S],
    distinct: bool = True,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> S:
    return reduce(
        lambda x, y: set_operation(this=x, expression=y, distinct=distinct, **opts),
        (maybe_parse(e, dialect=dialect, copy=copy, **opts) for e in expressions),
    )

def union(
    *expressions: ExpOrStr,
    distinct: bool = True,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> Union:
    """
    Initializes a syntax tree for the `UNION` operation.

    Example:
        >>> union("SELECT * FROM foo", "SELECT * FROM bla").sql()
        'SELECT * FROM foo UNION SELECT * FROM bla'

    Args:
        expressions: the SQL code strings, corresponding to the `UNION`'s operands.
            If `Expression` instances are passed, they will be used as-is.
        distinct: set the DISTINCT flag if and only if this is true.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy the expression.
        opts: other options to use to parse the input expressions.

    Returns:
        The new Union instance.
    """
    assert len(expressions) >= 2, "At least two expressions are required by `union`."
    return _apply_set_operation(
        *expressions, set_operation=Union, distinct=distinct, dialect=dialect, copy=copy, **opts
    )

def intersect(
    *expressions: ExpOrStr,
    distinct: bool = True,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> Intersect:
    """
    Initializes a syntax tree for the `INTERSECT` operation.

    Example:
        >>> intersect("SELECT * FROM foo", "SELECT * FROM bla").sql()
        'SELECT * FROM foo INTERSECT SELECT * FROM bla'

    Args:
        expressions: the SQL code strings, corresponding to the `INTERSECT`'s operands.
            If `Expression` instances are passed, they will be used as-is.
        distinct: set the DISTINCT flag if and only if this is true.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy the expression.
        opts: other options to use to parse the input expressions.

    Returns:
        The new Intersect instance.
    """
    assert len(expressions) >= 2, "At least two expressions are required by `intersect`."
    return _apply_set_operation(
        *expressions, set_operation=Intersect, distinct=distinct, dialect=dialect, copy=copy, **opts
    )

def except_(
    *expressions: ExpOrStr,
    distinct: bool = True,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> Except:
    """
    Initializes a syntax tree for the `EXCEPT` operation.

    Example:
        >>> except_("SELECT * FROM foo", "SELECT * FROM bla").sql()
        'SELECT * FROM foo EXCEPT SELECT * FROM bla'

    Args:
        expressions: the SQL code strings, corresponding to the `EXCEPT`'s operands.
            If `Expression` instances are passed, they will be used as-is.
        distinct: set the DISTINCT flag if and only if this is true.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy the expression.
        opts: other options to use to parse the input expressions.

    Returns:
        The new Except instance.
    """
    assert len(expressions) >= 2, "At least two expressions are required by `except_`."
    return _apply_set_operation(
        *expressions, set_operation=Except, distinct=distinct, dialect=dialect, copy=copy, **opts
    )

def select(*expressions: ExpOrStr, dialect: DialectType = None, **opts) -> Select:
    """
    Initializes a syntax tree from one or multiple SELECT expressions.

    Example:
        >>> select("col1", "col2").from_("tbl").sql()
        'SELECT col1, col2 FROM tbl'

    Args:
        *expressions: the SQL code string to parse as the expressions of a
            SELECT statement. If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expressions (in the case that an
            input expression is a SQL string).
        **opts: other options to use to parse the input expressions (again, in the case
            that an input expression is a SQL string).

    Returns:
        Select: the syntax tree for the SELECT statement.
    """
    return Select().select(*expressions, dialect=dialect, **opts)

def from_(expression: ExpOrStr, dialect: DialectType = None, **opts) -> Select:
    """
    Initializes a syntax tree from a FROM expression.

    Example:
        >>> from_("tbl").select("col1", "col2").sql()
        'SELECT col1, col2 FROM tbl'

    Args:
        *expression: the SQL code string to parse as the FROM expressions of a
            SELECT statement. If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression (in the case that the
            input expression is a SQL string).
        **opts: other options to use to parse the input expressions (again, in the case
            that the input expression is a SQL string).

    Returns:
        Select: the syntax tree for the SELECT statement.
    """
    return Select().from_(expression, dialect=dialect, **opts)

def update(
    table: str | Table,
    properties: t.Optional[dict] = None,
    where: t.Optional[ExpOrStr] = None,
    from_: t.Optional[ExpOrStr] = None,
    with_: t.Optional[t.Dict[str, ExpOrStr]] = None,
    dialect: DialectType = None,
    **opts,
) -> Update:
    """
    Creates an update statement.

    Example:
        >>> update("my_table", {"x": 1, "y": "2", "z": None}, from_="baz_cte", where="baz_cte.id > 1 and my_table.id = baz_cte.id", with_={"baz_cte": "SELECT id FROM foo"}).sql()
        "WITH baz_cte AS (SELECT id FROM foo) UPDATE my_table SET x = 1, y = '2', z = NULL FROM baz_cte WHERE baz_cte.id > 1 AND my_table.id = baz_cte.id"

    Args:
        properties: dictionary of properties to SET which are
            auto converted to sql objects eg None -> NULL
        where: sql conditional parsed into a WHERE statement
        from_: sql statement parsed into a FROM statement
        with_: dictionary of CTE aliases / select statements to include in a WITH clause.
        dialect: the dialect used to parse the input expressions.
        **opts: other options to use to parse the input expressions.

    Returns:
        Update: the syntax tree for the UPDATE statement.
    """
    update_expr = Update(this=maybe_parse(table, into=Table, dialect=dialect))
    if properties:
        update_expr.set(
            "expressions",
            [
                EQ(this=maybe_parse(k, dialect=dialect, **opts), expression=convert(v))
                for k, v in properties.items()
            ],
        )
    if from_:
        update_expr.set(
            "from",
            maybe_parse(from_, into=From, dialect=dialect, prefix="FROM", **opts),
        )
    if isinstance(where, Condition):
        where = Where(this=where)
    if where:
        update_expr.set(
            "where",
            maybe_parse(where, into=Where, dialect=dialect, prefix="WHERE", **opts),
        )
    if with_:
        cte_list = [
            alias_(CTE(this=maybe_parse(qry, dialect=dialect, **opts)), alias, table=True)
            for alias, qry in with_.items()
        ]
        update_expr.set(
            "with",
            With(expressions=cte_list),
        )
    return update_expr

def delete(
    table: ExpOrStr,
    where: t.Optional[ExpOrStr] = None,
    returning: t.Optional[ExpOrStr] = None,
    dialect: DialectType = None,
    **opts,
) -> Delete:
    """
    Builds a delete statement.

    Example:
        >>> delete("my_table", where="id > 1").sql()
        'DELETE FROM my_table WHERE id > 1'

    Args:
        where: sql conditional parsed into a WHERE statement
        returning: sql conditional parsed into a RETURNING statement
        dialect: the dialect used to parse the input expressions.
        **opts: other options to use to parse the input expressions.

    Returns:
        Delete: the syntax tree for the DELETE statement.
    """
    delete_expr = Delete().delete(table, dialect=dialect, copy=False, **opts)
    if where:
        delete_expr = delete_expr.where(where, dialect=dialect, copy=False, **opts)
    if returning:
        delete_expr = delete_expr.returning(returning, dialect=dialect, copy=False, **opts)
    return delete_expr

def insert(
    expression: ExpOrStr,
    into: ExpOrStr,
    columns: t.Optional[t.Sequence[str | Identifier]] = None,
    overwrite: t.Optional[bool] = None,
    returning: t.Optional[ExpOrStr] = None,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> Insert:
    """
    Builds an INSERT statement.

    Example:
        >>> insert("VALUES (1, 2, 3)", "tbl").sql()
        'INSERT INTO tbl VALUES (1, 2, 3)'

    Args:
        expression: the sql string or expression of the INSERT statement
        into: the tbl to insert data to.
        columns: optionally the table's column names.
        overwrite: whether to INSERT OVERWRITE or not.
        returning: sql conditional parsed into a RETURNING statement
        dialect: the dialect used to parse the input expressions.
        copy: whether to copy the expression.
        **opts: other options to use to parse the input expressions.

    Returns:
        Insert: the syntax tree for the INSERT statement.
    """
    expr = maybe_parse(expression, dialect=dialect, copy=copy, **opts)
    this: Table | Schema = maybe_parse(into, into=Table, dialect=dialect, copy=copy, **opts)

    if columns:
        this = Schema(this=this, expressions=[to_identifier(c, copy=copy) for c in columns])

    insert = Insert(this=this, expression=expr, overwrite=overwrite)

    if returning:
        insert = insert.returning(returning, dialect=dialect, copy=False, **opts)

    return insert

def merge(
    *when_exprs: ExpOrStr,
    into: ExpOrStr,
    using: ExpOrStr,
    on: ExpOrStr,
    returning: t.Optional[ExpOrStr] = None,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
) -> Merge:
    """
    Builds a MERGE statement.

    Example:
        >>> merge("WHEN MATCHED THEN UPDATE SET col1 = source_table.col1",
        ...       "WHEN NOT MATCHED THEN INSERT (col1) VALUES (source_table.col1)",
        ...       into="my_table",
        ...       using="source_table",
        ...       on="my_table.id = source_table.id").sql()
        'MERGE INTO my_table USING source_table ON my_table.id = source_table.id WHEN MATCHED THEN UPDATE SET col1 = source_table.col1 WHEN NOT MATCHED THEN INSERT (col1) VALUES (source_table.col1)'

    Args:
        *when_exprs: The WHEN clauses specifying actions for matched and unmatched rows.
        into: The target table to merge data into.
        using: The source table to merge data from.
        on: The join condition for the merge.
        returning: The columns to return from the merge.
        dialect: The dialect used to parse the input expressions.
        copy: Whether to copy the expression.
        **opts: Other options to use to parse the input expressions.

    Returns:
        Merge: The syntax tree for the MERGE statement.
    """
    expressions: t.List[Expression] = []
    for when_expr in when_exprs:
        expression = maybe_parse(when_expr, dialect=dialect, copy=copy, into=Whens, **opts)
        expressions.extend([expression] if isinstance(expression, When) else expression.expressions)

    merge = Merge(
        this=maybe_parse(into, dialect=dialect, copy=copy, **opts),
        using=maybe_parse(using, dialect=dialect, copy=copy, **opts),
        on=maybe_parse(on, dialect=dialect, copy=copy, **opts),
        whens=Whens(expressions=expressions),
    )
    if returning:
        merge = merge.returning(returning, dialect=dialect, copy=False, **opts)

    return merge

def condition(
    expression: ExpOrStr, dialect: DialectType = None, copy: bool = True, **opts
) -> Condition:
    """
    Initialize a logical condition expression.

    Example:
        >>> condition("x=1").sql()
        'x = 1'

        This is helpful for composing larger logical syntax trees:
        >>> where = condition("x=1")
        >>> where = where.and_("y=1")
        >>> Select().from_("tbl").select("*").where(where).sql()
        'SELECT * FROM tbl WHERE x = 1 AND y = 1'

    Args:
        *expression: the SQL code string to parse.
            If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression (in the case that the
            input expression is a SQL string).
        copy: Whether to copy `expression` (only applies to expressions).
        **opts: other options to use to parse the input expressions (again, in the case
            that the input expression is a SQL string).

    Returns:
        The new Condition instance
    """
    return maybe_parse(
        expression,
        into=Condition,
        dialect=dialect,
        copy=copy,
        **opts,
    )

def and_(
    *expressions: t.Optional[ExpOrStr],
    dialect: DialectType = None,
    copy: bool = True,
    wrap: bool = True,
    **opts,
) -> Condition:
    """
    Combine multiple conditions with an AND logical operator.

    Example:
        >>> and_("x=1", and_("y=1", "z=1")).sql()
        'x = 1 AND (y = 1 AND z = 1)'

    Args:
        *expressions: the SQL code strings to parse.
            If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy `expressions` (only applies to Expressions).
        wrap: whether to wrap the operands in `Paren`s. This is true by default to avoid
            precedence issues, but can be turned off when the produced AST is too deep and
            causes recursion-related issues.
        **opts: other options to use to parse the input expressions.

    Returns:
        The new condition
    """
    return t.cast(Condition, _combine(expressions, And, dialect, copy=copy, wrap=wrap, **opts))

def or_(
    *expressions: t.Optional[ExpOrStr],
    dialect: DialectType = None,
    copy: bool = True,
    wrap: bool = True,
    **opts,
) -> Condition:
    """
    Combine multiple conditions with an OR logical operator.

    Example:
        >>> or_("x=1", or_("y=1", "z=1")).sql()
        'x = 1 OR (y = 1 OR z = 1)'

    Args:
        *expressions: the SQL code strings to parse.
            If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy `expressions` (only applies to Expressions).
        wrap: whether to wrap the operands in `Paren`s. This is true by default to avoid
            precedence issues, but can be turned off when the produced AST is too deep and
            causes recursion-related issues.
        **opts: other options to use to parse the input expressions.

    Returns:
        The new condition
    """
    return t.cast(Condition, _combine(expressions, Or, dialect, copy=copy, wrap=wrap, **opts))

def xor(
    *expressions: t.Optional[ExpOrStr],
    dialect: DialectType = None,
    copy: bool = True,
    wrap: bool = True,
    **opts,
) -> Condition:
    """
    Combine multiple conditions with an XOR logical operator.

    Example:
        >>> xor("x=1", xor("y=1", "z=1")).sql()
        'x = 1 XOR (y = 1 XOR z = 1)'

    Args:
        *expressions: the SQL code strings to parse.
            If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy `expressions` (only applies to Expressions).
        wrap: whether to wrap the operands in `Paren`s. This is true by default to avoid
            precedence issues, but can be turned off when the produced AST is too deep and
            causes recursion-related issues.
        **opts: other options to use to parse the input expressions.

    Returns:
        The new condition
    """
    return t.cast(Condition, _combine(expressions, Xor, dialect, copy=copy, wrap=wrap, **opts))

def not_(expression: ExpOrStr, dialect: DialectType = None, copy: bool = True, **opts) -> Not:
    """
    Wrap a condition with a NOT operator.

    Example:
        >>> not_("this_suit='black'").sql()
        "NOT this_suit = 'black'"

    Args:
        expression: the SQL code string to parse.
            If an Expression instance is passed, this is used as-is.
        dialect: the dialect used to parse the input expression.
        copy: whether to copy the expression or not.
        **opts: other options to use to parse the input expressions.

    Returns:
        The new condition.
    """
    this = condition(
        expression,
        dialect=dialect,
        copy=copy,
        **opts,
    )
    return Not(this=_wrap(this, Connector))

def paren(expression: ExpOrStr, copy: bool = True) -> Paren:
    """
    Wrap an expression in parentheses.

    Example:
        >>> paren("5 + 3").sql()
        '(5 + 3)'

    Args:
        expression: the SQL code string to parse.
            If an Expression instance is passed, this is used as-is.
        copy: whether to copy the expression or not.

    Returns:
        The wrapped expression.
    """
    return Paren(this=maybe_parse(expression, copy=copy))

SAFE_IDENTIFIER_RE: t.Pattern[str] = re.compile(r"^[_a-zA-Z][\w]*$")

@t.overload
def to_identifier(name: None, quoted: t.Optional[bool] = None, copy: bool = True) -> None: ...

@t.overload
def to_identifier(
    name: str | Identifier, quoted: t.Optional[bool] = None, copy: bool = True
) -> Identifier: ...

def to_identifier(name, quoted=None, copy=True):
    """Builds an identifier.

    Args:
        name: The name to turn into an identifier.
        quoted: Whether to force quote the identifier.
        copy: Whether to copy name if it's an Identifier.

    Returns:
        The identifier ast node.
    """

    if name is None:
        return None

    if isinstance(name, Identifier):
        identifier = maybe_copy(name, copy)
    elif isinstance(name, str):
        identifier = Identifier(
            this=name,
            quoted=not SAFE_IDENTIFIER_RE.match(name) if quoted is None else quoted,
        )
    else:
        raise ValueError(f"Name needs to be a string or an Identifier, got: {name.__class__}")
    return identifier

def parse_identifier(name: str | Identifier, dialect: DialectType = None) -> Identifier:
    """
    Parses a given string into an identifier.

    Args:
        name: The name to parse into an identifier.
        dialect: The dialect to parse against.

    Returns:
        The identifier ast node.
    """
    try:
        expression = maybe_parse(name, dialect=dialect, into=Identifier)
    except (ParseError, TokenError):
        expression = to_identifier(name)

    return expression

INTERVAL_STRING_RE = re.compile(r"\s*(-?[0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)\s*")

def to_interval(interval: str | Literal) -> Interval:
    """Builds an interval expression from a string like '1 day' or '5 months'."""
    if isinstance(interval, Literal):
        if not interval.is_string:
            raise ValueError("Invalid interval string.")

        interval = interval.this

    interval = maybe_parse(f"INTERVAL {interval}")
    assert isinstance(interval, Interval)
    return interval

def to_table(
    sql_path: str | Table, dialect: DialectType = None, copy: bool = True, **kwargs
) -> Table:
    """
    Create a table expression from a `[catalog].[schema].[table]` sql path. Catalog and schema are optional.
    If a table is passed in then that table is returned.

    Args:
        sql_path: a `[catalog].[schema].[table]` string.
        dialect: the source dialect according to which the table name will be parsed.
        copy: Whether to copy a table if it is passed in.
        kwargs: the kwargs to instantiate the resulting `Table` expression with.

    Returns:
        A table expression.
    """
    if isinstance(sql_path, Table):
        return maybe_copy(sql_path, copy=copy)

    try:
        table = maybe_parse(sql_path, into=Table, dialect=dialect)
    except ParseError:
        catalog, db, this = split_num_words(sql_path, ".", 3)

        if not this:
            raise

        table = table_(this, db=db, catalog=catalog)

    for k, v in kwargs.items():
        table.set(k, v)

    return table

def to_column(
    sql_path: str | Column,
    quoted: t.Optional[bool] = None,
    dialect: DialectType = None,
    copy: bool = True,
    **kwargs,
) -> Column:
    """
    Create a column from a `[table].[column]` sql path. Table is optional.
    If a column is passed in then that column is returned.

    Args:
        sql_path: a `[table].[column]` string.
        quoted: Whether or not to force quote identifiers.
        dialect: the source dialect according to which the column name will be parsed.
        copy: Whether to copy a column if it is passed in.
        kwargs: the kwargs to instantiate the resulting `Column` expression with.

    Returns:
        A column expression.
    """
    if isinstance(sql_path, Column):
        return maybe_copy(sql_path, copy=copy)

    try:
        col = maybe_parse(sql_path, into=Column, dialect=dialect)
    except ParseError:
        return column(*reversed(sql_path.split(".")), quoted=quoted, **kwargs)

    for k, v in kwargs.items():
        col.set(k, v)

    if quoted:
        for i in col.find_all(Identifier):
            i.set("quoted", True)

    return col

def alias_(
    expression: ExpOrStr,
    alias: t.Optional[str | Identifier],
    table: bool | t.Sequence[str | Identifier] = False,
    quoted: t.Optional[bool] = None,
    dialect: DialectType = None,
    copy: bool = True,
    **opts,
):
    """Create an Alias expression.

    Example:
        >>> alias_('foo', 'bar').sql()
        'foo AS bar'

        >>> alias_('(select 1, 2)', 'bar', table=['a', 'b']).sql()
        '(SELECT 1, 2) AS bar(a, b)'

    Args:
        expression: the SQL code strings to parse.
            If an Expression instance is passed, this is used as-is.
        alias: the alias name to use. If the name has
            special characters it is quoted.
        table: Whether to create a table alias, can also be a list of columns.
        quoted: whether to quote the alias
        dialect: the dialect used to parse the input expression.
        copy: Whether to copy the expression.
        **opts: other options to use to parse the input expressions.

    Returns:
        Alias: the aliased expression
    """
    exp = maybe_parse(expression, dialect=dialect, copy=copy, **opts)
    alias = to_identifier(alias, quoted=quoted)

    if table:
        table_alias = TableAlias(this=alias)
        exp.set("alias", table_alias)

        if not isinstance(table, bool):
            for column in table:
                table_alias.append("columns", to_identifier(column, quoted=quoted))

        return exp

    if "alias" in exp.arg_types and not isinstance(exp, Window):
        exp.set("alias", alias)
        return exp
    return Alias(this=exp, alias=alias)

def subquery(
    expression: ExpOrStr,
    alias: t.Optional[Identifier | str] = None,
    dialect: DialectType = None,
    **opts,
) -> Select:
    """
    Build a subquery expression that's selected from.

    Example:
        >>> subquery('select x from tbl', 'bar').select('x').sql()
        'SELECT x FROM (SELECT x FROM tbl) AS bar'

    Args:
        expression: the SQL code strings to parse.
            If an Expression instance is passed, this is used as-is.
        alias: the alias name to use.
        dialect: the dialect used to parse the input expression.
        **opts: other options to use to parse the input expressions.

    Returns:
        A new Select instance with the subquery expression included.
    """

    expression = maybe_parse(expression, dialect=dialect, **opts).subquery(alias, **opts)
    return Select().from_(expression, dialect=dialect, **opts)

@t.overload
def column(
    col: str | Identifier,
    table: t.Optional[str | Identifier] = None,
    db: t.Optional[str | Identifier] = None,
    catalog: t.Optional[str | Identifier] = None,
    *,
    fields: t.Collection[t.Union[str, Identifier]],
    quoted: t.Optional[bool] = None,
    copy: bool = True,
) -> Dot:
    pass

@t.overload
def column(
    col: str | Identifier | Star,
    table: t.Optional[str | Identifier] = None,
    db: t.Optional[str | Identifier] = None,
    catalog: t.Optional[str | Identifier] = None,
    *,
    fields: Lit[None] = None,
    quoted: t.Optional[bool] = None,
    copy: bool = True,
) -> Column:
    pass

def column(
    col,
    table=None,
    db=None,
    catalog=None,
    *,
    fields=None,
    quoted=None,
    copy=True,
):
    """
    Build a Column.

    Args:
        col: Column name.
        table: Table name.
        db: Database name.
        catalog: Catalog name.
        fields: Additional fields using dots.
        quoted: Whether to force quotes on the column's identifiers.
        copy: Whether to copy identifiers if passed in.

    Returns:
        The new Column instance.
    """
    if not isinstance(col, Star):
        col = to_identifier(col, quoted=quoted, copy=copy)

    this = Column(
        this=col,
        table=to_identifier(table, quoted=quoted, copy=copy),
        db=to_identifier(db, quoted=quoted, copy=copy),
        catalog=to_identifier(catalog, quoted=quoted, copy=copy),
    )

    if fields:
        this = Dot.build(
            (this, *(to_identifier(field, quoted=quoted, copy=copy) for field in fields))
        )
    return this

def cast(
    expression: ExpOrStr, to: DATA_TYPE, copy: bool = True, dialect: DialectType = None, **opts
) -> Cast:
    """Cast an expression to a data type.

    Example:
        >>> cast('x + 1', 'int').sql()
        'CAST(x + 1 AS INT)'

    Args:
        expression: The expression to cast.
        to: The datatype to cast to.
        copy: Whether to copy the supplied expressions.
        dialect: The target dialect. This is used to prevent a re-cast in the following scenario:
            - The expression to be cast is already a exp.Cast expression
            - The existing cast is to a type that is logically equivalent to new type

            For example, if :expression='CAST(x as DATETIME)' and :to=Type.TIMESTAMP,
            but in the target dialect DATETIME is mapped to TIMESTAMP, then we will NOT return `CAST(x (as DATETIME) as TIMESTAMP)`
            and instead just return the original expression `CAST(x as DATETIME)`.

            This is to prevent it being output as a double cast `CAST(x (as TIMESTAMP) as TIMESTAMP)` once the DATETIME -> TIMESTAMP
            mapping is applied in the target dialect generator.

    Returns:
        The new Cast instance.
    """
    expr = maybe_parse(expression, copy=copy, dialect=dialect, **opts)
    data_type = DataType.build(to, copy=copy, dialect=dialect, **opts)

    if isinstance(expr, Cast):
        from sqlglot.dialects.dialect import Dialect

        target_dialect = Dialect.get_or_raise(dialect)
        type_mapping = target_dialect.generator_class.TYPE_MAPPING

        existing_cast_type: DataType.Type = expr.to.this
        new_cast_type: DataType.Type = data_type.this
        types_are_equivalent = type_mapping.get(
            existing_cast_type, existing_cast_type.value
        ) == type_mapping.get(new_cast_type, new_cast_type.value)

        if expr.is_type(data_type) or types_are_equivalent:
            return expr

    expr = Cast(this=expr, to=data_type)
    expr.type = data_type

    return expr

def table_(
    table: Identifier | str,
    db: t.Optional[Identifier | str] = None,
    catalog: t.Optional[Identifier | str] = None,
    quoted: t.Optional[bool] = None,
    alias: t.Optional[Identifier | str] = None,
) -> Table:
    """Build a Table.

    Args:
        table: Table name.
        db: Database name.
        catalog: Catalog name.
        quote: Whether to force quotes on the table's identifiers.
        alias: Table's alias.

    Returns:
        The new Table instance.
    """
    return Table(
        this=to_identifier(table, quoted=quoted) if table else None,
        db=to_identifier(db, quoted=quoted) if db else None,
        catalog=to_identifier(catalog, quoted=quoted) if catalog else None,
        alias=TableAlias(this=to_identifier(alias)) if alias else None,
    )

def values(
    values: t.Iterable[t.Tuple[t.Any, ...]],
    alias: t.Optional[str] = None,
    columns: t.Optional[t.Iterable[str] | t.Dict[str, DataType]] = None,
) -> Values:
    """Build VALUES statement.

    Example:
        >>> values([(1, '2')]).sql()
        "VALUES (1, '2')"

    Args:
        values: values statements that will be converted to SQL
        alias: optional alias
        columns: Optional list of ordered column names or ordered dictionary of column names to types.
         If either are provided then an alias is also required.

    Returns:
        Values: the Values expression object
    """
    if columns and not alias:
        raise ValueError("Alias is required when providing columns")

    return Values(
        expressions=[convert(tup) for tup in values],
        alias=(
            TableAlias(this=to_identifier(alias), columns=[to_identifier(x) for x in columns])
            if columns
            else (TableAlias(this=to_identifier(alias)) if alias else None)
        ),
    )

def var(name: t.Optional[ExpOrStr]) -> Var:
    """Build a SQL variable.

    Example:
        >>> repr(var('x'))
        'Var(this=x)'

        >>> repr(var(column('x', table='y')))
        'Var(this=x)'

    Args:
        name: The name of the var or an expression who's name will become the var.

    Returns:
        The new variable node.
    """
    if not name:
        raise ValueError("Cannot convert empty name into var.")

    if isinstance(name, Expression):
        name = name.name
    return Var(this=name)

def rename_table(
    old_name: str | Table,
    new_name: str | Table,
    dialect: DialectType = None,
) -> Alter:
    """Build ALTER TABLE... RENAME... expression

    Args:
        old_name: The old name of the table
        new_name: The new name of the table
        dialect: The dialect to parse the table.

    Returns:
        Alter table expression
    """
    old_table = to_table(old_name, dialect=dialect)
    new_table = to_table(new_name, dialect=dialect)
    return Alter(
        this=old_table,
        kind="TABLE",
        actions=[
            AlterRename(this=new_table),
        ],
    )

def rename_column(
    table_name: str | Table,
    old_column_name: str | Column,
    new_column_name: str | Column,
    exists: t.Optional[bool] = None,
    dialect: DialectType = None,
) -> Alter:
    """Build ALTER TABLE... RENAME COLUMN... expression

    Args:
        table_name: Name of the table
        old_column: The old name of the column
        new_column: The new name of the column
        exists: Whether to add the `IF EXISTS` clause
        dialect: The dialect to parse the table/column.

    Returns:
        Alter table expression
    """
    table = to_table(table_name, dialect=dialect)
    old_column = to_column(old_column_name, dialect=dialect)
    new_column = to_column(new_column_name, dialect=dialect)
    return Alter(
        this=table,
        kind="TABLE",
        actions=[
            RenameColumn(this=old_column, to=new_column, exists=exists),
        ],
    )

def convert(value: t.Any, copy: bool = False) -> Expression:
    """Convert a python value into an expression object.

    Raises an error if a conversion is not possible.

    Args:
        value: A python object.
        copy: Whether to copy `value` (only applies to Expressions and collections).

    Returns:
        The equivalent expression object.
    """
    if isinstance(value, Expression):
        return maybe_copy(value, copy)
    if isinstance(value, str):
        return Literal.string(value)
    if isinstance(value, bool):
        return Boolean(this=value)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return null()
    if isinstance(value, numbers.Number):
        return Literal.number(value)
    if isinstance(value, bytes):
        return HexString(this=value.hex())
    if isinstance(value, datetime.datetime):
        datetime_literal = Literal.string(value.isoformat(sep=" "))

        tz = None
        if value.tzinfo:

            tz = Literal.string(str(value.tzinfo))

        return TimeStrToTime(this=datetime_literal, zone=tz)
    if isinstance(value, datetime.date):
        date_literal = Literal.string(value.strftime("%Y-%m-%d"))
        return DateStrToDate(this=date_literal)
    if isinstance(value, tuple):
        if hasattr(value, "_fields"):
            return Struct(
                expressions=[
                    PropertyEQ(
                        this=to_identifier(k), expression=convert(getattr(value, k), copy=copy)
                    )
                    for k in value._fields
                ]
            )
        return Tuple(expressions=[convert(v, copy=copy) for v in value])
    if isinstance(value, list):
        return Array(expressions=[convert(v, copy=copy) for v in value])
    if isinstance(value, dict):
        return Map(
            keys=Array(expressions=[convert(k, copy=copy) for k in value]),
            values=Array(expressions=[convert(v, copy=copy) for v in value.values()]),
        )
    if hasattr(value, "__dict__"):
        return Struct(
            expressions=[
                PropertyEQ(this=to_identifier(k), expression=convert(v, copy=copy))
                for k, v in value.__dict__.items()
            ]
        )
    raise ValueError(f"Cannot convert {value}")

def replace_children(expression: Expression, fun: t.Callable, *args, **kwargs) -> None:
    """
    Replace children of an expression with the result of a lambda fun(child) -> exp.
    """
    for k, v in tuple(expression.args.items()):
        is_list_arg = type(v) is list

        child_nodes = v if is_list_arg else [v]
        new_child_nodes = []

        for cn in child_nodes:
            if isinstance(cn, Expression):
                for child_node in ensure_collection(fun(cn, *args, **kwargs)):
                    new_child_nodes.append(child_node)
            else:
                new_child_nodes.append(cn)

        expression.set(k, new_child_nodes if is_list_arg else seq_get(new_child_nodes, 0))

def replace_tree(
    expression: Expression,
    fun: t.Callable,
    prune: t.Optional[t.Callable[[Expression], bool]] = None,
) -> Expression:
    """
    Replace an entire tree with the result of function calls on each node.

    This will be traversed in reverse dfs, so leaves first.
    If new nodes are created as a result of function calls, they will also be traversed.
    """
    stack = list(expression.dfs(prune=prune))

    while stack:
        node = stack.pop()
        new_node = fun(node)

        if new_node is not node:
            node.replace(new_node)

            if isinstance(new_node, Expression):
                stack.append(new_node)

    return new_node

def column_table_names(expression: Expression, exclude: str = "") -> t.Set[str]:
    """
    Return all table names referenced through columns in an expression.

    Example:
        >>> import sqlglot
        >>> sorted(column_table_names(sqlglot.parse_one("a.b AND c.d AND c.e")))
        ['a', 'c']

    Args:
        expression: expression to find table names.
        exclude: a table name to exclude

    Returns:
        A list of unique names.
    """
    return {
        table
        for table in (column.table for column in expression.find_all(Column))
        if table and table != exclude
    }

def table_name(table: Table | str, dialect: DialectType = None, identify: bool = False) -> str:
    """Get the full name of a table as a string.

    Args:
        table: Table expression node or string.
        dialect: The dialect to generate the table name for.
        identify: Determines when an identifier should be quoted. Possible values are:
            False (default): Never quote, except in cases where it's mandatory by the dialect.
            True: Always quote.

    Examples:
        >>> from sqlglot import exp, parse_one
        >>> table_name(parse_one("select * from a.b.c").find(exp.Table))
        'a.b.c'

    Returns:
        The table name.
    """

    table = maybe_parse(table, into=Table, dialect=dialect)

    if not table:
        raise ValueError(f"Cannot parse {table}")

    return ".".join(
        (
            part.sql(dialect=dialect, identify=True, copy=False, comments=False)
            if identify or not SAFE_IDENTIFIER_RE.match(part.name)
            else part.name
        )
        for part in table.parts
    )

def normalize_table_name(table: str | Table, dialect: DialectType = None, copy: bool = True) -> str:
    """Returns a case normalized table name without quotes.

    Args:
        table: the table to normalize
        dialect: the dialect to use for normalization rules
        copy: whether to copy the expression.

    Examples:
        >>> normalize_table_name("`A-B`.c", dialect="bigquery")
        'A-B.c'
    """
    from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

    return ".".join(
        p.name
        for p in normalize_identifiers(
            to_table(table, dialect=dialect, copy=copy), dialect=dialect
        ).parts
    )

def replace_tables(
    expression: E, mapping: t.Dict[str, str], dialect: DialectType = None, copy: bool = True
) -> E:
    """Replace all tables in expression according to the mapping.

    Args:
        expression: expression node to be transformed and replaced.
        mapping: mapping of table names.
        dialect: the dialect of the mapping table
        copy: whether to copy the expression.

    Examples:
        >>> from sqlglot import exp, parse_one
        >>> replace_tables(parse_one("select * from a.b"), {"a.b": "c"}).sql()
        'SELECT * FROM c /* a.b */'

    Returns:
        The mapped expression.
    """

    mapping = {normalize_table_name(k, dialect=dialect): v for k, v in mapping.items()}

    def _replace_tables(node: Expression) -> Expression:
        if isinstance(node, Table) and node.meta.get("replace") is not False:
            original = normalize_table_name(node, dialect=dialect)
            new_name = mapping.get(original)

            if new_name:
                table = to_table(
                    new_name,
                    **{k: v for k, v in node.args.items() if k not in TABLE_PARTS},
                    dialect=dialect,
                )
                table.add_comments([original])
                return table
        return node

    return expression.transform(_replace_tables, copy=copy)

def replace_placeholders(expression: Expression, *args, **kwargs) -> Expression:
    """Replace placeholders in an expression.

    Args:
        expression: expression node to be transformed and replaced.
        args: positional names that will substitute unnamed placeholders in the given order.
        kwargs: keyword arguments that will substitute named placeholders.

    Examples:
        >>> from sqlglot import exp, parse_one
        >>> replace_placeholders(
        ...     parse_one("select * from :tbl where ? = ?"),
        ...     exp.to_identifier("str_col"), "b", tbl=exp.to_identifier("foo")
        ... ).sql()
        "SELECT * FROM foo WHERE str_col = 'b'"

    Returns:
        The mapped expression.
    """

    def _replace_placeholders(node: Expression, args, **kwargs) -> Expression:
        if isinstance(node, Placeholder):
            if node.this:
                new_name = kwargs.get(node.this)
                if new_name is not None:
                    return convert(new_name)
            else:
                try:
                    return convert(next(args))
                except StopIteration:
                    pass
        return node

    return expression.transform(_replace_placeholders, iter(args), **kwargs)

def expand(
    expression: Expression,
    sources: t.Dict[str, Query | t.Callable[[], Query]],
    dialect: DialectType = None,
    copy: bool = True,
) -> Expression:
    """Transforms an expression by expanding all referenced sources into subqueries.

    Examples:
        >>> from sqlglot import parse_one
        >>> expand(parse_one("select * from x AS z"), {"x": parse_one("select * from y")}).sql()
        'SELECT * FROM (SELECT * FROM y) AS z /* source: x */'

        >>> expand(parse_one("select * from x AS z"), {"x": parse_one("select * from y"), "y": parse_one("select * from z")}).sql()
        'SELECT * FROM (SELECT * FROM (SELECT * FROM z) AS y /* source: y */) AS z /* source: x */'

    Args:
        expression: The expression to expand.
        sources: A dict of name to query or a callable that provides a query on demand.
        dialect: The dialect of the sources dict or the callable.
        copy: Whether to copy the expression during transformation. Defaults to True.

    Returns:
        The transformed expression.
    """
    normalized_sources = {normalize_table_name(k, dialect=dialect): v for k, v in sources.items()}

    def _expand(node: Expression):
        if isinstance(node, Table):
            name = normalize_table_name(node, dialect=dialect)
            source = normalized_sources.get(name)

            if source:

                parsed_source = source() if callable(source) else source
                subquery = parsed_source.subquery(node.alias or name)
                subquery.comments = [f"source: {name}"]

                return subquery.transform(_expand, copy=False)

        return node

    return expression.transform(_expand, copy=copy)

def func(name: str, *args, copy: bool = True, dialect: DialectType = None, **kwargs) -> Func:
    """
    Returns a Func expression.

    Examples:
        >>> func("abs", 5).sql()
        'ABS(5)'

        >>> func("cast", this=5, to=DataType.build("DOUBLE")).sql()
        'CAST(5 AS DOUBLE)'

    Args:
        name: the name of the function to build.
        args: the args used to instantiate the function of interest.
        copy: whether to copy the argument expressions.
        dialect: the source dialect.
        kwargs: the kwargs used to instantiate the function of interest.

    Note:
        The arguments `args` and `kwargs` are mutually exclusive.

    Returns:
        An instance of the function of interest, or an anonymous function, if `name` doesn't
        correspond to an existing `sqlglot.expressions.Func` class.
    """
    if args and kwargs:
        raise ValueError("Can't use both args and kwargs to instantiate a function.")

    from sqlglot.dialects.dialect import Dialect

    dialect = Dialect.get_or_raise(dialect)

    converted: t.List[Expression] = [maybe_parse(arg, dialect=dialect, copy=copy) for arg in args]
    kwargs = {key: maybe_parse(value, dialect=dialect, copy=copy) for key, value in kwargs.items()}

    constructor = dialect.parser_class.FUNCTIONS.get(name.upper())
    if constructor:
        if converted:
            if "dialect" in constructor.__code__.co_varnames:
                function = constructor(converted, dialect=dialect)
            else:
                function = constructor(converted)
        elif constructor.__name__ == "from_arg_list":
            function = constructor.__self__(**kwargs)
        else:
            constructor = FUNCTION_BY_NAME.get(name.upper())
            if constructor:
                function = constructor(**kwargs)
            else:
                raise ValueError(
                    f"Unable to convert '{name}' into a Func. Either manually construct "
                    "the Func expression of interest or parse the function call."
                )
    else:
        kwargs = kwargs or {"expressions": converted}
        function = Anonymous(this=name, **kwargs)

    for error_message in function.error_messages(converted):
        raise ValueError(error_message)

    return function

def case(
    expression: t.Optional[ExpOrStr] = None,
    **opts,
) -> Case:
    """
    Initialize a CASE statement.

    Example:
        case().when("a = 1", "foo").else_("bar")

    Args:
        expression: Optionally, the input expression (not all dialects support this)
        **opts: Extra keyword arguments for parsing `expression`
    """
    if expression is not None:
        this = maybe_parse(expression, **opts)
    else:
        this = None
    return Case(this=this, ifs=[])

def array(
    *expressions: ExpOrStr, copy: bool = True, dialect: DialectType = None, **kwargs
) -> Array:
    """
    Returns an array.

    Examples:
        >>> array(1, 'x').sql()
        'ARRAY(1, x)'

    Args:
        expressions: the expressions to add to the array.
        copy: whether to copy the argument expressions.
        dialect: the source dialect.
        kwargs: the kwargs used to instantiate the function of interest.

    Returns:
        An array expression.
    """
    return Array(
        expressions=[
            maybe_parse(expression, copy=copy, dialect=dialect, **kwargs)
            for expression in expressions
        ]
    )

def tuple_(
    *expressions: ExpOrStr, copy: bool = True, dialect: DialectType = None, **kwargs
) -> Tuple:
    """
    Returns an tuple.

    Examples:
        >>> tuple_(1, 'x').sql()
        '(1, x)'

    Args:
        expressions: the expressions to add to the tuple.
        copy: whether to copy the argument expressions.
        dialect: the source dialect.
        kwargs: the kwargs used to instantiate the function of interest.

    Returns:
        A tuple expression.
    """
    return Tuple(
        expressions=[
            maybe_parse(expression, copy=copy, dialect=dialect, **kwargs)
            for expression in expressions
        ]
    )

def true() -> Boolean:
    """
    Returns a true Boolean expression.
    """
    return Boolean(this=True)

def false() -> Boolean:
    """
    Returns a false Boolean expression.
    """
    return Boolean(this=False)

def null() -> Null:
    """
    Returns a Null expression.
    """
    return Null()

def relation(this:str | Identifier,alias:str|Identifier|TableAlias) -> Relation:
    rel = Relation()
    this = this if isinstance(this,Identifier) else to_identifier(this,quoted=False)
    if isinstance(alias,str):
        alias = to_identifier(alias,quoted=False)
    if isinstance(alias,Identifier):
        alias = TableAlias(this=alias)

    rel.args['this'] = this
    rel.args['alias'] = alias

    return rel

def create_an_alias(alias:str,all_alias) -> Identifier:
    num = 0
    while(True):
        tmp = to_identifier(f"{alias.lower()}_{num}",quoted=False)

        if tmp not in all_alias:
            all_alias.append(tmp)
            return tmp
        else:
            num += 1

def check_lower_eq(cols1:list[str] | str,cols2:list[str] | str):
    """
        Check equality of column/table names (str or list[str]) case-insensitively
        Used when converting JOIN to MATCH
    """
    if cols1 is None or cols2 is None:
        return False
    assert type(cols1)==type(cols2)
    if isinstance(cols1,str):
        return cols1.lower() == cols2.lower()
    elif isinstance(cols1,list):
        return len(cols1) == len(cols2) and sorted([col.lower() for col in cols1]) == sorted([col.lower() for col in cols2])
    else:
        raise NotImplementedError("only support str,list now")

def graphpattern(list_of_exp:list[Expression],reverse=False):
    """
    Build a GraphPattern object
    list_of_exp is a list of nodes and relationships
    reverse controls direction; True reverses the pattern
    """
    tmp = GraphPattern()
    tmp.args['this'] = list_of_exp
    tmp.args['reverse'] = reverse
    return tmp
class GraphPattern_Utils:
    @staticmethod
    def is_a_node(exp:Expression):
        return isinstance(exp,(Table,Subquery,CTE))

    @staticmethod
    def is_a_rel(exp:Expression):
        return isinstance(exp,Relation)
    @staticmethod
    def type2num_exp(exp:Expression):
        if GraphPattern_Utils.is_a_node(exp):
            return 1
        elif GraphPattern_Utils.is_a_rel(exp):
            return 0
        else:
            raise TypeError(f"only node and rel are allowed.{exp.__class__} is not allowed.")
    @staticmethod
    def type2num_list(list_of_exp:GraphPattern):

        return [GraphPattern_Utils.type2num_exp(exp) for exp in list_of_exp.args['this']]
    @staticmethod
    def is_a_path(list_of_exp:GraphPattern):
        """
            Return True if the pattern alternates node and relationship
        """
        type_of_list = GraphPattern_Utils.type2num_list(list_of_exp)
        if 0 not in type_of_list:
            return False
        for i in range(1,len(type_of_list)):
            if type_of_list[i] == type_of_list[i-1]:
                return False
        return True
    @staticmethod
    def is_all_node(list_of_exp:GraphPattern):
        """
            Return True if all elements are nodes
        """

        type_of_list = GraphPattern_Utils.type2num_list(list_of_exp)
        return sum(type_of_list) == len(type_of_list)
    @staticmethod
    def is_all_rel(list_of_exp:GraphPattern):
        """
            Return True if all elements are relationships
            Impossible in practice; relationships require nodes
        """
        type_of_list = GraphPattern_Utils.type2num_list(list_of_exp)
        return sum(type_of_list) == 0
    @staticmethod
    def can_merge(list1:GraphPattern,list2:GraphPattern):
        """
        Return whether two paths can be merged
        """
        assert GraphPattern_Utils.is_a_path(list1) and GraphPattern_Utils.is_a_path(list2)

        if list1.reverse != list2.reverse:
            return 0

        if list1.this[-1] == list2.this[0]:
            return 1
        elif list2.this[-1] == list1.this[0]:
            return 2
        return 0
    @staticmethod
    def mergeTwoPattern(list1:GraphPattern,list2:GraphPattern):
        assert GraphPattern_Utils.can_merge(list1,list2)

        return graphpattern(list1.this + list2.this[1:],list1.reverse)
    @staticmethod
    def merge_all_paths(all_paths:list[GraphPattern]):
        """
        Merge all paths
            Repeatedly merge until no more merges are possible
        """
        lst = copy.deepcopy(all_paths)

        changed = True
        while changed:
            changed = False
            new_lst = []
            del_idx = []
            i = 0
            n = len(lst)
            while i < n:
                if i in del_idx:
                    i += 1
                    continue
                j = i + 1
                while j < n:
                    if j in del_idx:
                        j += 1
                        continue
                    can_merge_flag = GraphPattern_Utils.can_merge(lst[i], lst[j])
                    if can_merge_flag > 0:
                        if can_merge_flag==1:
                            merged = GraphPattern_Utils.mergeTwoPattern(lst[i], lst[j])
                        elif can_merge_flag==2:
                            merged = GraphPattern_Utils.mergeTwoPattern(lst[j], lst[i])

                        changed = True
                        del_idx.append(i)
                        del_idx.append(j)
                        new_lst.append(merged)
                        break
                    else:
                        j += 1

                i += 1
            new_lst.extend([e for idx,e in enumerate(lst) if idx not in del_idx])
            lst = new_lst

        return lst

def appendOrExtend(l:list,new_l):
    if isinstance(new_l,list):
        l.extend(new_l)
    elif isinstance(new_l,GraphPattern):
        l.append(new_l)

NONNULL_CONSTANTS = (
    Literal,
    Boolean,
)

CONSTANTS = (
    Literal,
    Boolean,
    Null,
)

