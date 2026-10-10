# Vendored copy of indicer

This directory is a copy of the runtime portion of `indicer-hetero-match`,
not original work of this repository.

| | |
|---|---|
| Source | https://github.com/sandipbramhankar/indicer-hetero-match |
| Commit | `29a5fad6d180a15d589c0bd216e89fd73406b943` |
| Dated | 2026-10-03 |
| Patent | Indian Patent Application 202621097866 |
| Author | Sandipkumar Prabhu Bramhankar |

## Why it is vendored rather than installed

The upstream repository is private. Installing from it during a Railway build
would require a GitHub token in the build environment; copying the package in
removes that dependency entirely, so the deploy needs no GitHub access.

## What was copied

`pipeline/` (stages 1-6) and `quorum/`. The `eval/` and `adapters/`
subpackages were left out: they exist to reproduce the benchmark, and nothing
in this platform imports them.

## Keeping it in step

This copy does not update itself. After changing indicer upstream:

```bash
cd ../indicer-hetero-match && git rev-parse HEAD      # note the new commit
cp -r indicer/pipeline indicer/quorum indicer/__init__.py ../seva-governance/indicer/
# update the commit hash in the table above, then run the tests
```

`tests/test_names.py` and `tests/test_verification.py` exercise this code
through the platform, so a bad sync shows up there.
