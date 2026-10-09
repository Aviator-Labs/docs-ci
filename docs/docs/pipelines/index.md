---
title: Pipelines
---

A pipeline is the result of configuring [Jobs](../jobs.md) and [Resources](../resources/index.md) together. When
you configure a pipeline, it takes on a life of its own, to continuously detect resource versions and automatically
queue new builds for jobs as they have new available inputs.

The name of a pipeline has a few restrictions that are outlined here: [
`identifier` schema](../config-basics.md#identifier-schema).

Pipelines are configured via [`fly set-pipeline`](setting-pipelines.md#fly-set-pipeline) or the [
`set_pipeline` step](../steps/set-pipeline.md) as declarative [YAML files](../config-basics.md#intro-to-yaml) which 
conform to the following schema:

## `pipeline` schema

```concourse-schema
def: pipeline
```
