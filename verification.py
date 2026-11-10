"""Real local tool adapters. KLEE/LLVM run in Docker; CBMC and Z3 run on the Mac."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from time import perf_counter
import uuid

PROFILES = {
    "main": "Open C program - safety checks on main",
    "factorial": "Function contract - int factorial(int n), n = 0..12",
    "maximum": "Function contract - int maximum(int a, int b), inputs = -100..100",
}
IMAGE = "klee/klee:3.0"
TIMEOUT = 60
UNWIND_BOUND = 32

# CPROVER intrinsics remain declarations, never no-op implementations.
# These C99 prototypes also permit strict GCC/Clang syntax checking.
CBMC_DECLARATIONS = (
    "extern int gradeai_nondet_int(void);\n"
    "extern void __CPROVER_assume(_Bool assumption);\n"
    "extern void __CPROVER_assert(_Bool assertion, const char *description);\n"
)


def command(args, cwd=None, timeout=TIMEOUT):
    """Record genuine tool termination separately from a property verdict."""
    start = perf_counter()
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           errors="replace", timeout=timeout, check=False)
        return {"exit_code": p.returncode, "timed_out": False,
                "log": (p.stdout + "\n" + p.stderr)[-160000:],
                "elapsed_ms": round((perf_counter() - start) * 1000, 2)}
    except subprocess.TimeoutExpired as exc:
        def decoded(v):
            return v.decode(errors="replace") if isinstance(v, bytes) else (v or "")
        return {"exit_code": None, "timed_out": True,
                "log": (decoded(exc.stdout) + decoded(exc.stderr))[-160000:],
                "elapsed_ms": round((perf_counter() - start) * 1000, 2)}
    except OSError as exc:
        return {"exit_code": None, "timed_out": False, "log": str(exc),
                "elapsed_ms": round((perf_counter() - start) * 1000, 2)}


def tool_health():
    health = {name: bool(shutil.which(name)) for name in ("gcc", "cppcheck", "cbmc", "z3", "docker")}
    health["docker_engine"] = False
    health["klee_image"] = False
    if health["docker"]:
        health["docker_engine"] = command(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)["exit_code"] == 0
        if health["docker_engine"]:
            health["klee_image"] = command(["docker", "image", "inspect", IMAGE], timeout=10)["exit_code"] == 0
    return health


def scanf_formats(source):
    """Read literal scanf formats, ignoring comments and unrelated strings."""
    pattern = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|\bscanf\s*\('
    formats = []
    for token in re.finditer(pattern, source, re.S):
        if not token.group().startswith("scanf"):
            continue
        literal = re.match(r'\s*"((?:\\.|[^"\\])*)"\s*,', source[token.end():])
        if not literal:
            return None
        # Only whitespace escape sequences are meaningful in this subset.
        fmt = literal.group(1)
        for escaped, value in [(r"\t", "\t"), (r"\n", "\n"), (r"\r", "\r"),
                               (r"\v", "\v"), (r"\f", "\f")]:
            fmt = fmt.replace(escaped, value)
        if "\\" in fmt or not re.fullmatch(r'\s*%(?:d|[1-9][0-9]*s)(?:\s+%(?:d|[1-9][0-9]*s))*\s*', fmt):
            return None
        conversions = re.findall(r'%(d|[1-9][0-9]*s)', fmt)
        if len(conversions) > 8 or any(c != "d" and int(c[:-1]) > 256 for c in conversions):
            return None
        if fmt not in formats:
            formats.append(fmt)
    return formats


def main_io_model(source):
    formats = scanf_formats(source)
    if formats is None:
        return "unsupported"
    if not formats:
        return "symbolic_bytes"
    return "bounded_tokens" if any(re.search(r'%[0-9]+s', f) for f in formats) else "integer_tokens"


def input_scope(model):
    if model in ("integer_tokens", "bounded_tokens"):
        return ("Token-level scanf abstraction: signed int %d and bounded %Ns strings (width 1..256); "
                "multiple whitespace-separated conversions and partial assignment counts are modelled. "
                "Strings contain non-NUL, non-whitespace bytes and a terminator. Calls are independent: "
                "raw text parsing, stream persistence, locale and printf output are not verified. "
                "Findings require review or replay against real input.")
    if model == "unsupported":
        return ("Unsupported scanf format: use literal %d or width-limited %Ns conversions separated "
                "by whitespace (up to 8 conversions, string width <=256), or supply a trusted harness. "
                "LLVM generation can still run; input-dependent symbolic and CBMC checks remain blocked.")
    return "Original main with the recorded symbolic stdin/library scope."


def harness(profile, backend, source=""):
    if profile == "main":
        if main_io_model(source) not in ("integer_tokens", "bounded_tokens"):
            return '#include "submission.c"\n'
        formats = scanf_formats(source)
        if backend == "klee":
            declarations = '#include <klee/klee.h>\n'
            choice = lambda name: f'klee_make_symbolic(&{name}, sizeof({name}), "{name}");'
            assume = lambda expr: f"klee_assume({expr});"
        else:
            declarations = CBMC_DECLARATIONS
            choice = lambda name: f"{name} = gradeai_nondet_int();"
            assume = lambda expr: f"__CPROVER_assume({expr});"
        cases = []
        for fmt in formats:
            conversions = re.findall(r'%(d|[1-9][0-9]*s)', fmt)
            escaped = json.dumps(fmt)
            lines = [f"if (strcmp(format, {escaped}) == 0) {{", "int status;", choice("status"),
                     assume("status >= -1"), assume(f"status <= {len(conversions)}"),
                     "va_list args;", "va_start(args, format);"]
            for i, conversion in enumerate(conversions):
                # Do not even fetch a destination argument for an unsuccessful conversion.
                lines.append(f"if (status > {i}) {{")
                if conversion == "d":
                    lines += ["int value;", choice("value"), "int *target = va_arg(args, int *);",
                              "*target = value;"]
                else:
                    width = int(conversion[:-1])
                    lines += ["int length;", choice("length"), assume("length >= 1"),
                              assume(f"length <= {width}"), "char *target = va_arg(args, char *);",
                              "for (int i = 0; i < length; ++i) {", "unsigned char byte;", choice("byte"),
                              assume("byte != 0"), assume("byte != 32"),
                              assume("(byte < 9) | (byte > 13)"), "target[i] = (char)byte;", "}",
                              "target[length] = 0;"]
                lines.append("}")
            lines += ["va_end(args);", "return status;", "}"]
            cases.append("\n".join(lines))
        return declarations + """#include <stdio.h>
#include <stdarg.h>
#include <string.h>
int gradeai_scanf(const char *format, ...);
int gradeai_printf(const char *format, ...);
#define scanf gradeai_scanf
#define printf gradeai_printf
#include "submission.c"
#undef scanf
#undef printf
int gradeai_scanf(const char *format, ...)
{
""" + "\n".join(cases) + """
    /* No literal-format case should be missing after adapter validation. */
""" + assume("0") + """
    return -1;
}
int gradeai_printf(const char *format, ...)
{
    (void)format;
    int print_result;
""" + choice("print_result") + """
    return print_result;
}
"""

    include = '#define main gradeai_student_main\n#include "submission.c"\n#undef main\n'
    if backend == "klee":
        declarations = '#include <klee/klee.h>\n'
        symbol = lambda n: f'klee_make_symbolic(&{n}, sizeof({n}), "{n}");'
        assume = lambda s: f"klee_assume({s});"
        check = lambda s: f"klee_assert({s});"
    else:
        declarations = CBMC_DECLARATIONS
        symbol = lambda n: f"{n} = gradeai_nondet_int();"
        assume = lambda s: f"__CPROVER_assume({s});"
        check = lambda s: f'__CPROVER_assert({s}, "assignment function contract");'
    if profile == "factorial":
        body = ["int n;", symbol("n"), assume("n >= 0"), assume("n <= 12"),
                "int expected = 1;", "for (int i = 1; i <= n; ++i) expected *= i;",
                check("factorial(n) == expected")]
    elif profile == "maximum":
        body = ["int a, b;", symbol("a"), symbol("b")]
        body += [assume(s) for s in ["a >= -100", "a <= 100", "b >= -100", "b <= 100"]]
        body += [check("maximum(a, b) == (a > b ? a : b)")]
    else:
        raise ValueError("Unknown assignment profile.")
    return declarations + include + "\nint main(void) {\n" + "\n".join(body) + "\nreturn 0;\n}\n"


def read_text(path, limit=160000):
    return path.read_text(errors="replace")[:limit] if path.is_file() else ""


def stage(key, status, result, steps=None, outputs=None, raw=None):
    return {"key": key, "status": status, "result": result, "steps": steps or [],
            "outputs": outputs or [], "raw_evidence": raw or [],
            "evidence_ids": ["TOOL-" + key.upper()],
            "inputs": [], "improvements": []}


def classify_klee(log, errors, done):
    if re.search(r"undefined reference to function:|calling external: (?:__isoc99_|__isoc23_)?scanf\b|external call with symbolic argument", log):
        return "INCONCLUSIVE", (
            "Unmodelled external calls or concretisation warnings limit the input analysis. "
            "A completed path count does not establish the intended coverage.")
    if errors:
        confirmed = any(re.search(r"\.(assert|ptr|div|overflow|free|readonly|overshift|abort)\.err\b", e)
                        for e in errors)
        if confirmed:
            return "VIOLATED", "KLEE generated a failed assertion or safety error. Inspect the recorded traces."
        return "INCONCLUSIVE", "KLEE generated execution/model error artifacts; these do not establish a submission defect."
    partial = re.search(r"partially completed paths\s*=\s*(\d+)", log)
    if done and "KLEE: done:" in log and partial and int(partial.group(1)) == 0:
        return "COMPLETED", "No KLEE error found in completed exploration under the recorded harness and limits."
    return "INCONCLUSIVE", "KLEE did not establish completed error-free exploration; inspect limits and diagnostics."


def classify_cbmc(run):
    if run["timed_out"]:
        return "INCONCLUSIVE", "CBMC reached its wall-time budget."
    log = run["log"]
    if run["exit_code"] == 0 and "VERIFICATION SUCCESSFUL" in log:
        return "COMPLETED", "CBMC verified the harness assertions and enabled safety checks within the stated scope."
    if "VERIFICATION FAILED" in log:
        if any("unwinding assertion" in line.lower() and
               ("FAILURE" in line or "FAILED" in line) for line in log.splitlines()):
            return "REVIEW REQUIRED", "CBMC reported a failed check including an unwinding assertion. Inspect individual properties."
        return "VIOLATED", "CBMC found a failed assertion or safety property. Inspect the counterexample trace."
    return "INCONCLUSIVE", "CBMC did not return a recognized completed verification result."


def execute(source, profile):
    if profile not in PROFILES:
        raise ValueError("Select a supported assignment profile.")
    records, artifacts = {}, {}
    with tempfile.TemporaryDirectory(prefix="gradeai-tools-") as temporary:
        root = Path(temporary)
        inputs, outputs = root / "inputs", root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        outputs.chmod(0o777)  # Private parent; permit the non-root KLEE container to write its mount.
        (inputs / "submission.c").write_text(source)
        input_model = main_io_model(source) if profile == "main" else "function_contract"
        artifacts["input_model"] = input_model
        (inputs / "klee_harness.c").write_text(harness(profile, "klee", source))
        (inputs / "cbmc_harness.c").write_text(harness(profile, "cbmc", source))
        artifacts["klee_harness.c"] = read_text(inputs / "klee_harness.c")
        artifacts["cbmc_harness.c"] = read_text(inputs / "cbmc_harness.c")
        if not shutil.which("docker"):
            records["llvm"] = stage("llvm", "UNAVAILABLE", "Docker CLI is missing. Run the Mac installer.")
            records["symbolic"] = stage("symbolic", "BLOCKED", "The Docker KLEE worker is unavailable.")
        else:
            name = "gradeai-klee-" + uuid.uuid4().hex[:16]
            # Commands and paths are fixed. Student text is written only to a mounted source file.
            script = """
set +e
clang --version > /out/llvm-version.txt 2>&1
klee --version > /out/klee-version.txt 2>&1
clang -I /home/klee/klee_src/include -I /tmp/klee_src/include -I /in -g -O0 -Xclang -disable-O0-optnone -emit-llvm -c /in/klee_harness.c -o /out/program.bc > /out/llvm.log 2>&1
compile_exit=$?
printf '%s' "$compile_exit" > /out/compile.exit
if [ "$compile_exit" -ne 0 ]; then exit 0; fi
llvm-dis /out/program.bc -o /out/program.ll >> /out/llvm.log 2>&1
"""
            if input_model == "unsupported":
                script += "printf '%s' 'Unsupported input model; symbolic execution skipped.' > /out/klee.log\n"
            elif profile == "main" and input_model == "symbolic_bytes":
                script += """
klee --max-time=45s --max-memory=1024 --write-smt2s --libc=uclibc --posix-runtime --output-dir=/out/klee-output /out/program.bc --sym-stdin 8 > /out/klee.log 2>&1
"""
            else:
                script += """
klee --max-time=45s --max-memory=1024 --write-smt2s --output-dir=/out/klee-output /out/program.bc > /out/klee.log 2>&1
"""
            script += """
printf '%s' "$?" > /out/klee.exit
for test in /out/klee-output/*.ktest; do
 [ -f "$test" ] || continue
 ktest-tool "$test" >> /out/counterexamples.log 2>&1
done
"""
            args = ["docker", "run", "--rm", "--name", name, "--platform", "linux/amd64",
                    "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--pids-limit", "256", "--memory", "2g", "--cpus", "2", "--ulimit", "stack=-1:-1",
                    "-v", f"{inputs}:/in:ro", "-v", f"{outputs}:/out", "-w", "/out",
                    IMAGE, "bash", "-lc", script]
            worker = command(args, timeout=90)
            if worker["timed_out"]:
                command(["docker", "rm", "-f", name], timeout=10)
            llvm_log = read_text(outputs / "llvm.log")
            ir = read_text(outputs / "program.ll")
            artifacts["program.ll"] = ir
            artifacts["llvm_version"] = read_text(outputs / "llvm-version.txt")
            artifacts["klee_version"] = read_text(outputs / "klee-version.txt")
            if ir:
                functions = re.findall(r"^define\s+.*?@([^ (]+)", ir, re.M)
                branches = len(re.findall(r"^\s*br\s", ir, re.M))
                records["llvm"] = stage("llvm", "COMPLETED",
                    "Actual LLVM bitcode and textual IR generated by the KLEE-compatible Clang toolchain.",
                    ["Compile the selected harness with Clang.", "Disassemble LLVM bitcode.",
                     "Count IR function definitions and branch instructions."],
                    [f"IR function definitions: {', '.join(functions)}", f"IR branch instructions: {branches}",
                     "Full CFG and def-use graph extraction are not implemented."],
                    [artifacts["llvm_version"], llvm_log, ir[:12000]])
            else:
                records["llvm"] = stage("llvm", "INCONCLUSIVE", "LLVM generation failed or worker was unavailable.",
                                        raw=[worker["log"], llvm_log])
            klee_log = read_text(outputs / "klee.log")
            error_files = sorted((outputs / "klee-output").glob("*.err"))
            errors = [f"{f.name}\n{read_text(f)}" for f in error_files]
            status, message = classify_klee(klee_log, errors, read_text(outputs / "klee.exit").strip() == "0")
            if input_model == "unsupported":
                status, message = "BLOCKED", input_scope(input_model)
            elif not ir:
                status, message = "BLOCKED", "KLEE requires successfully compiled LLVM bitcode."
            records["symbolic"] = stage("symbolic", status, message,
                ["Run KLEE with a 45-second internal and 90-second worker deadline.",
                 "Retain error files, generated test inputs and solver queries."],
                [f"Error artifacts: {len(errors)}", "Scope: " + PROFILES[profile]],
                [klee_log, *errors, read_text(outputs / "counterexamples.log")])
            artifacts["klee.log"] = klee_log
            artifacts["klee_errors"] = errors
            artifacts["klee_test_inputs"] = read_text(outputs / "counterexamples.log")

        # Z3 replays queries generated from THIS submission's KLEE paths.
        queries = sorted((outputs / "klee-output").glob("*.smt2"))
        query_results = []
        if not shutil.which("z3"):
            records["smt"] = stage("smt", "UNAVAILABLE", "Z3 executable is missing. Install z3 with Homebrew.")
        elif not queries:
            records["smt"] = stage("smt", "BLOCKED", "KLEE produced no replayable SMT-LIB queries for this run. " + (input_scope(input_model) if input_model == "unsupported" else "Inspect the LLVM and symbolic execution outcomes."))
        else:
            for path in queries[:12]:
                run = command(["z3", "-T:4", "-smt2", str(path)], timeout=6)
                query_results.append({"file": path.name, "query": read_text(path), **run})
            all_decided = all(r["exit_code"] == 0 and re.search(r"(?m)^(sat|unsat)$", r["log"])
                              for r in query_results)
            records["smt"] = stage("smt", "COMPLETED" if all_decided else "INCONCLUSIVE",
                "Replayed KLEE-generated path queries. SAT describes query satisfiability, not a grading verdict.",
                ["Read KLEE SMT-LIB artifacts.", "Run Z3 on up to 12 queries with a per-query time limit."],
                [f"Queries replayed: {len(query_results)} of {len(queries)} generated.",
                 "Replay is a query audit and does not prove whole-program correctness."],
                [r["file"] + "\n" + r["log"] for r in query_results])
        artifacts["z3_queries"] = query_results
        if input_model == "unsupported":
            records["verification"] = stage("verification", "BLOCKED", input_scope(input_model),
                steps=["Inspect literal scanf formats before choosing an input harness."],
                outputs=["LLVM compilation is independent of this input-model limitation."])
        elif not shutil.which("cbmc"):
            records["verification"] = stage("verification", "UNAVAILABLE", "CBMC executable is missing. Install cbmc with Homebrew.")
        else:
            formats = scanf_formats(source) if profile == "main" else []
            string_widths = [int(x) for fmt in (formats or []) for x in re.findall(r'%([0-9]+)s', fmt)]
            unwind_bound = max([UNWIND_BOUND] + [width + 1 for width in string_widths])
            args = ["cbmc", str(inputs / "cbmc_harness.c"), "--function", "main",
                    "--unwind", str(unwind_bound), "--unwinding-assertions", "--signed-overflow-check",
                    "--bounds-check", "--pointer-check", "--div-by-zero-check", "--trace"]
            run = command(args, cwd=str(inputs), timeout=60)
            status, message = classify_cbmc(run)
            records["verification"] = stage("verification", status, message,
                ["Run CBMC on the original C submission and selected trusted harness.",
                 "Enable memory bounds, pointer, division and signed-overflow checks.",
                 f"Retain unwinding assertions at bound {unwind_bound}; an exhausted bound requires review."],
                ["Scope: " + PROFILES[profile], f"Unwind bound: {unwind_bound}; wall-time limit: 60 seconds."],
                [run["log"]])
            failed_properties = [line.strip() for line in run["log"].splitlines()
                                 if line.lstrip().startswith("[") and "FAILURE" in line]
            records["verification"]["outputs"].extend(failed_properties[:30])
            records["verification"]["outputs"].append("Tool process exit: " + str(run["exit_code"]))
            artifacts["cbmc.log"] = run["log"]
        for record in records.values():
            record["outputs"].append("Input model: " + input_model)
            record["outputs"].append(input_scope(input_model))
            record["inputs"] = ["Submitted C source.", "Assignment profile: " + PROFILES[profile]]
        return records, artifacts
