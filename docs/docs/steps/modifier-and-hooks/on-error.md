---
title: On Error Step Hook
tags:
  - Step
  - Hook
---

# `on_error` Step Hook

```concourse-schema
def: on_errorModifier
```

---

???+ example "Sending a notification"

    This step can be used to notify folks if their builds errored out:

    ```yaml
    plan:
      - do:
          - get: ci
          - task: unit
            file: ci/unit.yml
        on_error:
          put: slack
    ```
