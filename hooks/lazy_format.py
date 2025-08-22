# lazy_format.py
import sys
from pathlib import Path

import libcst as cst
from libcst import matchers as m

LOGGING_METHODS = {"debug", "info", "warning", "error", "critical", "exception"}


class LoggingFstringTransformer(cst.CSTTransformer):
    """
    Transform logging f-strings to %s formatting while preserving comments.
    Converts:
        log.info(f"Failed: {var}")
    To:
        log.info("Failed: %s", var)
    """

    def leave_Call(self, original_node, updated_node):
        # Check for logging calls
        if m.matches(updated_node, m.Call(func=m.Attribute(value=m.Attribute(attr=m.Name("log")), attr=m.Name()))):
            func_attr = updated_node.func.attr.value
            if func_attr in LOGGING_METHODS:
                args = updated_node.args
                if args and isinstance(args[0].value, cst.FormattedString):
                    fstr_node = args[0].value
                    fmt_parts = []
                    values = []

                    for part in fstr_node.parts:
                        if isinstance(part, cst.FormattedStringExpression):
                            fmt_parts.append("%s")
                            values.append(part.expression)
                        elif isinstance(part, cst.FormattedStringText):
                            fmt_parts.append(part.value)

                    new_str = cst.SimpleString(f'"{"".join(fmt_parts)}"')

                    if values:
                        if len(values) > 1:
                            new_args = [cst.Arg(new_str), cst.Arg(cst.Tuple(values))]
                        else:
                            new_args = [cst.Arg(new_str), cst.Arg(values[0])]
                        return updated_node.with_changes(args=new_args)
                    return updated_node.with_changes(args=[cst.Arg(new_str)])
        return updated_node


def fix_file(path: Path):
    source = path.read_text(encoding="utf-8")
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError as e:
        print(f"Skipping {path}: {e}")
        return
    transformer = LoggingFstringTransformer()
    new_tree = tree.visit(transformer)
    new_code = new_tree.code
    if new_code != source:
        path.write_text(new_code, encoding="utf-8")
        print(f"Fixed: {path}")


# def fix_file(path: Path):
#    source = path.read_text(encoding="utf-8")
#    tree = cst.parse_module(source)
#    transformer = LoggingFstringTransformer()
#    new_tree = tree.visit(transformer)
#    new_code = new_tree.code
#    if new_code != source:
#        path.write_text(new_code, encoding="utf-8")
#        print(f"Fixed: {path}")


def main():
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        files = Path(".").rglob("*.py")
    for f in files:
        fix_file(f)
    sys.exit(0)


if __name__ == "__main__":
    main()
