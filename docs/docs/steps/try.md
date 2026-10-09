---
title: Try Step
tags:
  - Step
---

```concourse-schema
def: tryFields
```

---

???+ example "Allowing non-critical behavior to fail"

    When emitting logs somewhere for analyzing later, if the destination flakes
    out it may not really be critical, so we may want to just swallow the error:

    ```yaml
    plan:
      - task: run-tests
        config: # ...
        on_success:
          try:
            put: test-logs
            params:
              from: run-tests/*.log
      - task: do-something-else
        config: # ...
    ```
