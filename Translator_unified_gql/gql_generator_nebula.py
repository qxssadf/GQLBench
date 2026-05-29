"""
    adapted from sqlglot generator.py
"""
from ast import alias
import os
import sys

from regex import P
from Translator_unified_gql import gql_expressions
from Translator_unified_gql.gql_generator import Generator
from copy import deepcopy
import pandas as pd

def not_None_args_num(exp:gql_expressions):
    return len([v for k,v in exp.args.items() if v is not None])
def can_str_to_num(str_a:str):
    """
    Return True if the string can be converted to a number.
    """
    try:
        float(str_a)
        return True
    except ValueError:
        return False

def exp_is_text(exp_a):
    return exp_a.is_type(gql_expressions.DataType.Type.TEXT) or exp_a.is_type(gql_expressions.DataType.Type.VARCHAR)
def exp_is_date(exp_a):
    return exp_a.is_type(gql_expressions.DataType.Type.DATE)
def exp_is_datetime(exp_a):
    return exp_a.is_type(gql_expressions.DataType.Type.DATETIME)
def fix_type(exp_a,exp_b):

    if isinstance(exp_b,gql_expressions.Literal):
        if exp_a.is_type(gql_expressions.DataType.Type.TEXT) and not exp_b.is_type(gql_expressions.DataType.Type.TEXT):
            exp_b.args['is_string'] = True
        elif not exp_a.is_type(gql_expressions.DataType.Type.TEXT) and exp_b.is_type(gql_expressions.DataType.Type.TEXT):
            exp_b.args['is_string'] = False
        elif exp_is_date(exp_a) and not exp_is_date(exp_b):
            try:
                tmp_exp_b = pd.to_datetime(exp_b.this).date().isoformat()
                exp_b.args['this'] = f"date('{tmp_exp_b}')"
                exp_b.args['is_string'] = False
            except Exception as e:
                pass
            print(repr(exp_b))
        elif exp_is_datetime(exp_a) and not exp_is_datetime(exp_b):
            try:
                tmp_exp_b = pd.to_datetime(exp_b.this).isoformat()
                exp_b.args['this'] = f"local_datetime('{tmp_exp_b}')"
                exp_b.args['is_string'] = False
            except Exception as e:
                pass
            print(repr(exp_b))
        else:
            print('here')
    elif exp_is_date(exp_a) and exp_b.is_type(gql_expressions.DataType.Type.INT):
        exp_b.args['this'] = f"date('{exp_b.this}')"
        exp_b.args['is_string'] = False
class _Generator(type):
    pass

class Generator(metaclass=_Generator):
    """
    Generator converts a given syntax tree to the corresponding GQL string.
    """
    def __init__(self,dialect):
        self.dialect = dialect

    def init_info(self,tablealias2table:dict,all_alias:list[gql_expressions.Identifier],db_name:str,allTables:list,allJoinTables:list):
        self.tablealias2table = tablealias2table
        self.all_alias = all_alias
        self.groupby_alias = {}
        self.subquery_alias = {}
        self.scalar_subquery_alias = {}
        self.outer_scalar_subquery_alias = {}
        self.inner_scalar_subquery_alias = {}
        self.in_collect_query = {}
        self.cur_cte_alias = {}
        self.outer_cte_alias = {}
        self.db_name = db_name
        self.allTables = allTables
        self.allJoinTables = allJoinTables

    def find_source_table_by_alias(self,alias:gql_expressions.Identifier):

        if alias not in self.tablealias2table:
            return None
            raise ValueError("alias not in tablealias2table")

        while True:
            if isinstance(alias,gql_expressions.Identifier) and alias in self.tablealias2table:
                if alias == self.tablealias2table[alias].this:
                    return self.tablealias2table[alias]

                table = self.tablealias2table[alias]
                alias = self.tablealias2table[alias].this

            else:
                break

        return table

    def gql(self,expression:gql_expressions.Expression|str) -> str:

        if isinstance(expression,str):
            return expression
        assert isinstance(expression,gql_expressions.Expression)

        if isinstance(expression, str):
            return expression

        if expression in self.groupby_alias and not isinstance(self.find_subquery_nearest_ancestor(expression),gql_expressions.Where):
            return self.gql(self.groupby_alias[expression])

        exp_handler_name = f"{expression.key}_gql"
        if hasattr(self, exp_handler_name):
            sql = getattr(self, exp_handler_name)(expression)
        else:
            print(expression)
            print(expression.key)
            return "not implemented"
        return sql

    def condition_gql(self):
 
        pass

    def predicate_gql(self):

        pass

    def derivedtable_gql(self):
 
        pass

    def query_gql(self):
 
        pass

    def with_gql(self,exp:gql_expressions.With):
        pass

    def join_gql(self,exp:gql_expressions.Join):
        pass

    def setoperation_gql(self,exp:gql_expressions.SetOperation):
        pass

    def get_cur_scope_subquery(self,ast:gql_expressions.Expression):
 
        subqueries = []
        for node in ast.walk(bfs=True,prune=lambda x:isinstance(x,gql_expressions.Subquery)):
            if node == ast: continue
            if isinstance(node,gql_expressions.Subquery):
                subqueries.append(node)

        return subqueries

    def find_subquery_nearest_ancestor(self,ast:gql_expressions.Subquery):
        """
        Return the nearest Select, Where, Join, or From ancestor of a Subquery to classify subquery usage.
        """
        anc = ast.find_ancestor(gql_expressions.Select,gql_expressions.Where,gql_expressions.Join,gql_expressions.From)
        return anc
NEBULA_KEYWORDS = ['list','type','product','characteristics','match','show']
class Nebula_Generator(Generator):

    def tablealias_gql(self,exp:gql_expressions.TableAlias):

        if exp.name in NEBULA_KEYWORDS:
            return f"{exp.name}_"
        return exp.name

    def column_gql(self,exp:gql_expressions.Column):
        assert (not_None_args_num(exp) == 2 and exp.args.get('this') and exp.args.get('table')) or \
        (not_None_args_num(exp)==1 and exp.args.get('this'))
        col_str = None
        if exp.args.get('table') and exp.args['table'] in self.cur_cte_alias:
            col_str = f"`{exp.name}`"
        elif exp.args.get('table') and not isinstance(self.find_source_table_by_alias(exp.args['table']),(gql_expressions.CTE,gql_expressions.Subquery)):
            if exp.table not in NEBULA_KEYWORDS:
                col_str = f"{exp.table.replace(' ','_').replace('-','_')}.`{exp.name}`"
            else:
                col_str = f"{exp.table.replace(' ','_').replace('-','_') + '_'}.`{exp.name}`"

        else:
            col_str = f"{exp.name}"
        if exp.is_type(gql_expressions.DataType.Type.TEXT) or exp.is_type(gql_expressions.DataType.Type.VARCHAR):
            if exp.parent.is_type(gql_expressions.DataType.Type.FLOAT) or exp.parent.is_type(gql_expressions.DataType.Type.DOUBLE):
                col_str = f"cast ({col_str} as float)"

        return col_str

    def from_gql(self,exp:gql_expressions.From):

        if isinstance(exp.args['this'],gql_expressions.Table):
            return self.gql(exp)
        elif isinstance(exp,gql_expressions.Subquery):
            return self.gql(exp)
        else:
            raise NotImplementedError("From must be Table or Subquery")
    def having_gql(self,exp:gql_expressions.Having):
        assert isinstance(exp,gql_expressions.Having)
        return f"WHERE {self.gql(exp.args['this'])}"

    def identifier_gql(self,exp:gql_expressions.Identifier):
        return exp.name

    def group_gql(self,exp:gql_expressions.Group):
        exps = exp.args['expressions']

        select_fa = self.find_subquery_nearest_ancestor(exp)
        if isinstance(select_fa, gql_expressions.Select):
            select_exprs = []
            select_alias_names = set()
            select_exp_alias_dict = {}
            for expr in select_fa.args['expressions']:
                if isinstance(expr, gql_expressions.Alias):
                    select_exprs.append(expr.this)
                    if expr.args.get("alias"):
                        alias_name = self.gql(expr.args["alias"])
                        select_alias_names.add(alias_name)
                        select_exp_alias_dict[expr.this] = alias_name
                else:
                    select_exprs.append(expr)

        groupby_alias = {}
        def process_group_exp(one_exp):
            one_exp_alias = gql_expressions.create_an_alias("_groupby_col",self.all_alias)
            if isinstance(one_exp,gql_expressions.Subquery):
                if one_exp in self.outer_scalar_subquery_alias:
                    exp_gql = self.gql(self.outer_scalar_subquery_alias[one_exp])
                elif one_exp in self.scalar_subquery_alias:
                    exp_gql = self.gql(self.scalar_subquery_alias[one_exp])
                elif one_exp in self.inner_scalar_subquery_alias:
                    exp_gql = self.gql(self.inner_scalar_subquery_alias[one_exp])
                else:
                    exp_gql = (one_exp,self.gql(one_exp_alias))
            else:
                exp_gql = self.gql(one_exp) if one_exp not in select_exp_alias_dict else self.gql(select_exp_alias_dict[one_exp])
            if isinstance(exp_gql,str):
                if exp_gql in NEBULA_KEYWORDS:
                    res.append(f"{exp_gql}_")
                else:
                    res.append(f"{exp_gql}")
            else:
                scalar_subquery_res.append(exp_gql)

        res = []
        scalar_subquery_res = []
        for one_exp in exps:
            process_group_exp(one_exp)

        select_exps = self.find_subquery_nearest_ancestor(exp).args['expressions']

        for k,v in groupby_alias.items():
            self.groupby_alias[k] = v

        res_str = ', '.join(res)
        return f"GROUP BY {res_str}", scalar_subquery_res

    def group_after_collect_subquery_gql(self,exp:gql_expressions.Group):
        pass

    def limit_gql(self,exp:gql_expressions):
        literal = exp.args['expression']
        assert isinstance(literal,gql_expressions.Literal)
        return f"LIMIT {self.gql(literal)}"

    def literal_gql(self,exp:gql_expressions.Literal):
        assert isinstance(exp, gql_expressions.Literal)
        exp_name = exp.name

        if exp.is_string:
            exp_name = exp_name.replace("\'","\\\'")
            exp_name = f"'{exp_name}'"
        elif exp.is_type(gql_expressions.DataType.Type.INT):
            exp_name = str(int(exp_name))
        return exp_name

    def offset_gql(self,exp:gql_expressions.Offset):
        literal = exp.args['expression']
        assert isinstance(literal,gql_expressions.Literal)
        return f"SKIP {self.gql(literal)}"

    def order_gql(self,exp:gql_expressions.Order):
        ordereds = exp.args['expressions']
        res = []
        pre_res = []
        select_fa = self.find_subquery_nearest_ancestor(exp)

        if isinstance(select_fa, gql_expressions.Select):
            select_exprs = []
            select_alias_names = set()
            select_exp_alias_dict = {}
            select_alias_exp_dict = {}
            for expr in select_fa.args['expressions']:
                if isinstance(expr, gql_expressions.Alias):
                    select_exprs.append(expr.this)
                    if expr.args.get("alias"):
                        alias_name = self.gql(expr.args["alias"])
                        select_alias_names.add(alias_name)
                        select_exp_alias_dict[expr.this] = alias_name
                        select_alias_exp_dict[alias_name] = expr.this
                else:
                    select_exprs.append(expr)

        if select_fa.args.get('group') is None:
            pre_res = [self.ordered_gql(ordered,select_alias_exp_dict=select_alias_exp_dict) for ordered in ordereds]
            res = []
            return ','.join(res), ','.join(pre_res)

        for ordered in ordereds:
            assert isinstance(ordered,gql_expressions.Ordered)
            if isinstance(select_fa, gql_expressions.Select):
                in_select = False
                if ordered.this in select_exprs:
                    in_select = True
                elif isinstance(ordered.this, gql_expressions.Column):
                    ordered_col_name = self.gql(ordered.this.this)
                    if ordered_col_name in select_alias_names:
                        in_select = True
                elif list(ordered.find_all(gql_expressions.Column)):
                    for col in list(ordered.find_all(gql_expressions.Column)):
                        if col.this.this in select_alias_names:
                            in_select = True
                if not in_select:
                    pre_res.append(self.gql(ordered))
                else:
                    res.append(self.ordered_gql(ordered,select_exp_alias_dict=select_exp_alias_dict))
            else:
                res.append(self.gql(ordered))

        if len(pre_res) != 0 and len(res)!=0:
            breakpoint()
        res = ', '.join(res)
        pre_res = ', '.join(pre_res)

        return res,pre_res
        return f"ORDER BY {res}", f"ORDER BY {pre_res}"

    def ordered_gql(self,exp:gql_expressions.Ordered,select_exp_alias_dict:dict={},select_alias_exp_dict:dict={}):
        desc = ""
        if exp.args.get('desc'):
            desc = "DESC" if exp.args['desc'] else "ASC"
        this_gql = self.gql(exp.args['this'])
        if isinstance(exp.this,gql_expressions.Column) and exp.this.name in select_alias_exp_dict:
            this_gql = self.gql(select_alias_exp_dict[exp.this.name])
        if isinstance(exp.this,gql_expressions.Length) and isinstance(exp.this.this,gql_expressions.Column) and exp.this.this.name in select_alias_exp_dict:
            this_gql = f"char_length({self.gql(select_alias_exp_dict[exp.this.this.name])})"
        if exp.this in select_exp_alias_dict:
            this_gql = self.gql(select_exp_alias_dict[exp.this])
        nulls_first = f"NULLS FIRST" if exp.args['nulls_first'] else f"NULLS LAST"
        return f"{this_gql} {desc} {nulls_first}"

    def graphpattern_gql(self,exp:gql_expressions.GraphPattern):
        pattern = exp.args['this']
        reverse = exp.args['reverse']
        if gql_expressions.GraphPattern_Utils.is_all_node(exp):
            return ', '.join([self.gql(node) for node in pattern if not isinstance(node,gql_expressions.Subquery) and not isinstance(self.find_source_table_by_alias(node.this),(gql_expressions.CTE,gql_expressions.Subquery))])
        elif gql_expressions.GraphPattern_Utils.is_a_path(exp):
            path_str = ''.join([(f"<-{self.gql(node)}-" if reverse else f"-{self.gql(node)}->")
                              if isinstance(node,gql_expressions.Relation)
                              else self.gql(node)
                              for node in pattern])
            if isinstance(pattern[0],gql_expressions.Relation):
                path_str = '()' + path_str
            if isinstance(pattern[-1],gql_expressions.Relation):
                path_str += '()'
            return path_str
        else:
            raise ValueError("GraphPattern must be nodes/path")

    def relation_gql(self,exp:gql_expressions.GraphPattern):
        rel_gql = f"[{self.gql(exp.args['alias']).replace(' ','_').replace('-','_')}:`{self.gql(exp.args['this'])}`]"
        return rel_gql

    def table_gql(self,exp:gql_expressions.Table):
        assert len([val for _,val in exp.args.items() if val is not None]) == 2 and exp.args.get('this') and exp.args.get('alias')
        if exp.alias not in NEBULA_KEYWORDS:
            return f"({exp.alias.replace(' ','_').replace('-','_')}@`{exp.name}`)"
        else:
            return f"({exp.alias.replace(' ','_').replace('-','_') + '_'}@`{exp.name}`)"

    def _get_expressions_from_set_operation(self, exp):
        """
        Recursively collect expressions from a set operation or Select.
        If exp is Select, return its expressions.
        If exp is Union/Intersect/Except, recursively collect expressions from this.
        """
        if isinstance(exp, gql_expressions.Select):
            return exp.args.get('expressions', [])
        elif isinstance(exp, (gql_expressions.Union, gql_expressions.Intersect, gql_expressions.Except)):
            return self._get_expressions_from_set_operation(exp.args.get('this'))
        else:
            return []

    def union_gql(self,exp:gql_expressions.Union):
        exp_this_exps = self._get_expressions_from_set_operation(exp)
        for i, (this_exps, expression_exps) in enumerate(zip(exp_this_exps, exp.expression.args.get('expressions',[]))):
            exp.expression.args['expressions'][i].args['alias'].args['this'] = this_exps.alias
        this_gql = self.gql(exp.args['this'])
        expression_gql = self.gql(exp.args['expression'])

        distinct_gql = "DISTINCT" if exp.args.get('distinct') else "ALL"

        limit_gql = "" if exp.args.get('limit') is None else self.gql(self.args.get('limit'))
        order_gql = "" if exp.args.get('order') is None else self.gql(self.args.get('order'))

        return f"{{{this_gql}}} \n UNION {distinct_gql}\n {{{expression_gql}}} \n {order_gql}\n{limit_gql}"

    def intersect_gql(self,exp:gql_expressions.Intersect):
        exp_this_exps = self._get_expressions_from_set_operation(exp)
        for i, (this_exps, expression_exps) in enumerate(zip(exp_this_exps, exp.expression.args.get('expressions',[]))):
            exp.expression.args['expressions'][i].args['alias'].args['this'] = this_exps.alias

        this_gql = self.gql(exp.args['this'])
        expression_gql = self.gql(exp.args['expression'])
        distinct_gql = "DISTINCT" if exp.args.get('distinct') else "ALL"

        limit_gql = "" if exp.args.get('limit') is None else self.gql(self.args.get('limit'))
        order_gql = "" if exp.args.get('order') is None else self.gql(self.args.get('order'))

        return f"{{{this_gql}}} \n INTERSECT {distinct_gql}\n {{{expression_gql}}} \n {order_gql}\n{limit_gql}"

    def except_gql(self,exp:gql_expressions.Except):
        exp_this_exps = self._get_expressions_from_set_operation(exp)
        for i, (this_exps, expression_exps) in enumerate(zip(exp_this_exps, exp.expression.args.get('expressions',[]))):
            exp.expression.args['expressions'][i].args['alias'].args['this'] = this_exps.alias

        this_gql = self.gql(exp.args['this'])
        expression_gql = self.gql(exp.args['expression'])
        distinct_gql = "DISTINCT" if exp.args.get('distinct') else "ALL"

        limit_gql = "" if exp.args.get('limit') is None else self.gql(self.args.get('limit'))
        order_gql = "" if exp.args.get('order') is None else self.gql(self.args.get('order'))

        return f"{{{this_gql}}} \n EXCEPT {distinct_gql}\n {{{expression_gql}}} \n {order_gql}\n{limit_gql}"

    def union_select_gql(self,exp:gql_expressions.Select):
        """
        In GQL UNION subqueries, RETURN aliases must match.

        """

    def select_gql(self,exp:gql_expressions.Select,is_in_subquery:bool=False):

        in_collect_list = []
        where_arg = exp.args.get('where')

        in_collect_copy = deepcopy(self.in_collect_query)
        self.in_collect_query = {}

        self.outer_scalar_subquery_alias = deepcopy(self.scalar_subquery_alias)
        self.scalar_subquery_alias = {}

        self.outer_cte_alias = deepcopy(self.cur_cte_alias)

        if where_arg:
            def collect_in_subqueries(node):
                if isinstance(node, gql_expressions.In):
                    query_arg = node.args.get('query')
                    if query_arg is not None and isinstance(query_arg, gql_expressions.Subquery):
                        if query_arg in in_collect_copy and False:
                            in_alias = in_collect_copy[query_arg]
                        else:
                            in_alias = gql_expressions.create_an_alias("in_collect", self.all_alias)
                        collect_gql = f"LET {self.gql(in_alias)} = VALUE {{ {self.select_gql(query_arg.this,is_in_subquery=True)} }} \n"

                        in_collect_list.append(collect_gql)
                        if query_arg not in self.in_collect_query and query_arg not in in_collect_copy:
                            self.in_collect_query[query_arg] = in_alias

                for arg_name, arg_value in node.args.items():
                    if arg_value is not None:
                        if isinstance(arg_value, list):
                            for item in arg_value:
                                if isinstance(item, gql_expressions.Expression) and not isinstance(item, gql_expressions.Subquery):
                                    collect_in_subqueries(item)
                        elif isinstance(arg_value, gql_expressions.Expression) and not isinstance(arg_value, gql_expressions.Subquery):
                            collect_in_subqueries(arg_value)

            collect_in_subqueries(where_arg)

        distinct_arg = exp.args.get('distinct')
        distinct_gql = self.gql(distinct_arg) if distinct_arg else ""

        with_arg = exp.args.get('with')
        with_gql = self.gql(with_arg) if with_arg else ""

        if with_arg:
            with_gql += "\n"

        match_list = exp.args.get('match',[])
        match_gql_list = [f"MATCH {pattern_str}\n" if (pattern_str := self.gql(pattern))!="" else "" for pattern in match_list ]
        match_gql = ''.join(match_gql_list)
        if len(match_gql)==0:
            match_gql = "\n"
        optional_match_list = exp.args.get('optional_match',[])
        optional_match_gql_list = [f"OPTIONAL MATCH {pattern_str}\n"if (pattern_str := self.gql(pattern))!="" else ""  for pattern in optional_match_list ]
        optional_match_gql = ''.join(optional_match_gql_list)

        match_call_list = []
        for pattern in match_list+optional_match_list:
            if not gql_expressions.GraphPattern_Utils.is_all_node(pattern): continue
            for node in pattern.this:
                if isinstance(node,gql_expressions.Subquery):
                    match_call_list.append(node)
        match_call_str_list = [self.match_call_gql(pattern) for pattern in match_call_list]
        match_call_str = "\n".join(match_call_str_list)
        match_call_str_list += "\n" if len(match_call_str_list)>0 else ""

        match_where_list = exp.args.get('match_where',[])
        match_where_gql_list = [f"{self.gql(pattern)}\n" for pattern in match_where_list]
        match_where_gql = 'AND '.join(match_where_gql_list) if len(match_where_list)>0 else ""

        optional_match_where_list = exp.args.get('optional_match_where',[])
        optional_match_where_gql_list = [f"{self.gql(pattern)}\n" for pattern in optional_match_where_list]
        optional_match_where_gql = "WHERE " + ' AND '.join(optional_match_where_gql_list) if len(optional_match_where_list)>0 else "" + '\n'

        where_arg = exp.args.get('where')
        where_gql = self.where_gql(where_arg) if where_arg else ""
        if match_where_gql and where_gql:
            final_where_gql = "WHERE " + match_where_gql + " AND " + f"({where_gql})"
        elif match_where_gql:
            final_where_gql = "WHERE " + match_where_gql
        elif where_gql:
            final_where_gql = "WHERE " + where_gql + "\n"
        else:
            final_where_gql = ""

        if final_where_gql == "":
            final_where_gql = "WHERE "
            final_where_gql += ' AND '.join(optional_match_where_gql_list) if len(optional_match_where_list)>0 else "" + '\n'
            if final_where_gql == "WHERE \n":
                final_where_gql = ""
        else:
            final_where_gql += ' AND ' + ' AND '.join(optional_match_where_gql_list) if len(optional_match_where_list)>0 else "" + '\n'

        group_arg = exp.args.get('group')
        group_gql,group_scalar_subquery_res_list = self.gql(group_arg) if group_arg else ("",[])
        if group_arg:
            group_gql += "\n"

        having_arg = exp.args.get('having')
        having_gql = self.gql(having_arg) if group_arg and having_arg else ""
        if having_arg:
            having_gql += "\n"

        order_arg = exp.args.get('order')
        order_gql,pre_order_gql = self.gql(order_arg) if order_arg else ("","")
        if len(order_gql) > 0:
            order_gql = f"ORDER BY {order_gql} \n"
        if len(pre_order_gql)>0:
            pre_order_gql = f"ORDER BY {pre_order_gql} \n"

        limit_arg = exp.args.get('limit')
        limit_gql = self.gql(limit_arg) if limit_arg else ""
        if limit_arg:
            limit_gql += '\n'

        offset_arg = exp.args.get('offset')
        offset_gql = self.gql(offset_arg) if offset_arg else ""
        if offset_arg:
            offset_gql += '\n'

        expressions_list = []
        call_list = []

        for tmp_e in exp.args['expressions']:
            if isinstance(tmp_e,gql_expressions.Alias):
                if not isinstance(tmp_e.this,gql_expressions.Subquery):
                    if not is_in_subquery:
                        expressions_list.append(self.gql(tmp_e))

                    else:
                        expressions_list.append(f"{self.alias_gql(tmp_e,is_in_subquery=True)}")

                else:
                    call_, actual_ = self.select_subquery_gql(tmp_e.this) if tmp_e.this not in self.groupby_alias else self.gql(self.groupby_alias[tmp_e.this])
                    call_list.append(call_)
                    expressions_list.append(actual_ + f" AS `{self.gql(tmp_e.alias)}`")

            elif isinstance(tmp_e,gql_expressions.Subquery) and tmp_e.args.get('alias',None) is not None:
                call_, actual_ = self.select_subquery_gql(tmp_e) if tmp_e.this not in self.groupby_alias else self.gql(self.groupby_alias[tmp_e.this])
                call_list.append(call_)
                expressions_list.append(actual_ + " ")
            elif isinstance(tmp_e,gql_expressions.Subquery):
                breakpoint()
                call_, actual_= self.select_subquery_gql(tmp_e) if tmp_e not in self.groupby_alias else self.gql(self.groupby_alias[tmp_e])
                call_list.append(call_)
                expressions_list.append(actual_)
            else:
                raise NotImplementedError("select only Alias and Subquery")

        expression_list_alias = {exp.split(" AS ")[0] : exp.split(" AS ")[1] for exp in expressions_list }
        for k,v in expression_list_alias.items():
            having_gql = having_gql.replace(k,v).replace('`','')
        next_gql = ""
        if having_gql:
            expression_list_alias_values = [v.replace('`','') for v in expression_list_alias.values()]
            next_gql = f"NEXT\n FILTER {having_gql} RETURN {', '.join(expression_list_alias_values)}"

        call_gql = "\n".join(call_list)
        if len(call_list) > 0:
            call_gql += '\n'

        scalar_calls = []
        for subquery, alias in self.scalar_subquery_alias.items():
            call_gql_scalar = f"CALL {{\n  {self.gql(subquery.this)}\n }}\n"
            scalar_calls.append(call_gql_scalar)
        self.scalar_subquery_alias = self.outer_scalar_subquery_alias | self.scalar_subquery_alias
        scalar_calls_gql = "".join(scalar_calls)

        return_gql = f"RETURN {distinct_gql}" + ", ".join(expressions_list)

        for one_exp in group_scalar_subquery_res_list:
            if not isinstance(one_exp,tuple): continue
            if one_exp[0] in self.inner_scalar_subquery_alias:
                tmp_gql = self.gql(self.inner_scalar_subquery_alias[one_exp[0]])
                if group_gql != "":
                    group_gql += f",{tmp_gql} AS {one_exp[1]}\n"
                else:
                    group_gql = f"WITH {tmp_gql} AS {one_exp[1]} \n"

        self.in_collect_query = in_collect_copy
        in_collect_gql = "\n".join(in_collect_list)

        self.cur_cte_alias = deepcopy(self.outer_cte_alias)
        if match_gql == '\n' and final_where_gql.strip() != "":
            final_where_gql = "FILTER " + final_where_gql
        if is_in_subquery:
            return f"{with_gql}{in_collect_gql}{scalar_calls_gql}{call_gql}{match_call_str}{match_gql}{optional_match_gql}{final_where_gql} {pre_order_gql} {offset_gql} {limit_gql}\n {return_gql} \n {group_gql}\n {order_gql} \n {next_gql} \n  "
        return f"{with_gql}{in_collect_gql}{scalar_calls_gql}{call_gql}{match_call_str}{match_gql}{optional_match_gql}{final_where_gql} {pre_order_gql} {return_gql} \n {group_gql}\n {order_gql} \n {next_gql} \n {offset_gql} {limit_gql} "
    def distinct_gql(self,exp:gql_expressions.Distinct):
        distinct_exps = exp.args.get('expressions')
        if distinct_exps:
            res = [self.gql(distinct_exp) for distinct_exp in distinct_exps]
            res = ", ".join(res)
        else:
            res = ""
        return f"DISTINCT {res}"

    def match_call_gql(self,exp:gql_expressions.Subquery):

        assert isinstance(exp,gql_expressions.Subquery)
        this_arg = exp.this
        this_gql = self.gql(this_arg)

        call_res = f"CALL {{\n  {this_gql}\n}}\n"
        return call_res

    def scalar_subquery_gql(self,exp:gql_expressions.Subquery):
        """
        Handle scalar subqueries.
        """
        assert isinstance(exp.this,gql_expressions.Select) and len(exp.this.args.get('expressions'))==1
        if exp in self.outer_scalar_subquery_alias:
            return f"`{self.gql(self.outer_scalar_subquery_alias[exp])}`"
        if exp not in self.scalar_subquery_alias:
            if exp.args.get('alias') is not None:
                scalar_alias = exp.args['alias'].this
            else:
                scalar_alias = exp.this.args['expressions'][0].args['alias']

            self.scalar_subquery_alias[exp] = scalar_alias
            self.inner_scalar_subquery_alias[exp] = scalar_alias

        return f"{self.gql(self.scalar_subquery_alias[exp])}"

    def subquery_gql(self,exp:gql_expressions.Subquery):
        this_arg = exp.this
        self.subquery_alias[exp] = this_arg

    def select_subquery_gql(self,exp:gql_expressions.Subquery):
        """
        Subquery in SELECT expressions; must be a scalar SELECT (one row, one column).
        """
        assert isinstance(exp.parent,gql_expressions.Select) or (isinstance(exp.parent,gql_expressions.Alias) and isinstance(exp.parent.parent,gql_expressions.Select)) or isinstance(self.find_subquery_nearest_ancestor(exp),gql_expressions.Select)
        this_arg = exp.args['this']
        this_gql = self.gql(this_arg)

        select_alias = this_arg.args['expressions'][0].args['alias']
        select_alias_gql = self.gql(select_alias)

        alias_arg = exp.args.get('alias')
        alias_gql = f"AS {self.gql(alias_arg)}" if alias_arg else ""

        call_res = f"CALL {{\n  {this_gql}\n}}\n"
        actual_res = f"{select_alias_gql} {alias_gql}"

        return call_res,actual_res

    def where_gql(self,exp:gql_expressions.Where):
        where_arg = exp.args['this']
        return self.gql(where_arg)

    def alias_gql(self,exp:gql_expressions.Alias,is_in_subquery:bool=False):
        this_arg = exp.args['this']
        alias_arg = exp.args['alias']

        if this_arg in self.groupby_alias:
            this_gql = self.gql(this_arg)
            self.groupby_alias[this_arg] = alias_arg
        elif this_arg in self.subquery_alias:
            this_arg = self.subquery_alias[this_arg]
            this_gql = self.gql(this_arg)
        else:
            this_gql = self.gql(this_arg)

        if is_in_subquery:
            this_gql = f"collect({this_gql})"
        alias_gql = self.gql(alias_arg)
        if this_gql==f"`{alias_gql}`":
            return this_gql
        if alias_gql in NEBULA_KEYWORDS:
            alias_gql = f"{alias_gql}_"
        return f"{this_gql} AS `{alias_gql}`"

    def eq_gql(self,exp:gql_expressions.EQ):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} = {right_gql}"

    def neq_gql(self,exp:gql_expressions.NEQ):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} <> {right_gql}"

    def is_gql(self,exp:gql_expressions.Is):
        if isinstance(exp.expression,gql_expressions.Null):
            return f"{self.gql(exp.this)} IS {self.gql(exp.expression)}"
        elif isinstance(exp.expression,gql_expressions.Literal):
            return f"{self.gql(exp.this)} = {self.gql(exp.expression)}"
        else:
            raise NotImplementedError("is expression can onpy be NULL or Literal")

    def in_gql(self,exp:gql_expressions.In):
        this_arg = exp.this
        this_gql = self.gql(this_arg)
        expressions_arg = exp.args.get('expressions')
        query_arg = exp.args.get('query')

        if expressions_arg is not None:
            expressions_gql = ", ".join([self.gql(element) if not isinstance(element,gql_expressions.Subquery) else self.scalar_subquery_gql(element) for element in expressions_arg])
            expressions_gql = f"[{expressions_gql}]"
            return f"{this_gql} IN {expressions_gql}"
        elif query_arg is not None:
            if query_arg in self.in_collect_query:
                return f"{this_gql} IN {self.gql(self.in_collect_query[query_arg])}"
            else:
                query_gql = self.select_gql(query_arg.this,is_in_subquery=True)
                alias_arg = query_arg.args.get('alias')
                assert alias_arg is None
                return f"{this_gql} IN VALUE {{ {query_gql} }}"

    def logical_gql(self,exp):
        left_gql, right_gql = self.gql(exp.left), self.gql(exp.right)

        left_gql = self.gql(exp.left) if not isinstance(exp.left,gql_expressions.Subquery) else self.scalar_subquery_gql(exp.left)
        right_gql = self.gql(exp.right) if not isinstance(exp.right,gql_expressions.Subquery) else self.scalar_subquery_gql(exp.right)
        if exp.left.is_type(gql_expressions.DataType.Type.INT) or exp.left.is_type(gql_expressions.DataType.Type.FLOAT):
            left_gql = f"{left_gql} <> 0"
        if exp.right.is_type(gql_expressions.DataType.Type.INT) or exp.right.is_type(gql_expressions.DataType.Type.FLOAT):
            right_gql = f"{right_gql} <> 0"

        if isinstance(exp.right,gql_expressions.Literal) and exp.right.is_string:
            right_value = exp.right.this
            digit_chars = []
            for i,char in enumerate(right_value):
                if char.isdigit() or (i==0 and char=='-'):
                    digit_chars.append(char)
                else:
                    break
            if can_str_to_num(right_value) and float(right_value)!=0:
                right_gql = "True"
            else:
                right_gql = "False"

        elif isinstance(exp.left,gql_expressions.Literal) and exp.left.is_string:
            left_value = exp.left.this
            if can_str_to_num(left_value) and float(left_value)!=0:
                left_gql = "True"
            else:
                left_gql = "False"
        return left_gql, right_gql
    def and_gql(self,exp:gql_expressions.And):
        left_gql, right_gql = self.logical_gql(exp)
        return f"{left_gql} AND {right_gql}"

    def or_gql(self,exp:gql_expressions.Or):

        left_gql, right_gql = self.logical_gql(exp)
        return f"{left_gql} OR {right_gql}"

    def paren_gql(self,exp:gql_expressions.Paren):
        return f"({self.gql(exp.this)})"

    def cast_gql(self,exp:gql_expressions.Cast):
        assert isinstance(exp.to,gql_expressions.DataType)
        this_arg = exp.this
        this_gql = self.gql(this_arg)
        if isinstance(this_arg,gql_expressions.Subquery):
            this_gql = self.scalar_subquery_gql(this_arg)

        if exp.to.is_type(gql_expressions.DataType.Type.FLOAT):
            return f"cast ({this_gql} as float)"
        elif exp.to.is_type(gql_expressions.DataType.Type.TEXT):
            return f"cast ({this_gql} as string)"
        elif exp.to.is_type(gql_expressions.DataType.Type.INT):
            return f"cast ({this_gql} as int)"
        else:
            raise NotImplementedError("not imlemented cast type")
    def not_gql(self,exp:gql_expressions.Not):
        return f"NOT {self.gql(exp.this)}"

    def null_gql(self,exp:gql_expressions.Null):
        return "NULL"

    def count_gql(self,exp:gql_expressions.Count):
        return f"COUNT({self.gql(exp.this)})"
    def avg_gql(self,exp:gql_expressions.Avg):
        return f"avg({self.gql(exp.this)})"
    def like_gql(self,exp:gql_expressions.Like):
        """
        LIKE with Column on the right is handled in preprocessing; right should be Literal here.
        """

        left_gql = self.gql(exp.left)
        right_gql = self.gql(exp.right)
        if exp.left.is_type(gql_expressions.DataType.Type.DATETIME) or exp.left.is_type(gql_expressions.DataType.Type.DATE):
            left_gql = f"cast ({left_gql} as string)"
        else:
            pass
        return f"like({left_gql},{right_gql})"

    def substring_gql(self,exp:gql_expressions.Substring):
        this_gql = self.gql(exp.this)
        start_arg = exp.args.get('start')
        length_arg = exp.args.get('length')

        if length_arg is None:
            start_gql = f"{self.gql(start_arg)}-1"
            return f"CASE WHEN {start_gql} < 0 THEN substring({this_gql},length({this_gql})+1+({start_gql}),-1-({start_gql})) ELSE substring({this_gql},{start_gql}, length({this_gql})-({start_gql})) END"

        start_gql = f"{self.gql(start_arg)}-1"
        length_gql = self.gql(length_arg)
        return f"CASE \
 WHEN {start_gql} < 0 AND {length_gql} < 0 \
 THEN substring({this_gql},length({this_gql})+1+({start_gql})+{length_gql},-({length_gql})) \
 WHEN {start_gql} < 0 AND {length_gql} >= 0 \
 THEN substring({this_gql},length({this_gql})+1+({start_gql}),{length_gql}) \
 WHEN {start_gql} >= 0 AND {length_gql} < 0 \
 THEN substring({this_gql},{start_gql}+1+({length_gql}),-({length_gql})) \
 ELSE substring({this_gql},{start_gql},{length_gql}) END"

        return f"substring({this_gql},{start_gql},{length_gql})"

    def strposition_gql(self,exp:gql_expressions.StrPosition):
        this_arg = exp.this
        substr_arg = exp.args['substr']

        this_gql = self.gql(this_arg)
        substr_gql = self.gql(substr_arg)
        return f"(position({substr_gql},{this_gql}) + 1)"

    def replace_gql(self,exp:gql_expressions.Replace):
        this_arg = exp.this
        expression_arg = exp.args['expression']
        replacement_arg = exp.args['replacement']

        this_str = self.gql(this_arg)
        expression_str = self.gql(expression_arg)
        replacement_str = self.gql(replacement_arg)
        return f"replace({this_str},{expression_str},{replacement_str})"

    def neg_gql(self,exp:gql_expressions.Neg):
        return f"-{self.gql(exp.this)}"

    def max_gql(self,exp:gql_expressions.Max):
        this_arg = exp.this
        expressions_arg = exp.args.get('expressions')

        if expressions_arg is None or len(expressions_arg)==0:
            return f"MAX({self.gql(this_arg)})"
        else:
            res_list = [this_arg] + expressions_arg
            res_list = [self.gql(element) for element in res_list]
            return f"MAX({res_list})"

    def binary_gql(self,exp:gql_expressions.Binary):
        left_arg = exp.left
        right_arg = exp.right

        fix_type(left_arg,right_arg)
        fix_type(right_arg,left_arg)

        left_gql = self.gql(left_arg) if not isinstance(left_arg,gql_expressions.Subquery) else self.scalar_subquery_gql(left_arg)
        right_gql = self.gql(right_arg) if not isinstance(right_arg,gql_expressions.Subquery) else self.scalar_subquery_gql(right_arg)
        if isinstance(exp,(gql_expressions.Add,gql_expressions.Sub,gql_expressions.Mul,gql_expressions.Div)) and not exp_is_date(left_arg) and not exp_is_date(right_arg):
            if left_arg.is_type(gql_expressions.DataType.Type.TEXT) or left_arg.is_type(gql_expressions.DataType.Type.VARCHAR):
                left_gql = f"cast ({left_gql} as float)"
                if isinstance(right_arg,gql_expressions.Literal) and right_arg.args['is_string']:
                    right_gql = f"cast ({right_gql} as float)"
            elif left_arg.is_type(gql_expressions.DataType.Type.BOOLEAN):
                left_gql = f"cast ({left_gql} as int)"
            if right_arg.is_type(gql_expressions.DataType.Type.TEXT) or right_arg.is_type(gql_expressions.DataType.Type.VARCHAR):
                right_gql = f"cast ({right_gql} as float)"
                if isinstance(left_arg,gql_expressions.Literal) and left_arg.args['is_string']:
                    left_gql = f"cast ({left_gql} as float)"
            elif right_arg.is_type(gql_expressions.DataType.Type.BOOLEAN):
                right_gql = f"cast ({right_gql} as int)"

        if isinstance(exp,gql_expressions.EQ):
            if left_arg.is_type(gql_expressions.DataType.Type.BOOLEAN):
                left_gql = f"cast ({left_gql} as int)"
            if right_arg.is_type(gql_expressions.DataType.Type.BOOLEAN):
                right_gql = f"cast ({right_gql} as int)"

        if exp_is_date(left_arg) and right_arg.is_type(gql_expressions.DataType.Type.TEXT):
            right_gql = f"local_datetime({right_gql},\"%Y-%m-%dT%H:%M:%S\")"
            right_arg._type = left_arg._type.copy()
        if exp_is_date(right_arg) and left_arg.is_type(gql_expressions.DataType.Type.TEXT):
            left_gql = f"local_datetime({left_gql},\"%Y-%m-%dT%H:%M:%S\")"
            left_arg._type = right_arg._type.copy()

        return left_gql,right_gql

    def add_gql(self,exp:gql_expressions.Add):
        left_gql,right_gql = self.binary_gql(exp)

        return f"{left_gql} + {right_gql}"

    def sub_gql(self,exp:gql_expressions.Sub):
        left_gql,right_gql = self.binary_gql(exp)
        if exp_is_datetime(exp.left) and exp_is_datetime(exp.right):
            return f"duration_between({left_gql},{right_gql})"
        if exp_is_date(exp.left) and exp_is_date(exp.right):
            return f"duration_between({left_gql},{right_gql})"
        return f"{left_gql} - {right_gql}"

    def mul_gql(self,exp:gql_expressions.Mul):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} * {right_gql}"

    def div_gql(self,exp:gql_expressions.Div):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} / {right_gql}"

    def lt_gql(self,exp:gql_expressions.LT):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} < {right_gql}"

    def lte_gql(self,exp:gql_expressions.LTE):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} <= {right_gql}"

    def gt_gql(self,exp:gql_expressions.GT):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} > {right_gql}"

    def gte_gql(self,exp:gql_expressions.GTE):
        left_gql,right_gql = self.binary_gql(exp)
        return f"{left_gql} >= {right_gql}"

    def sum_gql(self,exp:gql_expressions.Sum):

        if isinstance(exp.this,(gql_expressions.EQ, gql_expressions.GT, gql_expressions.GTE, gql_expressions.LT, gql_expressions.LTE, gql_expressions.NEQ,gql_expressions.And,gql_expressions.Or,gql_expressions.Not)):
            return f"sum(cast ({self.gql(exp.this)} as int))"

        return f"sum({self.gql(exp.this)})"

    def window_gql(self,exp:gql_expressions.Window):
        this_arg = exp.this
        order_arg = exp.args.get('order')
        partition_arg = exp.args.get('partition_by')

        if this_arg == "RANK":
            assert order_arg is not None

    def anonymous_gql(self,exp:gql_expressions.Anonymous):
        this_arg = exp.this
        print(this_arg)
        if this_arg == "RANK":
            pass
        elif this_arg == "strftime":
            pass
        elif this_arg == "DATETIME":

            if len(exp.expressions)==2 and isinstance(exp.expressions[0],gql_expressions.CurrentTimestamp) and exp.expressions[1].name == "localtime":
                return "local_datetime()"
            elif len(exp.expressions)==1 and isinstance(exp.expressions[0],gql_expressions.Column):
                return self.gql(exp.expressions[0])
            else:
                raise NotImplementedError("not implemented datetime")
            return "date()"
        elif this_arg == "TIME":
            return "local_datetime()"
    def timetostr_gql(self,exp:gql_expressions.TimeToStr):
        assert len(exp.args) == 2
        assert isinstance(exp.this,gql_expressions.TsOrDsToTimestamp)
        this_str = self.gql(exp.this)
        format_str = self.gql(exp.args['format']).replace("%Y","yyyy").replace("%m","MM").replace("%d","dd")
        return f"CASE WHEN {this_str} is not NULL THEN apoc.temporal.format({this_str},{format_str}) ELSE NULL END"

    def tsordstotimestamp_gql(self,exp:gql_expressions.TsOrDsToTimestamp):
        assert len(exp.args) == 1
        if exp.this.is_type(gql_expressions.DataType.Type.DATE) and self.gql(exp.this.this).lower() == "\'now\'":
            return "local_datetime()"
        return self.gql(exp.this)

    def currenttimestamp_gql(self,exp:gql_expressions.CurrentTimestamp):
        return "local_datetime()"

    def date_gql(self,exp:gql_expressions.Date):
        if exp.this is not None:
            return f"cast({self.gql(exp.this)} as date)"
        else:
            return "date()"
    def between_gql(self,exp:gql_expressions.Between):
        this_arg = exp.this
        low_arg = exp.args['low']
        high_arg = exp.args['high']

        this_str = self.gql(this_arg)
        low_str = self.gql(low_arg) if not isinstance(low_arg,gql_expressions.Subquery) else self.scalar_subquery_gql(low_arg)
        high_str = self.gql(high_arg) if not isinstance(high_arg,gql_expressions.Subquery) else self.scalar_subquery_gql(high_arg)

        first_exp = gql_expressions.GTE()
        first_exp.args['this'] = this_arg
        first_exp.args['expression'] = low_arg

        second_exp = gql_expressions.LTE()
        second_exp.args['this'] = this_arg
        second_exp.args['expression'] = high_arg

        return f"{self.gql(first_exp)} AND {self.gql(second_exp)}"

    def case_gql(self,exp:gql_expressions.Case):
        ifs = exp.args.get('ifs')
        ifs_str = ' '.join([self.if_in_case_gql(if_) for if_ in ifs])

        this_arg = exp.this
        this_str = self.gql(this_arg) if this_arg else ""
        default_arg = exp.args.get('default')

        default_str = f"ELSE {self.gql(default_arg)}" if default_arg else ""

        return f"CASE {this_str} {ifs_str} {default_str} END"

    def if_in_case_gql(self,exp:gql_expressions.If):
        this_arg = exp.this
        this_str = self.gql(this_arg)
        if this_arg is not None and (this_arg.is_type(gql_expressions.DataType.Type.INT) or this_arg.is_type(gql_expressions.DataType.Type.FLOAT)):
            this_str = this_str + "<> 0"

        true_arg = exp.args.get('true')
        true_str = self.gql(true_arg)

        false_arg = exp.args.get('false')
        false_str = self.gql(false_arg) if false_arg else 'NULL'
        return f"WHEN {this_str} THEN {true_str}"

    def if_gql(self,exp:gql_expressions.If):
        this_arg = exp.this
        this_str = self.gql(this_arg)
        true_arg = exp.args.get('true')
        true_str = self.gql(true_arg)

        false_arg = exp.args.get('false')

        if false_arg.is_type(gql_expressions.DataType.Type.INT) and true_arg.is_type(gql_expressions.DataType.Type.TEXT):
            true_str = f"cast ({true_str} as float)"

        false_str = self.gql(false_arg) if false_arg else 'NULL'

        return f"CASE WHEN {this_str} THEN {true_str} ELSE {false_str} END"
    def star_gql(self,exp:gql_expressions.Star):
        return "*"
    def min_gql(self,exp:gql_expressions.Min):
        return f"min({self.gql(exp.this)})"
    def abs_gql(self,exp:gql_expressions.Abs):
        return f"abs({self.gql(exp.this)})"

    def dpipe_gql(self,exp:gql_expressions.DPipe):
        left_arg = exp.left
        right_arg = exp.right

        left_gql = self.gql(left_arg)
        right_gql = self.gql(right_arg)

        return f"{left_gql} || {right_gql}"

    def round_gql(self,exp:gql_expressions.Round):
        this_arg = exp.this
        this_gql = self.gql(this_arg)

        if exp.args.get('decimals') is None:
            return f"round({this_gql})"

        decimals_arg = exp.args.get('decimals')
        decimals_gql = self.gql(decimals_arg)

        return f"round({this_gql},{decimals_gql})"

    def length_gql(self,exp:gql_expressions.Length):
        this_arg = exp.this
        this_gql = self.gql(this_arg)

        if this_arg.is_type(gql_expressions.DataType.Type.INT):
            return f"char_length(cast ({this_gql} as string))"
        return f"char_length({this_gql})"

    def exists_gql(self,exp:gql_expressions.Exists):
        this_arg = exp.this
        this_gql = self.gql(this_arg)
        return f"EXISTS{{{this_gql}}}"

    def boolean_gql(self,exp:gql_expressions.Boolean):
        if exp.this:
            return 'TRUE'
        else:
            return 'FALSE'

    def lower_gql(self,exp:gql_expressions.Lower):
        return f"lower({self.gql(exp.this)})"

    def trim_gql(self,exp:gql_expressions.Trim):
        this_arg = exp.this
        this_str = self.gql(this_arg)
        exp_arg = exp.expression
        exp_str = self.gql(exp_arg)
        return f"trim(BOTH {exp_str} FROM {this_str})"

if __name__ == "__main__":
    pass
