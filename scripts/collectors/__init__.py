"""collectors/ — one module per source (errata §4.3). All keyless unless an
optional env token exists. Each module exposes `collect(...) -> list[dict]`
returning util.make_item records.
"""
