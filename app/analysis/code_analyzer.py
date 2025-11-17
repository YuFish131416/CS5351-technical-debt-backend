# app/analysis/code_analyzer.py
from typing import Dict, List, Optional
import ast
import logging
import os
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

from app.analysis.base import BaseAnalyzer


logger = logging.getLogger(__name__)


class CodeComplexityAnalyzer(BaseAnalyzer):
    """代码复杂度分析器，支持 Python 及通用文本文件的静态信号"""

    async def analyze(self, project_path: str, project_root: Optional[str] = None, **_: Dict) -> Dict:
        complexity_data: Dict[str, Dict] = {}
        project_root_path = self._determine_project_root(project_path, project_root)

        for file_path in self._find_source_files(project_path):
            try:
                abs_path = Path(file_path).resolve()
                rel_path = self._to_relative_path(abs_path, project_root_path)

                with open(abs_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()

                language_hint = self._detect_language(abs_path)

                if language_hint == 'python':
                    complexity_results = cc_visit(source_code)
                    avg_complexity = self._calculate_avg_complexity(complexity_results)
                    max_complexity = max((result.complexity for result in complexity_results), default=0.0)

                    maintainability_index = self._extract_maintainability(mi_visit(source_code, multi=True))

                    raw_metrics = analyze(source_code)
                    comment_density = raw_metrics.comments / raw_metrics.loc if raw_metrics.loc > 0 else 0.0
                    smell_info = self._detect_code_smells(source_code, complexity_results)

                    complexity_data[rel_path] = {
                        'relative_path': rel_path,
                        'absolute_path': str(abs_path),
                        'language': language_hint,
                        'avg_complexity': avg_complexity,
                        'max_complexity': max_complexity,
                        'maintainability_index': maintainability_index,
                        'lines_of_code': raw_metrics.loc,
                        'logical_lines': raw_metrics.lloc,
                        'comment_density': comment_density,
                        'function_count': len(complexity_results),
                        'smell_score': smell_info['smell_score'],
                        'smell_flags': smell_info['smell_flags'],
                        'smell_samples': smell_info['samples'],
                        'longest_line': smell_info['longest_line'],
                        'long_line_count': smell_info['long_line_count'],
                        'long_function_count': smell_info['long_function_count'],
                        'high_complexity_blocks': smell_info['high_complexity_blocks'],
                        'max_nesting_depth': smell_info['max_nesting_depth'],
                        'deeply_nested_functions': smell_info['deeply_nested_functions'],
                        'long_parameter_functions': smell_info['long_parameter_functions'],
                        'complex_conditionals': smell_info['complex_conditionals'],
                        'uninformative_identifiers': smell_info['uninformative_identifiers'],
                    }
                else:
                    complexity_data[rel_path] = self._analyze_non_python(
                        source_code, abs_path, rel_path, language_hint
                    )

            except Exception:
                logger.exception("Error analyzing %s", file_path)
                continue

        return complexity_data

    def _find_source_files(self, project_path: str) -> List[str]:
        src_files: List[str] = []
        p = Path(project_path)

        if p.is_file():
            return [str(p)]

        exts = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.cpp', '.c', '.map', '.json', '.css', '.html'
        }
        skip_dirs = {
            '.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build'
        }

        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                file_path = Path(root) / fname
                suffixes = [s.lower() for s in file_path.suffixes]
                if not suffixes:
                    continue
                last = suffixes[-1]
                second_last = suffixes[-2] if len(suffixes) > 1 else ''
                if last in exts:
                    src_files.append(str(file_path))
                elif last == '.map' and second_last in {'.js', '.ts'}:
                    src_files.append(str(file_path))
        return src_files

    def _determine_project_root(self, project_path: str, project_root: Optional[str]) -> Path:
        if project_root:
            candidate = Path(project_root).resolve()
        else:
            candidate = Path(project_path).resolve()

        if candidate.is_dir():
            return candidate
        return candidate.parent

    def _to_relative_path(self, file_path: Path, project_root: Path) -> str:
        try:
            return str(file_path.relative_to(project_root)).replace('\\', '/')
        except ValueError:
            return str(file_path).replace('\\', '/')

    def _extract_maintainability(self, value) -> float:
        if value is None:
            return 100.0
        if isinstance(value, (list, tuple)):
            values = [float(v) for v in value if v is not None]
            if not values:
                return 100.0
            return sum(values) / len(values)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 100.0

    def _calculate_avg_complexity(self, complexity_results: List) -> float:
        if not complexity_results:
            return 0.0
        return sum(result.complexity for result in complexity_results) / len(complexity_results)

    def _detect_code_smells(self, source_code: str, complexity_results: List) -> Dict:
        lines = source_code.splitlines()
        long_line_threshold = 120
        extreme_line_threshold = 180
        long_lines = [(idx + 1, len(line)) for idx, line in enumerate(lines) if len(line) > long_line_threshold]
        longest_line = max((len(line) for line in lines), default=0)
        line_count = len(lines)

        high_complexity_blocks = []
        long_functions = []
        for result in complexity_results:
            complexity = getattr(result, 'complexity', 0.0) or 0.0
            start_line = getattr(result, 'lineno', None)
            end_line = getattr(result, 'endline', start_line)
            length = (end_line - start_line + 1) if (start_line and end_line and end_line >= start_line) else 0
            block_name = getattr(result, 'name', 'unknown')

            if complexity >= 12:
                high_complexity_blocks.append({
                    'name': block_name,
                    'complexity': complexity,
                    'start_line': start_line,
                    'end_line': end_line,
                })

            if length >= 80:
                long_functions.append({
                    'name': block_name,
                    'length': length,
                    'start_line': start_line,
                    'end_line': end_line,
                })

        ast_metrics = self._analyze_ast_smells(source_code)

        smell_flags: List[str] = []
        if longest_line >= extreme_line_threshold:
            smell_flags.append('Lines exceeding 180 characters')
        if len(long_lines) >= 5:
            smell_flags.append('Multiple overlength lines')
        if high_complexity_blocks:
            smell_flags.append('Functions with very high cyclomatic complexity')
        if long_functions:
            smell_flags.append('Long methods (>80 lines) detected')
        if ast_metrics['deeply_nested_functions']:
            smell_flags.append('Deeply nested control flow')
        if ast_metrics['long_parameter_functions']:
            smell_flags.append('Functions with too many parameters')
        if ast_metrics['complex_conditionals']:
            smell_flags.append('Complex boolean expressions')
        if ast_metrics['uninformative_identifiers']:
            smell_flags.append('Uninformative identifier names')

        smell_score = 0.0
        smell_score += min(len(long_lines) / 30, 0.35)
        smell_score += min(len(high_complexity_blocks) / 5, 0.4)
        smell_score += min(len(long_functions) / 4, 0.35)
        smell_score += min(len(ast_metrics['deeply_nested_functions']) / 3, 0.4)
        smell_score += min(len(ast_metrics['long_parameter_functions']) / 4, 0.3)
        smell_score += min(len(ast_metrics['complex_conditionals']) / 6, 0.25)
        smell_score += min(len(ast_metrics['uninformative_identifiers']) / 8, 0.2)
        if longest_line > extreme_line_threshold:
            smell_score += 0.15
        smell_score = min(1.0, smell_score)

        smell_score = min(1.0, smell_score + min(ast_metrics['max_nesting_depth'] / 20, 0.2))

        minified_candidate = (
            longest_line >= 400
            or (line_count <= 5 and longest_line >= 200)
            or (line_count == 1 and longest_line >= 150)
        )
        if minified_candidate and 'Potentially minified or generated asset' not in smell_flags:
            smell_flags.append('Potentially minified or generated asset')
            smell_score = min(1.0, smell_score + 0.35)

        samples = {
            'long_lines': long_lines[:10],
            'long_functions': long_functions[:5],
            'high_complexity_blocks': high_complexity_blocks[:5],
            'deeply_nested_functions': ast_metrics['deeply_nested_functions'][:5],
            'long_parameter_functions': ast_metrics['long_parameter_functions'][:5],
            'complex_conditionals': ast_metrics['complex_conditionals'][:10],
            'uninformative_identifiers': ast_metrics['uninformative_identifiers'][:10],
        }

        return {
            'smell_score': smell_score,
            'smell_flags': smell_flags,
            'samples': samples,
            'longest_line': longest_line,
            'long_line_count': len(long_lines),
            'long_function_count': len(long_functions),
            'high_complexity_blocks': high_complexity_blocks[:5],
            'max_nesting_depth': ast_metrics['max_nesting_depth'],
            'deeply_nested_functions': ast_metrics['deeply_nested_functions'],
            'long_parameter_functions': ast_metrics['long_parameter_functions'],
            'complex_conditionals': ast_metrics['complex_conditionals'],
            'uninformative_identifiers': ast_metrics['uninformative_identifiers'],
            'is_minified_candidate': minified_candidate,
        }

    def _analyze_ast_smells(self, source_code: str) -> Dict:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return {
                'max_nesting_depth': 0,
                'deeply_nested_functions': [],
                'long_parameter_functions': [],
                'complex_conditionals': [],
                'uninformative_identifiers': [],
            }

        control_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With)

        long_param_functions: List[Dict] = []
        deeply_nested_functions: List[Dict] = []
        complex_conditionals: List[Dict] = []
        uninformative_identifiers: List[Dict] = []
        max_nesting_depth = 0

        def count_params(func: ast.AST) -> int:
            args = func.args
            count = len(getattr(args, 'posonlyargs', [])) + len(args.args) + len(args.kwonlyargs)
            count += 1 if args.vararg else 0
            count += 1 if args.kwarg else 0
            return count

        def nesting_depth(node: ast.AST, depth: int = 0) -> int:
            current_max = depth
            for child in ast.iter_child_nodes(node):
                if isinstance(child, control_nodes):
                    child_depth = nesting_depth(child, depth + 1)
                else:
                    child_depth = nesting_depth(child, depth)
                if child_depth > current_max:
                    current_max = child_depth
            return current_max

        class ConditionalVisitor(ast.NodeVisitor):
            def visit_BoolOp(self, node: ast.BoolOp):
                if len(node.values) >= 3:
                    complex_conditionals.append({
                        'line': getattr(node, 'lineno', None),
                        'elements': len(node.values),
                        'text': ast.unparse(node) if hasattr(ast, 'unparse') else None,
                    })
                self.generic_visit(node)

        cond_visitor = ConditionalVisitor()
        cond_visitor.visit(tree)

        identifier_lengths: List[int] = []

        class IdentifierVisitor(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name):
                ident = node.id
                if ident and ident not in {'self', 'cls'}:
                    identifier_lengths.append(len(ident))
                    if len(ident) <= 2:
                        uninformative_identifiers.append({
                            'name': ident,
                            'line': getattr(node, 'lineno', None),
                        })
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef):
                identifier_lengths.append(len(node.name))
                if len(node.name) <= 2:
                    uninformative_identifiers.append({
                        'name': node.name,
                        'line': getattr(node, 'lineno', None),
                    })
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                identifier_lengths.append(len(node.name))
                if len(node.name) <= 2:
                    uninformative_identifiers.append({
                        'name': node.name,
                        'line': getattr(node, 'lineno', None),
                    })
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef):
                identifier_lengths.append(len(node.name))
                if len(node.name) <= 2:
                    uninformative_identifiers.append({
                        'name': node.name,
                        'line': getattr(node, 'lineno', None),
                    })
                self.generic_visit(node)

        IdentifierVisitor().visit(tree)

        for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            params = count_params(func)
            if params > 6:
                long_param_functions.append({
                    'name': func.name,
                    'parameters': params,
                    'line': getattr(func, 'lineno', None),
                })

            depth = nesting_depth(func)
            if depth > max_nesting_depth:
                max_nesting_depth = depth
            if depth >= 4:
                deeply_nested_functions.append({
                    'name': func.name,
                    'max_nesting': depth,
                    'line': getattr(func, 'lineno', None),
                })

        avg_identifier_length = (
            sum(identifier_lengths) / len(identifier_lengths)
            if identifier_lengths else None
        )
        if avg_identifier_length is not None and avg_identifier_length < 3:
            if not uninformative_identifiers:
                uninformative_identifiers.append({'name': '<avg_length>', 'line': None})

        return {
            'max_nesting_depth': max_nesting_depth,
            'deeply_nested_functions': deeply_nested_functions,
            'long_parameter_functions': long_param_functions,
            'complex_conditionals': complex_conditionals,
            'uninformative_identifiers': uninformative_identifiers,
        }

    def _detect_language(self, path: Path) -> str:
        suffixes = [s.lower() for s in path.suffixes]
        if not suffixes:
            return 'text'
        if suffixes[-1] == '.py' or '.py' in suffixes:
            return 'python'
        if suffixes[-1] == '.tsx':
            return 'tsx'
        if suffixes[-1] == '.ts':
            return 'typescript'
        if suffixes[-1] == '.jsx':
            return 'jsx'
        if suffixes[-1] == '.js':
            return 'javascript'
        if suffixes[-1] == '.map' and len(suffixes) > 1 and suffixes[-2] in {'.js', '.ts'}:
            return 'javascript-map'
        if suffixes[-1] == '.json':
            return 'json'
        if suffixes[-1] == '.css':
            return 'css'
        if suffixes[-1] == '.html':
            return 'html'
        if suffixes[-1] in {'.java', '.go', '.cpp', '.c'}:
            return suffixes[-1].lstrip('.')
        return suffixes[-1].lstrip('.')

    def _analyze_non_python(self, source_code: str, abs_path: Path, rel_path: str, language: str) -> Dict:
        lines = source_code.splitlines() or ['']
        loc = len(lines)
        non_empty = sum(1 for line in lines if line.strip())
        comment_markers = ('//', '/*', '*', '--', '#', '/*!', '//!', '<!--')
        comment_lines = sum(1 for line in lines if line.strip().startswith(comment_markers))
        comment_density = comment_lines / loc if loc else 0.0

        smell_info = self._detect_code_smells(source_code, [])
        longest_line = smell_info['longest_line']
        smell_flags = list(dict.fromkeys(smell_info['smell_flags']))
        smell_score = smell_info['smell_score']
        is_minified = smell_info.get('is_minified_candidate')

        if language in {'javascript-map', 'json'} and 'Minified bundle or generated artifact' not in smell_flags:
            smell_flags.append('Minified bundle or generated artifact')
            smell_score = min(1.0, smell_score + 0.25)

        estimated_maintainability = self._estimate_non_python_maintainability(loc, longest_line, bool(is_minified))

        return {
            'relative_path': rel_path,
            'absolute_path': str(abs_path),
            'language': language,
            'avg_complexity': 0.0,
            'max_complexity': 0.0,
            'maintainability_index': estimated_maintainability,
            'lines_of_code': loc,
            'logical_lines': non_empty,
            'comment_density': comment_density,
            'function_count': 0,
            'smell_score': smell_score,
            'smell_flags': smell_flags,
            'smell_samples': smell_info['samples'],
            'longest_line': longest_line,
            'long_line_count': smell_info['long_line_count'],
            'long_function_count': 0,
            'high_complexity_blocks': [],
            'max_nesting_depth': smell_info['max_nesting_depth'],
            'deeply_nested_functions': smell_info['deeply_nested_functions'],
            'long_parameter_functions': smell_info['long_parameter_functions'],
            'complex_conditionals': smell_info['complex_conditionals'],
            'uninformative_identifiers': smell_info['uninformative_identifiers'],
        }

    def _estimate_non_python_maintainability(self, loc: int, longest_line: int, minified: bool) -> float:
        base = 100.0
        base -= min(80.0, longest_line / 2)
        base -= min(30.0, loc / 5)
        if minified:
            base = min(base, 12.0)
        return max(5.0, base)
