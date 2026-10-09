---
title: Ensure Step Hook
tags:
  - Step
  - Hook
---

# `ensure` Step Hook

```concourse-schema
def: ensureModifier
```

---

???+ example "Releasing a lock"

    The following build plan acquires a lock and then `ensure`s that the lock is released.

    ```yaml
    plan:
      - put: some-lock
        params:
          acquire: true
      - task: integration
        file: foo/integration.yml
        ensure:
          put: some-lock
          params:
            release: some-lock
    ```
