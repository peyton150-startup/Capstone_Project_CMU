"""The research agent: one model, the toolbox, and a bounded investigation loop.

The loop is plain: show the model the anomaly, run whatever tools it asks
for, hand back the results, repeat until it submits a diagnosis or runs
out of turns. The staged reasoning (observe, hypothesise, test, act,
verify) is asked for in the system prompt and recorded in the notebook;
it is not hard-coded, because choosing what to look at next is the
agent's job.
"""

from dataclasses import dataclass

from capstone.agent.models import Model, Turn
from capstone.agent.toolbox import Toolbox

SYSTEM_PROMPT = """\
You are a research agent investigating an anomaly on a simulated manufacturing line. \
You see the factory only through your tools. Time passes only when you call wait; \
looking things up is free.

The line: machines CNC-01 upward, in order; every job visits each machine in turn and \
is inspected (pass/fail) when it leaves the last one. Jobs are cut from numbered material \
batches. Each machine has vibration (mm/s), temperature (°F) and load (%) sensors; the \
factory has an air thermometer. Normal life includes: jobs of different weights (load), \
a daily air temperature cycle, a loading door that cools the air for a while, machines \
waiting on each other, and about one inspection failure in a hundred.

Possible causes, exactly one of which is present:
- bearing_degradation: one machine's bearing wears. Vibration creeps up over hundreds of \
ticks, then temperature, motor load and job time; rejects rise; eventually the machine stops. \
Fix: replace_bearing on that machine.
- wrong_setting: one machine's speed was changed. A single lasting step in its job time \
and its speed setting, small steps in vibration and heat, more rejects. Fix: reset_setting.
- bad_material_batch: one material batch is poor. Rejects concentrate in that batch's jobs \
while machine sensors look normal; it ends by itself when the batch runs out. Fix: none.
- false_alarm: a sensor glitch. A brief spike on one sensor of one machine that nothing \
else confirms and that goes away by itself. Fix: none.

Work like a scientist:
1. Collect initial evidence about the anomaly you are given.
2. Record competing hypotheses with update_hypotheses (supporting and contradicting \
evidence, rough confidence), and revise the table as evidence comes in.
3. For each hypothesis, decide what evidence would tell them apart and fetch it. Compare \
a machine with its own past and with the other machines. Prefer get_sensor_trend for long \
ranges.
4. Act only if the cause needs fixing: propose_action with a reason that states what you \
expect afterwards. A needless repair stops production and counts against you, and so does \
fixing the wrong machine. Then check get_proposals for the human's decision.
5. Verify: after an approved action, wait for the work to finish and long enough to compare \
before and after. If what you predicted did not happen, revise.
6. Finish with submit_diagnosis, naming the cause and the machine (or batch), with a short \
summary of the evidence, the action and the verification.

If search_incident_history is available, past cases can suggest where to look first; \
they are hints, not proof, and may have been wrong.

Be economical: tool calls and elapsed ticks are both scored."""


@dataclass
class Investigation:
    turns: int
    text: list[str]
    finished: bool


class ResearchAgent:
    def __init__(self, model: Model, toolbox: Toolbox, *, max_turns: int = 40, after_tools=None):
        self.model = model
        self.toolbox = toolbox
        self.max_turns = max_turns
        # Called after each batch of tool calls; the episode uses it to let the human decide proposals.
        self._after_tools = after_tools or (lambda: None)

    def investigate(self, anomaly: str) -> Investigation:
        prompt = f"Anomaly detected:\n{anomaly}\n\nInvestigate it."
        turn = self.model.start(SYSTEM_PROMPT, self.toolbox.specs, prompt)
        said: list[str] = []
        for number in range(1, self.max_turns + 1):
            if turn.text:
                said.append(turn.text)
            if self.toolbox.notebook.diagnosis is not None:
                return Investigation(number, said, True)
            if turn.stop_reason == "refusal":
                break
            if turn.stop_reason == "pause_turn":
                turn = self.model.continue_with([])
                continue
            turn = self._next(turn)
        return Investigation(self.max_turns, said, self.toolbox.notebook.diagnosis is not None)

    def _next(self, turn: Turn) -> Turn:
        results = [self.toolbox.run(call) for call in turn.tool_calls]
        self._after_tools()
        if self.toolbox.notebook.diagnosis is not None:
            return Turn(text="", tool_calls=[], stop_reason="end_turn")
        note = None if results else "Continue the investigation. Finish by calling submit_diagnosis."
        return self.model.continue_with(results, note)
