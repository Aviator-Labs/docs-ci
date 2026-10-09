---
title: Get Step
tags:
  - Step
---

# `get` Step

Fetches a version of a [resource](../resources/index.md) and potentially
metadata about the resource. Metadata is exposed as a [local
var](../vars.md#local-var) under the name of `get` step. Expand each section
below for more details and examples.

## `get` schema

```concourse-schema
def: getFields
```

---

??? example "Access Metadata from Local Var"

    ### Access Metadata from Local Var

    Resources have the option to expose metadata for any version that it fetches.
    You'll need to reference the documentation for the resource type you're using
    to see if it exposes any metadata. Metadata is rendered as a table of key-value
    strings if viewed from the web UI.

    If the resource does expose metadata, it is then added as a [local
    var](../vars.md#local-var) named after the `get` step. This example results
    in a local var called `my-resource`, with keys `hello` and `foo`.

    ```yaml
    resources:
      - name: my-resource
        type: mock
        source:
          metadata:
            - name: hello
              value: world
            - name: foo
              value: bar

    jobs:
      - name: job
        plan:
          - get: my-resource
          - task: ref-local-vars
            config:
              platform: linux
              image_resource:
                type: mock
                source: {mirror_self: true}
              params:
                FOO: ((.:my-resource.foo))
              run:
                path: sh
                args:
                  - -c
                  - |
                    echo Hello ((.:my-resource.hello))
                    echo foo $FOO
    ```
