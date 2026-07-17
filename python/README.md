# nodes-core

Nodes core: a problem-agnostic knowledge substrate.

`nodes-core` is the Python implementation of the Nodes kernel — a portable
corpus of plain-text nodes with typed relations, structural shapes, and
derived full-text-search and similarity indexes. A TypeScript implementation
([`@nodes-dev/core`](https://www.npmjs.com/package/@nodes-dev/core)) passes
the same cross-language conformance fixtures.

## Install

```
pip install nodes-core
```

## Use

```python
import nodes.core
```

The `nodes` namespace is a PEP 420 native namespace package; `nodes-core`
ships exactly the `nodes.core` subpackage.

## Documentation

The language-neutral format and behavior specification, both
implementations, and the shared conformance fixtures live at
<https://github.com/nodes-dev/core>.

## License

MIT
