# Groups durable memory contracts, promotion policy, and persistence boundaries.
# Responsibility: keep post-investigation memory separate from the live runtime.
"""Episodic memory: the lessons kept from finished investigations. A lesson is built
from the record (`reflection`), checked by a gate (`policy`), stored (`repository`,
`schema`) and found again (`recall`). Importing it needs no database.
"""
