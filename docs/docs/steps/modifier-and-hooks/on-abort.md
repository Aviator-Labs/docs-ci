---
title: On Abort Step Hook
tags:
  - Step
  - Hook
---

# `on_abort` Step Hook

```concourse-schema
def: on_abortModifier
```

---

???+ example "Cleaning up on abort"

    The following will perform the `cleanup` task only if the build is aborted while the `unit` task was running:

    ```yaml
    plan:
      - get: foo
      - task: unit
        file: foo/unit.yml
        on_abort:
          task: cleanup
          file: foo/cleanup.yml
    ```
