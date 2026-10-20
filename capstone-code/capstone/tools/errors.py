# The error a tool raises when the agent's own request cannot be served.
# Responsibility: mark the messages that are safe and useful to show the agent.
"""`ToolInputError`: a `ValueError` whose message is written for the agent.

The factory provider passes this message on as it is, so it may describe
only the request: what the agent sent and what would be accepted instead.
It must never describe the factory's hidden state. A tool that fails in
any other way is reported without its message.
"""


class ToolInputError(ValueError):
    """The request was wrong in a way the agent can correct."""
