---
title: Timeout Step Modifier
tags:
  - Step
  - Modifier
---

# `timeout` Step Modifier


```concourse-schema
def: timeoutModifier
```

---

???+ example "Giving up"

    The following will run the `unit` task and cancel it if it takes longer than
    1 hour and 30 minutes:

    ```yaml
    plan:
      - get: foo
      - task: unit
        file: foo/unit.yml
        timeout: 1h30m
    ```
