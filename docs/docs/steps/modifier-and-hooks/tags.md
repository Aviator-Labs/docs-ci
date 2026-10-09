---
title: Tags Step Modifier
tags:
  - Step
  - Modifier
---

# `tags` Step Modifier


```concourse-schema
def: tagsModifier
```

---

???+ example "Running in a private network"

    You may have a private cluster only reachable by special workers running
    on-premises. To run steps against those workers, just provide a matching
    tag:

    ```yaml
    plan:
      - get: my-repo
      - task: acceptance-tests
        tags:
          - private
        file: my-repo/ci/acceptance.yml
      - put: my-site
        tags:
          - private
        params:
          path: my-repo
    ```

???+ example "Tagging multiple steps"

    If you have multiple steps to tag you can easily tag them all using `do` or
    `in_parallel`.

    ```yaml
    plan:
      - tags: ["private"]
        do:
          - get: my-repo
          - task: acceptance-tests
            file: my-repo/ci/acceptance.yml
          - put: my-site
            params:
              path: my-repo
    ```
