---
title: Attempts Step Modifier
tags:
  - Step
  - Modifier
---

# `attempts` Step Modifier

```concourse-schema
def: attemptsModifier
```

---

??? example "Retrying a task"

    The following will run the task and retry it up to 9 times (for a total of 10 attempts) if it fails:

    ```yaml
    plan:
      - get: foo
      - task: unit
        file: foo/unit.yml
        attempts: 10
    ```

??? example "Retrying with a timeout"

    When used in combination with `timeout`, the timeout applies to each step.

    This semi-arbitrary decision was made because often things either succeed in
    a reasonable amount of time or fail due to hanging/flakiness. In this case
    it seems more useful to allow each attempt the allotted timeout rather than
    have one very long attempt prevent more attempts.

    ```yaml
    plan:
      - get: flake
      - task: flaky-tests
        file: flake/integration.yml
        timeout: 10m
        attempts: 3
    ```
