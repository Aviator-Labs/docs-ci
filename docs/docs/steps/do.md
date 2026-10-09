---
title: Do Step
tags:
  - Step
---

# `do` Step


```concourse-schema
def: doFields
```

---

???+ example "Running multiple steps in a try"

    This can be used to perform multiple steps serially in a [`try` step](try.md):

    ```yaml
    jobs:
      - name: with-do
        plan:
          - try:
              do:
                - get: black-ice
                - get: control-node
                - get: cyberdeck

    resources:
      - name: black-ice
        type: mock
      - name: control-node
        type: mock
      - name: cyberdeck
        type: mock
    ```
