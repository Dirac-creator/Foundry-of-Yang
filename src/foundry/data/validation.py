"""Validate the exchange format and cross-record scientific data lineage."""
import json
import math
from datetime import datetime
from importlib.resources import files
from jsonschema import Draft202012Validator, FormatChecker


class DataError(ValueError):
    """Invalid exchange data."""


def _require(condition, message):
    if not condition:
        raise DataError(message)


def _finite(value):
    if isinstance(value, float):
        _require(math.isfinite(value), "Non-finite numeric value")
    elif isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def _acyclic(graph):
    # Iterative topological elimination avoids recursion limits for long histories.
    pending = {node: set(edges) for node, edges in graph.items()}
    reverse = {node: set() for node in pending}
    for node, edges in pending.items():
        for edge in edges:
            reverse[edge].add(node)
    ready = [node for node, edges in pending.items() if not edges]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for child in reverse[node]:
            pending[child].remove(node)
            if not pending[child]:
                ready.append(child)
    _require(visited == len(graph), "Cyclic record references")


def validate_dataset(data):
    """Raise DataError on invalid data; never modify or fill in measurements."""
    schema = json.loads(files("foundry").joinpath("schemas/dataset.schema.json").read_text(encoding="utf-8"))
    error = next(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data), None)
    if error:
        location = "/".join(map(str, error.absolute_path)) or "<root>"
        raise DataError(f"{location}: {error.message}")
    _finite(data)
    names = ("samples", "layouts", "artifacts", "process_runs", "measurements")
    indexes = {}
    seen = set()
    for name in names:
        indexes[name] = {}
        for record in data[name]:
            key = record["id"]
            _require(key not in seen, f"Duplicate ID: {key}")
            seen.add(key)
            indexes[name][key] = record

    def lookup(kind, key):
        _require(key in indexes[kind], f"Missing {kind} reference: {key}")
        return indexes[kind][key]

    parents = {"wafer": "lot", "die": "wafer", "device": "die"}
    for sample in data["samples"]:
        parent = sample["parent_id"]
        if sample["kind"] == "lot":
            _require(parent is None, "Lot cannot have a parent")
        else:
            _require(lookup("samples", parent)["kind"] == parents[sample["kind"]], "Invalid sample parent kind")
        if sample.get("layout_id") is not None:
            lookup("layouts", sample["layout_id"])
    for layout in data["layouts"]:
        lookup("artifacts", layout["artifact_id"])

    def ancestors(sample_id):
        result = set()
        while sample_id is not None:
            result.add(sample_id)
            sample_id = lookup("samples", sample_id)["parent_id"]
        return result

    expected_units = {"duration": "s", "temperature": "K", "pressure": "Pa", "flow": "sccm", "power": "W", "thickness": "nm", "etch_depth": "nm", "wavelength": "nm", "angle": "deg", "loss": "dB", "loss_coefficient": "dB/cm"}
    for name in ("process_runs", "measurements"):
        for record in data[name]:
            lookup("samples", record["sample_id"])
            for artifact_id in record["artifact_ids"]:
                lookup("artifacts", artifact_id)
            for field in ("parameters", "quantities", "conditions"):
                for quantity, value in record.get(field, {}).items():
                    if quantity in expected_units:
                        _require(value["unit"] == expected_units[quantity], f"Wrong unit for {quantity}: expected {expected_units[quantity]}")

    def time(value):
        return datetime.fromisoformat(value.upper())
    process_graph = {}
    for run in data["process_runs"]:
        _require(time(run["started_at"]) <= time(run["ended_at"]), "Process ends before it starts")
        process_graph[run["id"]] = run["previous_run_ids"]
        for previous_id in run["previous_run_ids"]:
            previous = lookup("process_runs", previous_id)
            _require(previous["sample_id"] in ancestors(run["sample_id"]), "Previous process belongs to unrelated sample")
            _require(time(previous["ended_at"]) <= time(run["started_at"]), "Previous process ends too late")
    _acyclic(process_graph)
    correction_graph = {}
    for measurement in data["measurements"]:
        run_id = measurement["process_run_id"]
        if run_id is not None:
            run = lookup("process_runs", run_id)
            _require(run["sample_id"] in ancestors(measurement["sample_id"]), "Measurement refers to unrelated process sample")
            _require(time(measurement["measured_at"]) >= time(run["ended_at"]), "Measurement precedes linked process completion")
        old_id = measurement.get("supersedes_id")
        correction_graph[measurement["id"]] = [old_id] if old_id is not None else []
        if old_id is not None:
            old = lookup("measurements", old_id)
            _require(old["sample_id"] == measurement["sample_id"], "Correction must refer to the same sample")
    _acyclic(correction_graph)
    return {name: len(data[name]) for name in names}


def validate_file(path):
    with open(path, encoding="utf-8-sig") as stream:
        return validate_dataset(json.load(stream))
