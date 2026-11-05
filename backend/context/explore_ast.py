# Import the ast module from the standard library to parse and inspect Python syntax trees
import ast
# Import Path from pathlib to handle filesystem paths reliably across different operating systems
from pathlib import Path

# Resolve the path to 'sample_for_testing.py' located in the same directory as this script
sample_path = Path(__file__).parent / "sample_for_testing.py"

# Read the raw Python source code from the file as a UTF-8 string
source_code = sample_path.read_text(encoding="utf-8")

# Parse the Python source code string into an Abstract Syntax Tree (AST) root node
tree = ast.parse(source_code)

# Print a header for the AST dump section
print("=" * 60)
print("AST DUMP (Indented)")
print("=" * 60)

# Print a nicely formatted, readable string representation of the full AST with an indent of 2
print(ast.dump(tree, indent=2))

# Print a header for the top-level nodes section
print("\n" + "=" * 60)
print("TOP-LEVEL NODES IN MODULE BODY")
print("=" * 60)

# Iterate through every node in the top-level body of the module
for node in tree.body:
    # Retrieve the class name of the AST node (such as 'ClassDef' or 'FunctionDef')
    node_type = type(node).__name__
    # Safely retrieve the 'name' attribute if present, otherwise fall back to '<unnamed>'
    node_name = getattr(node, "name", "<unnamed>")
    # Print the node's AST type, its identifier name, and its starting line number in the source file
    print(f"Type: {node_type:<18} Name: {node_name:<15} Line: {node.lineno}")

# Print a header for the class inspection section
print("\n" + "=" * 60)
print("CLASS METHODS AND PARAMETERS")
print("=" * 60)

# Iterate again through the top-level nodes to find class definitions
for node in tree.body:
    # Check if the current top-level node is a class definition (ast.ClassDef)
    if isinstance(node, ast.ClassDef):
        # Print the name of the class
        print(f"Class: {node.name}")
        # Iterate through every statement or definition located inside the class body
        for item in node.body:
            # Check if the child node is a function or method definition
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Extract the parameter name strings from each argument object in item.args.args
                param_names = [arg.arg for arg in item.args.args]
                # Print the method's name and its list of parameter names
                print(f"  Method: {item.name:<10} Parameters: {param_names}")

