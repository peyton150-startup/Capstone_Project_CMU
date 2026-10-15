# The package for the research agent's live investigation path.
# Responsibility: name the package only. The agent reaches the factory through tools.
"""The research agent and the live investigation it runs. The investigation
(`investigation`) is a set of stages, the inner loop (`loop`) takes the turns, a
policy (`policy`) makes each choice, and working memory (`state`) holds what has
been learned so far. It sees tool results only, never the simulator.
"""
