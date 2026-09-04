---
title: Templating - Single File
---

`ytt` has a concept of data values that, on a simple level, can act like [Static Vars](../../docs/vars.md#static-vars).

In the below example, we are templating a simple pipeline that just prints out "hello world of vars!". With this
pipeline, we load the data on the first line, and use the various data values declared to fill in the blanks:

```yaml linenums="1"
--8<-- "libs/examples/pipelines/templates/simple/template.yml"
```

When specifying a values file, we denote it with the `#@data/values` notation and then specify all of our possible keys.

```yaml linenums="1"
--8<-- "libs/examples/pipelines/templates/simple/vars.yml"
```

Given the template and the data values, we can then compile the YAML files to gain our final output:

```shell
$ ytt -f template.yml -f vars.yml
jobs:
- name: hello-world-job
  plan:
  - task: hello-task
    config:
      platform: linux
      image_resource:
        type: mock
        source:
          mirror_self: true
      run:
        path: echo
        args:
        - hello world of vars!
```

The above can also be stored to an output file and then applied using [
`fly set-pipeline`](../../docs/pipelines/setting-pipelines.md#fly-set-pipeline)

```shell
ytt -f template.yml -f vars.yml > generated.yml

fly -t main set-pipeline -p ytt-single-file -c generated.yml
```

<div>
  <div style="position:relative;padding-top:40%;">
    <iframe src="https://ci.concourse-ci.org/teams/examples/pipelines/hello-world-rendered?hide_ui=true" allowfullscreen
      style="position:absolute;top:0;left:0;width:100%;height:100%;border:0"></iframe>
  </div>
</div>
