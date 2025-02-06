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
        # Add a new dictionary to store module paths for each class
        self.class_modules = {}
        # Add a dictionary to store full module content
        self.module_contents = {}

    def add_class(self, class_name: str, parent_names: list[str], source_code: str, module_path: str, module_content: str) -> None:
        """
        Add a class and its direct parent classes to the graph.
        
        Args:
            class_name: Name of the class being added
            parent_names: List of direct parent class names
            source_code: Raw source code of the class
            module_path: Path to the module containing the class
            module_content: Full content of the module
        """
        self.direct_parents[class_name] = set(parent_names)
        self.class_source[class_name] = source_code
        self.class_modules[class_name] = module_path
        self.module_contents[module_path] = module_content

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
        self.current_module_content = ""
        self.current_module_path = ""

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
        self.inheritance_graph.add_class(
            full_class_name, 
            base_names, 
            source_code,
            self.current_module_path,
            self.current_module_content
        )

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
        # Store the full module content in the extractor
        extractor.current_module_content = source
        extractor.current_module_path = file_path
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
    """Write subclass-superclass pairs to files with complete module contents."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    def get_classes_in_module(module_path: str, as_super: bool, pairs: list[tuple[str, str]]) -> list[str]:
        """Get classes defined in a module, filtered by their role in the inheritance pairs."""
        classes = set()
        for superclass, subclass in pairs:
            if inheritance_graph.class_modules[superclass] == module_path and as_super:
                classes.add(superclass)
            elif inheritance_graph.class_modules[subclass] == module_path and not as_super:
                classes.add(subclass)
        return sorted(classes)

    def get_other_classes_in_module(module_path: str, pairs: list[tuple[str, str]]) -> list[str]:
        """Get classes defined in a module that aren't involved in these inheritance relationships."""
        involved_classes = set()
        for superclass, subclass in pairs:
            involved_classes.add(superclass)
            involved_classes.add(subclass)
        
        return sorted([
            class_name for class_name, path in inheritance_graph.class_modules.items()
            if path == module_path and class_name not in involved_classes
        ])

    # Group pairs by their module combinations
    module_groups = {}
    for pair in inheritance_graph.get_all_pairs():
        superclass, subclass = pair
        super_module = inheritance_graph.class_modules[superclass]
        sub_module = inheritance_graph.class_modules[subclass]
        
        module_key = (super_module, sub_module)
        if module_key not in module_groups:
            module_groups[module_key] = []
        module_groups[module_key].append((superclass, subclass))
    
    # Write one file per unique module combination
    for (super_module, sub_module), pairs in module_groups.items():
        first_pair = pairs[0]
        output_path = os.path.join(output_dir, f"{first_pair[0]}.{first_pair[1]}.txt")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header with inheritance relationships
            f.write("# Inheritance relationships in this file:\n")
            for superclass, subclass in pairs:
                f.write(f"# - {superclass} -> {subclass}\n")
            f.write("\n")
            
            # List classes in first module
            f.write(f"# Classes in {super_module}:\n")
            f.write("# Superclasses:\n")
            for class_name in get_classes_in_module(super_module, True, pairs):
                f.write(f"# - {class_name}\n")
            if super_module == sub_module:
                f.write("# Subclasses:\n")
                for class_name in get_classes_in_module(super_module, False, pairs):
                    f.write(f"# - {class_name}\n")
            f.write("# Other classes:\n")
            for class_name in get_other_classes_in_module(super_module, pairs):
                f.write(f"# - {class_name}\n")
            f.write("\n")
            
            if super_module != sub_module:
                f.write(f"# Classes in {sub_module}:\n")
                f.write("# Subclasses:\n")
                for class_name in get_classes_in_module(sub_module, False, pairs):
                    f.write(f"# - {class_name}\n")
                f.write("# Other classes:\n")
                for class_name in get_other_classes_in_module(sub_module, pairs):
                    f.write(f"# - {class_name}\n")
                f.write("\n")
            
            # Write module contents
            f.write(f"# Full contents of {super_module}:\n")
            f.write(inheritance_graph.module_contents[super_module])
            
            f.write("\n\n" + "="*80 + "\n\n")
            
            if super_module != sub_module:
                f.write(f"# Full contents of {sub_module}:\n")
                f.write(inheritance_graph.module_contents[sub_module])

if __name__ == "__main__":
    path = "/home/zby/llm/pydantic-ai/pydantic_ai_slim/"
    extractor = ClassInfoExtractor()
    inheritance_graph = process_codebase(path, extractor)
    
    # Now we have the full source code of each class in inheritance_graph.class_source
    # and the inheritance relationships in inheritance_graph.direct_parents
    write_class_pairs(inheritance_graph, "class_pairs")