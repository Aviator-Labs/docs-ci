---
title: Resource Types
---

Each resource in a pipeline has a `type`. The resource's type determines what versions are detected, the bits that are
fetched when the resource's [`get` step](../steps/get.md) runs, and the side effect that occurs when the
resource's [put step](../steps/put.md) runs.

Concourse comes with a few "core" resource types to cover common use cases like
`git` and `s3` - the rest are developed and supported by the Concourse
community. An exhaustive list of all resource types is available in the
[Resource Types Catalog page](../../resource-types-list.md).

A pipeline's resource types are listed under [`pipeline.resource_types`](../pipelines/index.md#pipeline-schema) with the
following schema:

## `resource_type` schema

```concourse-schema
def: resourceType
```

---

??? example "Using a `rss` resource type to subscript to RSS feeds"

    Resource Types can be used to extend the functionality of your pipeline and provide deeper integrations. This 
    example uses one to trigger a job whenever a new [Dinosaur Comic](http://www.qwantz.com/) is out.
    
    ```yaml
    ---
    resource_types:
      - name: rss
        type: registry-image
        source:
          repository: suhlig/concourse-rss-resource
          tag: latest
    
    resources:
      - name: dino-comic
        type: rss
        source:
          url: http://www.qwantz.com/rssfeed.php
    
    jobs:
      - name: get-comic
        plan:
          - get: dino-comic
            trigger: true
    ```
