import ast

class NodeVisitor(ast.NodeVisitor):
    def generic_visit(self, node):
        self._continue(node)

    def visit_Call(self, node):
        # block datetime.today()
        if node.func.value.id == "datetime" and \
           node.func.attr == "today":
            raise Exception("This function calls datetime.today()"
                            "- use clock.now()")

        # block datetime.now()
        if node.func.value.id == "datetime" and \
           node.func.attr == "now":
            raise Exception("This function calls datetime.now()"
                            "- use clock.now()")

        # block datetime.utcnow()
        if node.func.value.id == "datetime" and \
           node.func.attr == "utcnow":
            raise Exception("This function calls datetime.utcnow()"
                            " - use clock.now()")
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
    except:
        return False
