import ast
import inspect
import logging

from .error import PrevalentError

logger = logging.getLogger(__name__)

FORBIDDEN_OBJECTS = ('datetime', 'date')

DATE_FUNCS = ('today',)

DATETIME_FUNCS = ('now', 'utcnow')

FORBIDDEN_FUNCS = DATE_FUNCS + DATETIME_FUNCS

class NodeVisitor(ast.NodeVisitor):
    def generic_visit(self, node):
        self._continue(node)

    def visit_Call(self, node):
        if not hasattr(node.func, 'value'):
            '''
                Ignore calls from nodes with no 'value' attribute,
                like constructors calls MyClass()
            '''
            return
        if isinstance(node.func.value, ast.Attribute):
            '''
                In this case we can't be sure if it's a call from a date or
                datetime instance
            '''
            if node.func.value.attr == "_clock":
                '''
                    A call to self._clock.method() wich is ok.
                '''
                return
            elif node.func.attr in FORBIDDEN_FUNCS:
                logger.warn("Dont call now(), utcnow() nor today() from date"
                            " or datetime objects. Use the clock instead.")
        elif isinstance(node.func.value, ast.Subscript):
            '''
                Ignore var[something] pattern
            '''
            return
        elif isinstance(node.func.value, ast.Str):
            '''
                ignore ''.join([]) patterns
            '''
            return
        elif hasattr(node.func.value, 'id'):
            if node.func.value.id in FORBIDDEN_OBJECTS and \
               node.func.attr in FORBIDDEN_FUNCS:
                '''
                    Bad calls: date.today(), datetime.now(), datetime.utcnow()
                '''
                raise Exception("This function calls %s.%s()- use clock.%s()" % \
                                (node.func.value.id, node.func.attr, node.func.attr))

        self._continue(node)

    def _continue(self, stmt):
        '''Helper: parse a node's children'''
        super(NodeVisitor, self).generic_visit(stmt)

def validate_date_datetime_calls(function):
    tree = ast.parse(function)
    node = NodeVisitor()
    try:
        node.visit(tree)
        return True
    except Exception as e:
        return False

def unindent_source(source_lines):
    source = source_lines[0]
    unindent_level = len(source) - len(source.lstrip())
    return "\n".join([line[unindent_level:] for line in source_lines])

def validate_system(system_instance):
    for (method_name, method) in inspect.getmembers(system_instance,
                                                    predicate=inspect.ismethod):
        if method_name.startswith("__") and method_name.endswith("__"):
            continue
        fixed_source = unindent_source(inspect.getsourcelines(method)[0])
        valid = validate_date_datetime_calls(fixed_source)
        if not valid:
            raise PrevalentError("%s contains methods with invalid calls "\
                                 "on method %s:\n%s" % (system_instance,
                                                        method_name,
                                                        fixed_source))
    return True
