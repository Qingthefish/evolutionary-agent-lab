"""Restricted Git operations on explicitly trusted repositories.

Commands use argument arrays (never a shell), a minimal environment without
inherited credentials, disabled hooks/fsmonitor/credential helpers, ignored
system/global configuration, and an allowlist for repository-local
configuration. Output and time are bounded. Pushes are fast-forward only and
are executed solely through the trusted approval-release path in the gateway;
this module never decides that a push is authorized. Untrusted repository
content is data: attributes, filters, textconv, and external diff drivers are
disabled or rejected.
"""

from dataclasses import asdict, dataclass, field
import base64
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from uuid import uuid4
from urllib.parse import urlsplit

from .core import WorkflowError
from .protocol import strict_json


class GitToolError(WorkflowError):
    """Rejected, failed, or uncertain Git operation with a program-authored reason."""


class GitUncertainError(GitToolError):
    """An external effect may or may not have happened; reconcile, never retry."""


_BRANCH = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)(?!.*@\{)(?!.*\.lock$)(?!/)(?!.*/$)[A-Za-z0-9._/-]{1,100}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DENIED_NAMES = re.compile(
    r"(^|/)(\.env(\..*)?|\.netrc|\.git-credentials|\.npmrc|\.pypirc|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|"
    r"credentials(\.json)?|secrets?(\..*)?)$|\.(pem|key|p12|pfx|sqlite3?|db)$", re.I)
_SECRET_CONTENT = re.compile(
    rb"(-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    rb"|\bsk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|(api[_-]?key|password|secret)\s*[:=]\s*\S{8,})", re.I)
# Repository-local configuration keys that cannot run programs or redirect I/O.
_LOCAL_CONFIG = [re.compile(p) for p in (
    r"core\.(repositoryformatversion|filemode|logallrefupdates|ignorecase|precomposeunicode|symlinks)",
    r"core\.bare", r"extensions\.objectformat", r"init\.defaultbranch",
    r"remote\.[A-Za-z0-9._-]+\.(url|fetch)", r"branch\.[A-Za-z0-9._/-]+\.(remote|merge)",
    r"user\.(name|email)", r"receive\.(denynonfastforwards|denydeletes)")]
_SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "core.pager=cat",
         "-c", "credential.helper=", "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false",
         "-c", "core.attributesFile=/dev/null", "-c", "core.excludesFile=/dev/null",
         "-c", "diff.noprefix=false", "-c", "color.ui=false", "-c", "advice.detachedHead=false",
         "-c", "protocol.allow=never", "-c", "protocol.file.allow=always", "--literal-pathspecs"]


def _run(argv, env, *, seconds, output_bytes, cwd=None):
    """Bounded subprocess without a shell. Returns (code, stdout, stderr, interrupted)."""
    started = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    interrupted = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   close_fds=True, start_new_session=True, env=env, cwd=cwd)
    except OSError:
        raise GitToolError("Git executable could not start") from None
    try:
        with selectors.DefaultSelector() as selector:
            for name in ("stdout", "stderr"):
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() and not interrupted:
                if time.monotonic() - started >= seconds:
                    interrupted = "timeout"
                    break
                for key, _ in selector.select(timeout=0.05):
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    room = output_bytes - len(buffers[key.data])
                    buffers[key.data].extend(chunk[:max(room, 0)])
                    if len(chunk) > room:
                        interrupted = "output_limit"
                        break
            while not interrupted and process.poll() is None:
                if time.monotonic() - started >= seconds:
                    interrupted = "timeout"
                else:
                    time.sleep(0.01)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    return process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]), interrupted


@dataclass(frozen=True)
class TrustedRepository:
    """Trusted setup only. Never constructed from model-controlled arguments."""
    name: str
    path: str
    writable_branches: tuple
    writable_paths: tuple
    remotes: tuple = ()          # ((name, url), ...)
    allow_network: bool = False  # HTTPS remotes stay disabled until credentials are provisioned
    committer: tuple = ("Agent Lab", "agent-lab@localhost.invalid")
    credential_env: str | None = None

    def __post_init__(self):
        if type(self.allow_network) is not bool:
            raise GitToolError("Network permission must be an explicit boolean")
        if self.credential_env is not None and (not self.allow_network or not isinstance(self.credential_env, str)
                                                or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}',self.credential_env) is None):
            raise GitToolError("Credential access requires explicit network permission and one named environment variable")
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise GitToolError("Repository names are short identifiers")
        if not isinstance(self.path, str) or not os.path.isabs(self.path):
            raise GitToolError("Configure an absolute repository path")
        if (not isinstance(self.writable_branches, tuple) or not self.writable_branches
                or any(not isinstance(b, str) or not _BRANCH.fullmatch(b) for b in self.writable_branches)):
            raise GitToolError("Configure explicit writable branch names")
        if (not isinstance(self.writable_paths, tuple) or not self.writable_paths
                or any(not isinstance(p, str) or not p.endswith("/") or p.startswith("/") or ".." in p.split("/")
                       for p in self.writable_paths)):
            raise GitToolError("Writable paths are explicit relative directory prefixes ending in '/'")
        for remote, url in self.remotes:
            if not _NAME.fullmatch(remote) or not isinstance(url, str):
                raise GitToolError("Remotes are (name, url) pairs")
            if not (url.startswith("/") or (self.allow_network and url.startswith("https://"))):
                raise GitToolError("Only local bare-repository remotes are enabled; HTTPS needs explicit network approval")
            if url.startswith('https://'):
                parsed=urlsplit(url)
                if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):
                    raise GitToolError("HTTPS repository URLs cannot contain credentials, query strings or custom ports")
                if self.credential_env and (parsed.hostname!='github.com' or re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?',parsed.path) is None):
                    raise GitToolError("Credential forwarding is limited to an explicit github.com repository URL")

    def remote_url(self, remote):
        for name, url in self.remotes:
            if name == remote:
                return url
        raise GitToolError("Remote is not configured for this trusted repository")


def load_trusted_repositories(path):
    """Read trusted repositories from a JSON file chosen by the operator."""
    text=Path(path).read_text(encoding="utf-8")
    if len(text)>1024*1024:raise GitToolError('Trusted repository configuration exceeds its size limit')
    data = strict_json(text)
    if (not isinstance(data,dict) or set(data)!={'repositories'} or not isinstance(data['repositories'],list)
            or len(data['repositories'])>20):
        raise GitToolError('Supply a repositories array with at most 20 trusted entries')
    result = []
    for item in data.get("repositories", []):
        if (not isinstance(item,dict) or not {'name','path','writable_branches','writable_paths'}<=item.keys()
                or not item.keys()<={'name','path','writable_branches','writable_paths','remotes','allow_network','credential_env'}
                or not isinstance(item.get('remotes',{}),dict)
                or not isinstance(item['writable_branches'],list) or not isinstance(item['writable_paths'],list)):
            raise GitToolError('Malformed trusted repository entry; literal credentials are not accepted')
        result.append(TrustedRepository(
            name=item["name"], path=item["path"], writable_branches=tuple(item["writable_branches"]),
            writable_paths=tuple(item["writable_paths"]),
            remotes=tuple((name, url) for name, url in item.get("remotes", {}).items()),
            allow_network=item.get("allow_network", False), credential_env=item.get('credential_env')))
    return result


class GitTools:
    def __init__(self, workflow, repositories, *, git_binary=None, timeout=20, output_bytes=256 * 1024,
                 max_file_bytes=1024 * 1024):
        self.workflow = workflow
        self.repositories = {}
        self._credentials = {}
        for repository in repositories:
            if not isinstance(repository, TrustedRepository) or repository.name in self.repositories:
                raise GitToolError("Configure distinct TrustedRepository records")
            self.repositories[repository.name] = repository
            if repository.credential_env:
                token=os.environ.get(repository.credential_env)
                if not token or any(c.isspace() for c in token):
                    raise GitToolError("Configured runtime GitHub credential variable is missing or invalid")
                self._credentials[repository.name]=token
        binary = git_binary or shutil.which("git", path="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin")
        if not binary or not os.path.isabs(binary):
            raise GitToolError("No absolute Git executable is available")
        self.binary, self.timeout, self.output_bytes = binary, timeout, output_bytes
        self.max_file_bytes = max_file_bytes
        self._home = tempfile.mkdtemp(prefix="agent-lab-git-home-")  # Empty: no user config or credentials.
        workflow.db.executescript("""
            CREATE TABLE IF NOT EXISTS git_repositories (
                name TEXT PRIMARY KEY, path TEXT NOT NULL, device INTEGER NOT NULL, inode INTEGER NOT NULL,
                root_commit TEXT
            );
            CREATE TABLE IF NOT EXISTS git_operations (
                id TEXT PRIMARY KEY, repository TEXT NOT NULL, task TEXT REFERENCES tasks(id), actor TEXT NOT NULL,
                operation TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
                started REAL NOT NULL, ended REAL
            );
        """)

    def close(self):
        shutil.rmtree(self._home, ignore_errors=True)

    def configuration(self):
        records={name:asdict(repo) for name,repo in sorted(self.repositories.items())}
        for record in records.values():
            if record['credential_env'] is None:record.pop('credential_env')  # Preserve existing task configurations.
        return {"repositories": records,
                "git": "restricted-cli-v1"}

    # ---- process boundary ----------------------------------------------------
    def _env(self):
        return {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": self._home,
                "LC_ALL": "C", "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/usr/bin/false", "SSH_ASKPASS": "/usr/bin/false",
                "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_LITERAL_PATHSPECS": "1"}

    def _git(self, repository, arguments, *, seconds=None, check=True, env=None):
        argv = [self.binary, "--git-dir", os.path.join(repository.path, ".git"), "--work-tree", repository.path,
                *_SAFE, *arguments]
        code, out, err, interrupted = self._exec(argv, {**self._env(), **(env or {})}, seconds or self.timeout)
        if interrupted == "output_limit":
            return code, out, err, interrupted
        if interrupted:
            raise GitToolError(f"Git command interrupted ({interrupted})")
        if check and code != 0:
            raise GitToolError("Git command failed: " + err.decode("utf-8", "replace").strip()[:300])
        return code, out, err, None

    def _remote_git(self, arguments, *, seconds=None):
        url=next((a for a in arguments if isinstance(a,str) and a.startswith('https://')),None)
        extra,env=self._remote_access(url)
        argv = [self.binary, *_SAFE, *extra, *arguments]
        return self._exec(argv, env, seconds or self.timeout)

    def _remote_access(self,url):
        env=self._env()
        if not url or not url.startswith('https://'):return [],env
        repositories=[r for r in self.repositories.values() if r.allow_network and any(u==url for _,u in r.remotes)]
        if len(repositories)!=1:raise GitToolError('HTTPS target is not one uniquely configured trusted remote')
        repo=repositories[0]
        if repo.credential_env:
            encoded=base64.b64encode(('x-access-token:'+self._credentials[repo.name]).encode()).decode()
            env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='http.'+url+'.extraHeader',
                       GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+encoded)
        return ['-c','protocol.https.allow=always','-c','http.followRedirects=false'],env

    def _exec(self, argv, env, seconds):
        code,out,err,interrupted=_run(argv, env, seconds=seconds, output_bytes=self.output_bytes)
        for token in self._credentials.values():
            for secret in (token.encode(),base64.b64encode(('x-access-token:'+token).encode())):
                out=out.replace(secret,b'[redacted]');err=err.replace(secret,b'[redacted]')
        return code,out,err,interrupted

    # ---- trust checks ----------------------------------------------------------
    def _owned_directory(self, path, description):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            raise GitToolError(f"{description} does not exist") from None
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise GitToolError(f"{description} must be a real directory owned by the current user")
        return info

    def _check_config(self, config_path, *, bare):
        if not os.path.exists(config_path):
            return
        code, out, _, interrupted = self._exec(
            [self.binary, *_SAFE, "config", "--file", config_path, "--no-includes", "--null", "--list"], self._env(), 10)
        if code != 0 or interrupted:
            raise GitToolError("Repository configuration could not be parsed safely")
        for entry in out.decode("utf-8", "replace").split("\0"):
            if not entry:
                continue
            key, _, value = entry.partition("\n")
            key = key.lower()
            if not any(p.fullmatch(key) for p in _LOCAL_CONFIG):
                raise GitToolError(f"Repository configuration key '{key}' is not allowed")
            if key == "core.bare" and value.lower() != ("true" if bare else "false"):
                raise GitToolError("Unexpected bare/non-bare repository layout")

    def _check_git_dir(self, git_dir, *, bare):
        self._owned_directory(git_dir, "Git directory")
        for relative in ("objects/info/alternates", "objects/info/http-alternates", "commondir"):
            if os.path.lexists(os.path.join(git_dir, relative)):
                raise GitToolError("Repositories with alternates or shared object directories are not trusted")
        self._check_config(os.path.join(git_dir, "config"), bare=bare)

    def repository(self, name):
        """Validate a trusted repository's identity and configuration before every use."""
        repository = self.repositories.get(name)
        if repository is None:
            raise GitToolError("Repository is not in the trusted allowlist")
        if os.path.realpath(repository.path) != repository.path:
            raise GitToolError("Trusted repository path must be canonical (no symlinks)")
        self._owned_directory(repository.path, "Repository")
        git_dir = os.path.join(repository.path, ".git")
        info = os.lstat(git_dir) if os.path.lexists(git_dir) else None
        if info is None or not stat.S_ISDIR(info.st_mode):
            raise GitToolError("Repository must have a real .git directory (no gitfile indirection)")
        self._check_git_dir(git_dir, bare=False)
        code, out, _, _ = self._git(repository, ["rev-list", "--max-parents=0", "HEAD"], check=False)
        root = out.decode().split()[-1] if code == 0 and out.strip() else None
        with self.workflow._transaction():
            bound = self.workflow.db.execute("SELECT * FROM git_repositories WHERE name=?", (name,)).fetchone()
            if bound is None:
                self.workflow.db.execute("INSERT INTO git_repositories VALUES(?,?,?,?,?)",
                                         (name, repository.path, info.st_dev, info.st_ino, root))
            elif (bound["path"], bound["device"], bound["inode"]) != (repository.path, info.st_dev, info.st_ino) \
                    or (bound["root_commit"] and bound["root_commit"] != root):
                raise GitToolError("Repository identity changed since it was first trusted; reconcile manually")
            elif bound["root_commit"] is None and root is not None:
                self.workflow.db.execute("UPDATE git_repositories SET root_commit=? WHERE name=?", (root, name))
        return repository

    def _remote(self, repository, remote):
        url = repository.remote_url(remote)
        if url.startswith("/"):
            if os.path.realpath(url) != url:
                raise GitToolError("Local remote path must be canonical")
            self._check_git_dir(url, bare=True)
        return url

    @staticmethod
    def _branch(branch):
        if not isinstance(branch, str) or not _BRANCH.fullmatch(branch):
            raise GitToolError("Invalid branch name")
        return branch

    def _writable_branch(self, repository, branch):
        self._branch(branch)
        if branch not in repository.writable_branches:
            raise GitToolError(f"Branch '{branch}' is not in this repository's writable allowlist")
        return branch

    def _path(self, repository, path):
        if (not isinstance(path, str) or not path or path.startswith(("/", "-", ":")) or "\\" in path
                or "\0" in path or any(p in {"", ".", ".."} for p in path.split("/"))):
            raise GitToolError("Use a relative POSIX path without traversal")
        if path.split("/")[0].lower() == ".git" or "/.git/" in "/" + path.lower() + "/":
            raise GitToolError("Paths inside .git are never writable")
        if not any(path.startswith(prefix) for prefix in repository.writable_paths):
            raise GitToolError(f"Path '{path}' is outside the authorized writable paths")
        if _DENIED_NAMES.search(path):
            raise GitToolError(f"Path '{path}' looks like a credential or private data file")
        return path

    # ---- evidence ----------------------------------------------------------------
    def _record(self, repository, operation, arguments, *, actor, task):
        identifier = uuid4().hex
        with self.workflow._transaction():
            self.workflow.db.execute(
                "INSERT INTO git_operations VALUES(?,?,?,?,?,?, 'started', NULL, ?, NULL)",
                (identifier, repository, task, actor, operation, json.dumps(arguments, sort_keys=True), self.workflow.clock()))
        return identifier

    def _settle(self, identifier, status, result, *, task=None, actor=None, event=None):
        with self.workflow._transaction():
            self.workflow.db.execute("UPDATE git_operations SET status=?,result=?,ended=? WHERE id=?",
                                     (status, json.dumps(result, sort_keys=True), self.workflow.clock(), identifier))
            if task is not None and event is not None:
                self.workflow._event(task, actor, event, {"operation_id": identifier, **result})

    def operations(self, *, limit=100):
        return [dict(row) | {"arguments": json.loads(row["arguments"]),
                             "result": json.loads(row["result"]) if row["result"] else None}
                for row in self.workflow.db.execute(
                    "SELECT * FROM git_operations ORDER BY started DESC LIMIT ?", (limit,))]

    # ---- read-only operations ------------------------------------------------------
    def status(self, name):
        repository = self.repository(name)
        _, out, _, _ = self._git(repository, ["status", "--porcelain=v2", "--branch", "--untracked-files=all",
                                              "--ignore-submodules=all", "-z"])
        result = {"repository": name, "branch": None, "head": None, "upstream": None, "entries": [],
                  "writable_branches": list(repository.writable_branches),
                  "writable_paths": list(repository.writable_paths),
                  "remotes": [name for name, _ in repository.remotes]}
        records = out.decode("utf-8", "replace").split("\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if record.startswith("# branch.head "):
                head = record.split(" ", 2)[2]
                result["branch"] = None if head == "(detached)" else head
            elif record.startswith("# branch.oid "):
                oid = record.split(" ", 2)[2]
                result["head"] = None if oid == "(initial)" else oid
            elif record.startswith("# branch.upstream "):
                result["upstream"] = record.split(" ", 2)[2]
            elif record.startswith("1 "):
                parts = record.split(" ", 8)
                result["entries"].append({"path": parts[8], "index": parts[1][0], "worktree": parts[1][1], "kind": "changed"})
            elif record.startswith("2 "):
                parts = record.split(" ", 9)
                result["entries"].append({"path": parts[9], "index": parts[1][0], "worktree": parts[1][1],
                                          "kind": "renamed", "from": records[index]})
                index += 1
            elif record.startswith("u "):
                result["entries"].append({"path": record.split(" ", 10)[10], "index": "U", "worktree": "U", "kind": "conflict"})
            elif record.startswith("? "):
                result["entries"].append({"path": record[2:], "index": "?", "worktree": "?", "kind": "untracked"})
        return result

    def diff(self, name, *, staged=False, paths=()):
        repository = self.repository(name)
        arguments = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "--find-renames"]
        if staged:
            arguments.append("--cached")
        for path in paths:
            if not isinstance(path, str) or path.startswith("-") or ".." in path.split("/"):
                raise GitToolError("Invalid diff path")
        _, out, _, truncated = self._git(repository, arguments + ["--", *paths])
        return {"repository": name, "staged": staged, "diff": out.decode("utf-8", "replace"),
                "truncated": truncated == "output_limit"}

    def log(self, name, *, limit=20):
        repository = self.repository(name)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise GitToolError("Log limit must be between 1 and 200")
        code, out, _, _ = self._git(repository, ["log", "--no-show-signature", "--no-color", f"-n{limit}",
                                                 "--format=%H%x1f%an%x1f%ae%x1f%at%x1f%s%x1e", "HEAD"], check=False)
        if code != 0:
            return []  # No commits yet.
        commits = []
        for entry in out.decode("utf-8", "replace").split("\x1e"):
            fields = entry.strip("\n").split("\x1f")
            if len(fields) == 5:
                commits.append({"sha": fields[0], "author": fields[1], "email": fields[2],
                                "timestamp": int(fields[3]), "subject": fields[4]})
        return commits

    # ---- commit ---------------------------------------------------------------------
    def _write_file(self, repository, path, data):
        """Write inside the work tree using no-follow descriptors; refuse links."""
        parts = path.split("/")
        directory = os.open(repository.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=directory)
                except FileExistsError:
                    pass
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = following
            try:
                info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise GitToolError("Only regular single-link files may be replaced")
            except FileNotFoundError:
                pass
            temporary = ".agent-lab-" + uuid4().hex
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=directory)
            try:
                os.write(descriptor, data)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
        except OSError:
            raise GitToolError("Could not write the file inside the trusted work tree") from None
        finally:
            os.close(directory)

    def _check_content(self, path, data):
        if len(data) > self.max_file_bytes:
            raise GitToolError(f"'{path}' exceeds the commit file size limit")
        if _SECRET_CONTENT.search(data):
            raise GitToolError(f"'{path}' contains credential-like content; refusing to commit")

    def _read_worktree(self, repository, path):
        full = os.path.join(repository.path, path)
        try:
            info = os.lstat(full)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise GitToolError(f"'{path}' is not a regular single-link file")
        current = repository.path
        for part in path.split("/")[:-1]:
            current = os.path.join(current, part)
            if os.path.islink(current):
                raise GitToolError(f"'{path}' traverses a symbolic link")
        with open(full, "rb") as handle:
            return handle.read(self.max_file_bytes + 1)

    def commit(self, name, paths, message, *, actor, task=None, contents=None):
        """Stage exactly `paths` (optionally writing trusted `contents` first) and commit.

        The current branch must be writable, the index must contain no other
        staged changes, and every path must be authorized and free of
        credential-like names or content. Hooks and signing are disabled.
        """
        repository = self.repository(name)
        if not isinstance(message, str) or not message.strip() or len(message) > 2000 or "\0" in message:
            raise GitToolError("Commit message must be nonempty text up to 2000 characters")
        if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= 50 or len(set(paths)) != len(paths):
            raise GitToolError("Commit between one and fifty distinct paths")
        paths = [self._path(repository, path) for path in paths]
        record = self._record(name, "commit", {"paths": paths, "message": message}, actor=actor, task=task)
        try:
            branch = self.status(name)["branch"]
            if branch is None:
                raise GitToolError("Detached HEAD: commits require a named writable branch")
            self._writable_branch(repository, branch)
            _, staged, _, _ = self._git(repository, ["diff", "--cached", "--name-only", "-z"])
            if [p for p in staged.decode().split("\0") if p]:
                raise GitToolError("The index already contains staged changes; refusing to mix unrelated work")
            for path in paths:
                if contents is not None and path in contents:
                    data = contents[path].encode("utf-8")
                    self._check_content(path, data)
                    self._write_file(repository, path, data)
                data = self._read_worktree(repository, path)
                if data is not None:
                    self._check_content(path, data)
            self._git(repository, ["add", "--", *paths])
            _, staged, _, _ = self._git(repository, ["diff", "--cached", "--name-only", "-z"])
            staged = sorted(p for p in staged.decode().split("\0") if p)
            if not staged:
                self._git(repository, ["reset", "-q", "--", *paths])
                raise GitToolError("No changes to commit for the requested paths")
            if not set(staged) <= set(paths):
                self._git(repository, ["reset", "-q", "--", *paths])
                raise GitToolError("Staging produced unrequested paths; nothing committed")
            committer, email = repository.committer
            identity = {"GIT_AUTHOR_NAME": f"{actor} (agent)" if task else actor,
                        "GIT_AUTHOR_EMAIL": f"{re.sub(r'[^A-Za-z0-9._-]', '-', actor)}@agent-lab.invalid",
                        "GIT_COMMITTER_NAME": committer, "GIT_COMMITTER_EMAIL": email}
            self._git(repository, ["commit", "--no-verify", "--no-gpg-sign", "-q", "-m", message], env=identity)
            _, head, _, _ = self._git(repository, ["rev-parse", "HEAD"])
            result = {"repository": name, "branch": branch, "commit": head.decode().strip(), "paths": staged}
        except GitToolError as error:
            self._settle(record, "failed", {"error": str(error)}, task=task, actor=actor, event="git_commit_failed")
            raise
        self._settle(record, "succeeded", result, task=task, actor=actor, event="git_committed")
        return result

    # ---- push -------------------------------------------------------------------------
    def _remote_head(self, url, branch):
        code, out, err, interrupted = self._remote_git(["ls-remote", "--refs", url, "refs/heads/" + branch])
        if interrupted or code != 0:
            raise GitToolError("Could not read the remote branch state")
        for line in out.decode().splitlines():
            sha, _, ref = line.partition("\t")
            if ref == "refs/heads/" + branch:
                return sha
        return None

    def prepare_push(self, name, remote, branch):
        """Return the exact binding a human must approve. No effect occurs here."""
        repository = self.repository(name)
        self._writable_branch(repository, branch)
        url = self._remote(repository, remote)
        code, out, _, _ = self._git(repository, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
                                    check=False)
        if code != 0:
            raise GitToolError("Local branch does not exist")
        commit = out.decode().strip()
        expected = self._remote_head(url, branch)
        if expected == commit:
            raise GitToolError("Remote branch already points at this commit; nothing to push")
        if expected is not None:
            known, _, _, _ = self._git(repository, ["cat-file", "-e", expected + "^{commit}"], check=False)
            if known != 0:
                raise GitToolError("Remote branch has commits unknown locally; reconcile before pushing")
            ancestor, _, _, _ = self._git(repository, ["merge-base", "--is-ancestor", expected, commit], check=False)
            if ancestor != 0:
                raise GitToolError("Push would not be a fast-forward; force pushes are not permitted")
        return {"repository": name, "remote": remote, "remote_url": url, "branch": branch,
                "commit": commit, "expected_remote": expected, "operation": "fast_forward_push"}

    def verify_binding(self, binding):
        """Recheck that local and remote state still equal the approved binding."""
        fresh = self.prepare_push(binding["repository"], binding["remote"], binding["branch"])
        if fresh != binding:
            raise GitToolError("Repository or remote state changed since approval; request a new approval")
        return fresh

    def push_approved(self, binding, *, actor, task, request_id):
        """Execute an already-consumed exact approval. Never retried automatically."""
        repository = self.repository(binding["repository"])
        record = self._record(repository.name, "push", binding | {"request_id": request_id}, actor=actor, task=task)
        refspec = f"{binding['commit']}:refs/heads/{binding['branch']}"
        try:
            extra,env=self._remote_access(binding['remote_url'])
            code, out, err, interrupted = self._exec(
                [self.binary, "--git-dir", os.path.join(repository.path, ".git"), *_SAFE,
                 *extra, "push", "--porcelain", "--no-verify", binding["remote_url"], refspec],
                env, self.timeout)
        except GitToolError as error:
            interrupted, code, err = "start_failed", None, str(error).encode()
        actual, remote_known = None, True
        try:
            actual = self._remote_head(binding["remote_url"], binding["branch"])
        except GitToolError:
            remote_known = False
        evidence = {"repository": repository.name, "branch": binding["branch"], "commit": binding["commit"],
                    "remote": binding["remote"], "observed_remote": actual, "remote_observed": remote_known,
                    "exit_code": code, "interrupted": interrupted, "stderr": err.decode("utf-8", "replace")[-500:]}
        if interrupted or not remote_known or (actual == binding["commit"]) != (code == 0):
            # Interrupted process, unreadable remote, or a result that disagrees
            # with the observed remote: the external effect is ambiguous.
            self._settle(record, "uncertain", evidence, task=task, actor=actor, event="git_push_uncertain")
            raise GitUncertainError("Push outcome is uncertain; reconcile remote state, do not retry automatically")
        if actual == binding["commit"]:
            self._settle(record, "verified", evidence, task=task, actor=actor, event="git_push_verified")
            return evidence
        self._settle(record, "failed", evidence, task=task, actor=actor, event="git_push_failed")
        raise GitToolError("Push was rejected; the remote branch does not show the approved commit")

    def reconcile(self, operation_id, *, actor):
        """Observe remote state for an uncertain push. Never pushes or retries."""
        row = self.workflow.db.execute("SELECT * FROM git_operations WHERE id=?", (operation_id,)).fetchone()
        if row is None or row["operation"] != "push":
            raise GitToolError("Unknown push operation")
        binding = json.loads(row["arguments"])
        repository = self.repository(binding["repository"])
        actual = self._remote_head(repository.remote_url(binding["remote"]), binding["branch"])
        outcome = "remote_shows_commit" if actual == binding["commit"] else "remote_does_not_show_commit"
        record = self._record(repository.name, "reconcile", {"operation_id": operation_id}, actor=actor, task=row["task"])
        self._settle(record, "succeeded", {"operation_id": operation_id, "observed_remote": actual, "outcome": outcome,
                                           "note": "Observation only; no push was attempted"})
        return {"operation_id": operation_id, "observed_remote": actual, "outcome": outcome}

