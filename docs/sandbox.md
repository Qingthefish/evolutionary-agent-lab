# Python sandbox setup and validation

The instructor requires private execution environments and actual code execution. The current backend executes Python with a Linux Docker engine selected by an explicit local Unix socket. The file broker, model loop, search, and future Git tools remain separate capabilities. This is a constrained Python backend, not a guarantee that every official test task or the instructor's unspecified minimum sandbox boundary is satisfied.

## macOS development environment

Use a dedicated Colima profile. This creates a Linux VM without sharing host folders or forwarding the SSH agent, sets resource limits, and leaves the current Docker context unchanged. No login service is needed.

```bash
brew install colima docker
colima start agent-lab --cpu 1 --memory 2 --disk 8 --root-disk 8 --vm-type vz --runtime docker --mount none --activate=false --ssh-agent=false --ssh-config=false --port-forwarder none --binfmt=false
docker --context colima-agent-lab pull python:3.12-slim
docker --context colima-agent-lab image inspect python:3.12-slim --format '{{index .RepoDigests 0}}'
```

Copy the **complete repository and digest reference** printed by inspection, such as `python@sha256:...`. A floating tag is allowed for this explicit setup pull, but execution refuses tags without a digest and never pulls automatically. Images and the Docker engine must be obtained from trusted sources and kept updated through a deliberate new validation run. Do not download models for this backend: the submitted LLM remains DeepSeek/HKGAI.

On Linux, use an existing appropriately configured local Docker engine and its actual Unix socket instead of Colima. The backend requires working memory/swap, CPU, PID, and default seccomp support; it fails closed when these checks fail. It does not install Docker, start a VM, change contexts, or pull images itself. If image setup needs a proxy, configure only the designated engine using the [Docker daemon proxy instructions](https://docs.docker.com/engine/daemon/proxy/). Host proxy/API credentials are not forwarded to executed code.

## Actual execution fixture

Replace the image placeholder with the inspected full digest reference:

```bash
python3 -m agent_lab sandbox-demo --docker-host "unix://${HOME}/.colima/agent-lab/docker.sock" --image 'python@sha256:REPLACE_WITH_INSPECTED_DIGEST'
```

The command creates a fresh ignored `runs/sandbox-*` directory, writes fixed text-processing source/test/input files through the controlled broker, dispatches `run_python`, exports a checked text result, confirms container deletion, and applies independent expected-text verification before completing the task. Reports are labelled `sandbox_integration_fixture`, contain zero model/API network calls, and have `benchmark_valid: false`. Its tests and source are scripted fixtures; this is actual process execution, not evidence of model ability or learned behavior. A failed fixture exits nonzero. Missing runtime/image fails instead of executing on the host.

## Actual isolation checks

```bash
AGENT_LAB_DOCKER_HOST="unix://${HOME}/.colima/agent-lab/docker.sock" AGENT_LAB_PYTHON_IMAGE='python@sha256:REPLACE_WITH_INSPECTED_DIGEST' python3 -m unittest discover -s tests -p test_sandbox_integration.py -v
```

These opt-in checks run real containers: multi-file imports/tests and export, genuine assertion failure, private-workspace and host-file separation, unavailable external networking, absent host environment/socket, root-file write refusal, payload/supervisor UID separation, effective capability/seccomp/cgroup checks, timeout and descendant removal, bounded output, memory/PID limits, unsafe export rejection, task cancellation, and independent watchdog expiry without the host execution loop. They never read real credentials or use live model calls. Ordinary offline test discovery skips these checks when the explicit variables are absent; skipped integration tests must not be reported as passed.

## Lifecycle and limits

Each invocation creates a fresh private container with only the requested, hash-matched input snapshots. It has no host bind mounts or Docker socket, no external network, a read-only image, dropped capabilities, no new privileges, bounded writable tmpfs storage/inodes, and limits for memory, CPU, processes, open files, file size, output, and duration. Payload code uses UID 65534; the trusted watchdog/export reader uses UID 65533. The watchdog stops the container after its fixed lifetime if the host controller disappears. Containers share a trusted Linux kernel/engine and base image; this is not a VM per agent or a proof against kernel/runtime vulnerabilities. The dedicated development VM adds host separation on macOS.

Supported jobs contain at most 20 text/source inputs, 16 script arguments, and 8 declared new text outputs. Each exported file is limited to 64 KiB, must be regular, single-link, readable by the separate exporter, and valid UTF-8. Inputs and outputs cannot overlap. Exports are checked through no-follow directory descriptors, durably checkpointed, and imported through the owned-task broker after confirmed cleanup. Export/import is not a cross-filesystem atomic transaction. Existing paths are never overwritten; partial import receipts remain visible. Tool dispatch `ok: true` means the tool returned a result, not that code exited zero or the task passed. Inspect `execution.exit_code`, `execution.interrupted`, `error`, and `cleanup_confirmed`, then use independent acceptance checks.

The backend permits only one reserved/active sandbox per workflow database at present. An unconfirmed cleanup or interrupted controller blocks another sandbox until a trusted controller reconciles it. It binds the endpoint digest and actual engine identity to the database, so switching engines cannot falsely confirm an old container's deletion. Cleanup removes only the run-labelled containers. `reconcile_cleanup` confirms removal; `recover_exports` can restore validated durable text snapshots without replaying code or overwriting changed artifacts. These are trusted recovery APIs, absent from model tools.

Host-side duration checks bound the execution CLI and remove the container on timeout, output excess, or task pause/cancellation. Setup and cleanup have separate bounded operations, so total return time may exceed the payload duration. The watchdog has a small fixed grace beyond that budget. If the daemon becomes unavailable, immediate deletion cannot be guaranteed; retain the run ID, wait for the watchdog where applicable, and confirm cleanup after access returns. Do not silently replay unknown effects. A fresh task has no package installation or network access; additional languages/dependencies, persistent agent containers, concurrency, and general execution verification remain future work.

Stop the dedicated VM when finished:

```bash
colima --profile agent-lab stop
```

This stops its processes and releases VM memory. It preserves its image cache and project-specific configuration for the next run. No `prune`, unrelated container deletion, or default-context change is required.

## Primary references

- [Colima installation](https://colima.run/docs/installation/) and [configuration](https://colima.run/docs/configuration/).
- [Docker execution flags](https://docs.docker.com/reference/cli/docker/container/run/), [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/), [none networking](https://docs.docker.com/engine/network/drivers/none/), and [tmpfs options](https://docs.docker.com/engine/storage/tmpfs/).
- [Docker security boundaries](https://docs.docker.com/engine/security/). A restricted container is an isolation mechanism, not an unconditional security guarantee.

## Delegated execution checks

The opt-in suite also runs two scheduler integration cases with fixed synthetic provider responses and the actual Docker backend. A reviewer delegates Python work to a coder; source creation, sandbox execution, explicit artifact offer/accept, and independent text/execution checks run through the scheduler and gateway. The successful case completes both tasks after actual zero-exit execution and confirmed cleanup. In the negative case, code exits with status 9, then a synthetic proposal writes the expected text through the file tool. The independent verifier still rejects it because the stored sandbox execution failed; the bounded child and root fail rather than receiving success for matching text alone.

Run just these cases with the same explicit environment settings using `python3 -m unittest discover -s tests -p test_sandbox_integration.py -k scheduler -v`. They are engineering integration checks, make zero model/API calls, and establish neither live autonomous collaboration nor performance on the instructor's test set. They require actual containers and are skipped when the Docker settings are absent.
