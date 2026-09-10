[35msrc/wysteria/reporting/github.py[m[36m-[m[32m23[m[36m-[mdef escape_github_data(value: str) -> str:
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m24[m[36m-[m    """Escape data / message values for GitHub workflow commands according to Actions spec."""
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m25[m[36m-[m    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m26[m[36m-[m
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m27[m[36m-[m
[35msrc/wysteria/reporting/github.py[m[36m:[m[32m28[m[36m:[m[1;31mdef normalize_file_path[m(path_str: str) -> str:
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m29[m[36m-[m    """Normalize file paths to forward-slash format for GitHub Actions."""
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m30[m[36m-[m    p = Path(path_str)
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m31[m[36m-[m    return p.as_posix()
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m32[m[36m-[m
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m33[m[36m-[m
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m34[m[36m-[mdef format_diagnostic_annotation(diag: Diagnostic | NormalizedDiagnostic) -> str:
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m35[m[36m-[m    """Format a single diagnostic as a GitHub Actions workflow command (::error or ::warning)."""
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m36[m[36m-[m    cmd = "error" if diag.severity == Severity.ERROR else "warning"
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m37[m[36m-[m    props: dict[str, str] = {}
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m38[m[36m-[m    if diag.location and diag.location.file and not diag.location.file.startswith("<"):
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m39[m[36m-[m        props["file"] = normalize_file_path(diag.location.file)
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m40[m[36m-[m        if diag.location.line > 0:
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m41[m[36m-[m            props["line"] = str(diag.location.line)
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m42[m[36m-[m        if diag.location.column > 0:
[35msrc/wysteria/reporting/github.py[m[36m-[m[32m43[m[36m-[m            props["col"] = str(diag.location.column)
