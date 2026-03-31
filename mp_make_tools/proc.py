import subprocess


def run(cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    return int(proc.returncode)


def run_bash(command: str, *, cwd: str | None = None, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(['bash', '-lc', command], cwd=cwd, env=env)
    return int(proc.returncode)
