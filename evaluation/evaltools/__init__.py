"""Evaluation scaffolding: inventories, evidence packets and Snap requests.

Nothing here is imported by the `capstone` package. These tools read the
repository, its test coverage and saved experiment records, and write the
evaluation artifacts under `evaluation/`. They never change production
behaviour, prompts, the simulator or the investigation graph.
"""
