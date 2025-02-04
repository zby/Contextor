import ast
import os
from typing import Dict
import json
import astor  # For converting AST back to source code

class InheritanceGraph:
    """
    Manages class inheritance relationships and stores class source code.
    """
    def __init__(self):
        # Maps class names to their direct parent classes
        self.direct_parents = {}
        # Maps class names to their source code
        self.class_source = {}

    def add_class(self, class_name: str, parent_names: list[str], source_code: str) -> None:
        """
        Add a class and its direct parent classes to the graph.
        
        Args:
            class_name: Name of the class being added
            parent_names: List of direct parent class names
            source_code: Raw source code of the class
        """
        self.direct_parents[class_name] = set(parent_names)
        self.class_source[class_name] = source_code

    def is_subclass(self, potential_child: str, potential_parent: str) -> bool:
        """
        Check if one class is a subclass of another by recursively traversing the inheritance graph.
        """
        if potential_child == potential_parent:
            return True
        if potential_child not in self.direct_parents:
            return False
        direct_parents = self.direct_parents[potential_child]
        if potential_parent in direct_parents:
            return True
        return any(self.is_subclass(parent, potential_parent) 
                  for parent in direct_parents)

    def get_all_pairs(self) -> list[tuple[str, str]]:
        """
        Find all subclass-superclass pairs in the inheritance graph.
        """
        pairs = []
        for child in self.direct_parents:
            for potential_parent in self.direct_parents:
                if child != potential_parent and self.is_subclass(child, potential_parent):
                    pairs.append((potential_parent, child))
        return pairs

class ClassInfoExtractor(ast.NodeVisitor):
    def __init__(self):
        super().__init__()
        self.inheritance_graph = InheritanceGraph()

    def visit_ClassDef(self, node: ast.ClassDef):
        """Extract class name, bases, and source code."""
        base_names = []

        # Extract direct base classes
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(self._get_full_attr_name(base))

        # Get the source code for the class
        source_code = astor.to_source(node)
        
        # Add to inheritance graph
        full_class_name = self._get_full_class_name(node)
        self.inheritance_graph.add_class(full_class_name, base_names, source_code)

        self.generic_visit(node)

    def _get_full_attr_name(self, node: ast.Attribute) -> str:
        """Return a dotted name for an Attribute node (e.g., 'module.Class')."""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_full_attr_name(node.value)}.{node.attr}"
        else:
            return node.attr

    def _get_full_class_name(self, node: ast.ClassDef) -> str:
        """Construct the full dotted name for a class."""
        full_name = node.name
        current = node
        while hasattr(current, 'parent') and isinstance(current.parent, ast.ClassDef):
            full_name = f"{current.parent.name}.{full_name}"
            current = current.parent
        return full_name

def process_file(file_path: str, extractor: ClassInfoExtractor) -> None:
    """Process a single Python file to extract class information."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, file_path)
        extractor.visit(tree)
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")

def process_codebase(root_dir: str, extractor: ClassInfoExtractor) -> InheritanceGraph:
    """
    Walk through the codebase and process all Python files.
    """
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.py'):
                file_path = os.path.join(dirpath, filename)
                process_file(file_path, extractor)
    
    return extractor.inheritance_graph

def write_class_pairs(inheritance_graph: InheritanceGraph, output_dir: str) -> None:
    """Write subclass-superclass pairs to a JSON file."""
    # make sure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    for pair in inheritance_graph.get_all_pairs():
        output_path = os.path.join(output_dir, f"{pair[0]}.{pair[1]}.txt")
        with open(output_path, 'w', encoding='utf-8') as f:
            superclass = inheritance_graph.class_source[pair[0]]
            subclass = inheritance_graph.class_source[pair[1]]
            f.write(f"Superclass source code:\n{superclass}\n\n")
            f.write(f"Subclass source code:\n{subclass}\n\n")

if __name__ == "__main__":
    path = "/home/zby/llm/pydantic-ai/pydantic_ai_slim/"
    extractor = ClassInfoExtractor()
    inheritance_graph = process_codebase(path, extractor)
    
    # Now we have the full source code of each class in inheritance_graph.class_source
    # and the inheritance relationships in inheritance_graph.direct_parents
    write_class_pairs(inheritance_graph, "class_pairs")