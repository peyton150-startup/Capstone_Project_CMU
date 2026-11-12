# 13-case live triage, 2026-11-11

This was a live model run on unmerged PR #239 source commit `17b5175bccdf99e4e6cc8b64a5b01fc79b66fa38`. It used 90-second triage, six requested tool calls, line context on, automatic line screening, and the optional late conclude route to NVIDIA Nemotron 3.5 Lightning 30B A3B. The run did not use deep investigation, manual approval, memory, critic, hazards, or tree of thought. The configuration, records and audit are preserved beside this note.

All 13 cases produced records. All 13 had line context enabled. Ten recommended a deep investigation, but none ran one. Seven ended at the time limit, three at the tool-call limit, and three with `model_unavailable`. Total wall time across cases was 1,033 seconds (17.2 minutes).

The deterministic scorer assigned no fault diagnosis to any case (`diagnosed_fault` is null in all 13). This does not mean every case was harmless: KA-12, a real hydraulic leak on CNC-05, was described as a false alarm. KA-11, real servo-drive wear on CNC-02, was described as a likely momentary spike. Some no-action cases have `resolved: true` in the score solely because no action was expected; that is not evidence of a correct diagnosis.

The run is evidence of poor diagnostic coverage and model availability in this particular 90-second configuration. It does not establish the performance of a full deep investigation. Review the per-case records and audit before changing triage budgets, tool selection, or model routing.
