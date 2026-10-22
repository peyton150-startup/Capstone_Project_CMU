# Near-duplicate pairs (draft lessons)

Drafted 2026-10-22 because the memory store held no real lessons yet. Labels are
Claude's draft labels for the developer to review; every 5th pair is held out.
Data: `near-duplicate-pairs.jsonl`. Results: `2026-10-22-near-duplicate-threshold.md`.

## 1. `routine_check` / `resolved` / `CNC-01`

Label: **different**

- **A** (Early spindle bearing wear on CNC-01): Routine check: the one machine with slowly rising vibration had early bearing wear.
- **B** (Spindle speed set off standard on CNC-01): On a routine check, compare each machine's spindle speed with its job standard; one was set off standard before any rejects appeared.

## 2. `inspection_failures` / `resolved` / `CNC-02`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Check whether failed jobs share a material batch before blaming a machine; here they did not, which ruled out the batch.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When failed jobs came from one machine and the same batch ran fine elsewhere, the cause was that machine's setting, not the material.

## 3. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Trace failed inspections back to the machine that produced them; all of them traced to one machine whose speed setting differed from the standard.

## 4. `inspection_failures` / `resolved` / `CNC-02`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When jobs start failing inspection, first find out which machine made them; if every failure came from the same machine, compare its spindle speed against the job standard, because a mis-set speed produced the dimensional rejects.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Look at the setting change log for the machine with the rejects; the failures began right after the spindle speed was changed.

## 5. `status` / `resolved` / `CNC-05`

Label: **different** (held out)

- **A** (Failed spindle bearing on CNC-05): When a machine stops unexpectedly, review its vibration history before the stop; a steady climb beforehand showed the spindle bearing had failed.
- **B** (Failed spindle bearing on CNC-05): After an unexpected stop, check maintenance records first; the stopped machine was past its bearing service interval.

## 6. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): Rising motor load alongside vibration on the alarmed machine was the clearest early sign; vibration alone was noisy.

## 7. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Inspection failures clustered on a single machine pointed to a wrong spindle speed setting there, so group failed jobs by machine before anything else.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Trace failed inspections back to the machine that produced them; all of them traced to one machine whose speed setting differed from the standard.

## 8. `inspection_failures` / `resolved` / `CNC-02`

Label: **different**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Trace failed inspections back to the machine that produced them; all of them traced to one machine whose speed setting differed from the standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): The rejects started immediately after a spindle speed change on that machine, so check its recent setting changes first.

## 9. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): Steady single-machine vibration rise means a worn spindle bearing; compare against the other machines.
- **B** (Spindle bearing wear on CNC-03): If the vibration alarm is on one machine, pull that machine's vibration history and compare it with the rest of the line; a gradual, sustained increase on that machine only is characteristic of spindle bearing wear, which replacement fixed.

## 10. `inspection_failures` / `resolved` / `CNC-02`

Label: **different** (held out)

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Check whether failed jobs share a material batch before blaming a machine; here they did not, which ruled out the batch.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Look at the setting change log for the machine with the rejects; the failures began right after the spindle speed was changed.

## 11. `routine_check` / `resolved` / `CNC-01`

Label: **same**

- **A** (Spindle speed set off standard on CNC-01): On a routine check, compare each machine's spindle speed with its job standard; one was set off standard before any rejects appeared.
- **B** (Spindle speed set off standard on CNC-01): Routine checks should include spindle speed against the job standard; a mis-set machine was caught before it produced rejects.

## 12. `routine_check` / `resolved` / `CNC-01`

Label: **different**

- **A** (Early spindle bearing wear on CNC-01): A routine check found early bearing wear by spotting the one machine whose vibration crept up while the rest stayed flat.
- **B** (Spindle speed set off standard on CNC-01): Routine checks should include spindle speed against the job standard; a mis-set machine was caught before it produced rejects.

## 13. `alarm` / `unresolved` / `CNC-04`

Label: **different**

- **A** (Spindle bearing wear on CNC-04): replace_bearing on CNC-04 was tried for alarm and the check afterwards found it unresolved.
- **B** (Wrong spindle speed on CNC-04): reset_setting on CNC-04 was tried for alarm and the check afterwards found it unresolved.

## 14. `status` / `resolved` / `CNC-05`

Label: **different**

- **A** (Failed spindle bearing on CNC-05): A machine that stopped after a long period of rising vibration had a failed spindle bearing, so read the vibration trend leading up to the stop.
- **B** (Failed spindle bearing on CNC-05): After an unexpected stop, check maintenance records first; the stopped machine was past its bearing service interval.

## 15. `alarm` / `resolved` / `CNC-03`

Label: **same** (held out)

- **A** (Spindle bearing wear on CNC-03): For a vibration alarm, a long steady upward trend on just one machine was the sign of a failing spindle bearing; replacing it cleared the alarm.
- **B** (Spindle bearing wear on CNC-03): If the vibration alarm is on one machine, pull that machine's vibration history and compare it with the rest of the line; a gradual, sustained increase on that machine only is characteristic of spindle bearing wear, which replacement fixed.

## 16. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): Check maintenance records for when the spindle bearing was last serviced; an overdue bearing explained the vibration alarm.
- **B** (Spindle bearing wear on CNC-03): Rising motor load alongside vibration on the alarmed machine was the clearest early sign; vibration alone was noisy.

## 17. `inspection_failures` / `resolved` / `CNC-02`

Label: **different**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Rejects from one machine only: check its spindle speed setting.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Check whether failed jobs share a material batch before blaming a machine; here they did not, which ruled out the batch.

## 18. `inspection_failures` / `unresolved` / `CNC-01`

Label: **same**

- **A** (Spindle speed off standard on CNC-01): reset_setting on CNC-01 was tried for inspection_failures and the check afterwards found it unresolved.
- **B** (CNC-01 speed setting wrong for the current job): reset_setting on CNC-01 was tried for inspection_failures and the check afterwards found it unresolved.

## 19. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): A slow, steady vibration rise confined to the alarmed machine indicated spindle bearing wear, so compare its vibration history against the other machines first.
- **B** (Spindle bearing wear on CNC-03): For a vibration alarm, a long steady upward trend on just one machine was the sign of a failing spindle bearing; replacing it cleared the alarm.

## 20. `alarm` / `resolved` / `CNC-03`

Label: **different** (held out)

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Wrong spindle speed setting on CNC-03): A steady vibration rise on one machine was not the bearing; the spindle speed had been set high, and resetting it cleared the alarm.

## 21. `inspection_failures` / `resolved` / `CNC-02`

Label: **different**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Look at the setting change log for the machine with the rejects; the failures began right after the spindle speed was changed.

## 22. `alarm` / `unresolved` / `CNC-04`

Label: **same**

- **A** (Spindle bearing wear on CNC-04): replace_bearing on CNC-04 was tried for alarm and the check afterwards found it unresolved.
- **B** (Worn spindle bearing causing high vibration on CNC-04): replace_bearing on CNC-04 was tried for alarm and the check afterwards found it unresolved.

## 23. `inspection_failures` / `resolved` / `CNC-02`

Label: **different**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Inspection failures clustered on a single machine pointed to a wrong spindle speed setting there, so group failed jobs by machine before anything else.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Look at the setting change log for the machine with the rejects; the failures began right after the spindle speed was changed.

## 24. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): For a vibration alarm, a long steady upward trend on just one machine was the sign of a failing spindle bearing; replacing it cleared the alarm.

## 25. `status` / `resolved` / `CNC-05`

Label: **different** (held out)

- **A** (Failed spindle bearing on CNC-05): Unexpected stop: check the vibration trend before it; a long rise means the bearing failed.
- **B** (Wrong spindle speed setting on CNC-05): An unexpected stop with normal vibration but high load pointed to the speed setting rather than the bearing.

## 26. `routine_check` / `resolved` / `CNC-01`

Label: **same**

- **A** (Early spindle bearing wear on CNC-01): During a routine check, compare each machine's vibration trend with the others; one machine drifting upward slowly had early spindle bearing wear.
- **B** (Early spindle bearing wear on CNC-01): A routine check found early bearing wear by spotting the one machine whose vibration crept up while the rest stayed flat.

## 27. `status` / `resolved` / `CNC-05`

Label: **same**

- **A** (Failed spindle bearing on CNC-05): When a machine stops unexpectedly, review its vibration history before the stop; a steady climb beforehand showed the spindle bearing had failed.
- **B** (Failed spindle bearing on CNC-05): A machine that stopped after a long period of rising vibration had a failed spindle bearing, so read the vibration trend leading up to the stop.

## 28. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): Check maintenance records for when the spindle bearing was last serviced; an overdue bearing explained the vibration alarm.

## 29. `inspection_failures` / `resolved` / `CNC-02`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Before blaming a machine for rejects, check whether the failed jobs used the same material batch; they did not, which ruled the batch out.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When failed jobs came from one machine and the same batch ran fine elsewhere, the cause was that machine's setting, not the material.

## 30. `inspection_failures` / `resolved` / `CNC-02`

Label: **same** (held out)

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Rejects from one machine only: check its spindle speed setting.

## 31. `routine_check` / `resolved` / `CNC-01`

Label: **same**

- **A** (Early spindle bearing wear on CNC-01): During a routine check, compare each machine's vibration trend with the others; one machine drifting upward slowly had early spindle bearing wear.
- **B** (Early spindle bearing wear on CNC-01): Routine check: the one machine with slowly rising vibration had early bearing wear.

## 32. `status` / `resolved` / `CNC-05`

Label: **same**

- **A** (Failed spindle bearing on CNC-05): A machine that stopped after a long period of rising vibration had a failed spindle bearing, so read the vibration trend leading up to the stop.
- **B** (Failed spindle bearing on CNC-05): Unexpected stop: check the vibration trend before it; a long rise means the bearing failed.

## 33. `inspection_failures` / `unresolved` / `CNC-01`

Label: **different**

- **A** (Bearing wear on CNC-01 causing dimensional variance): replace_bearing on CNC-01 was tried for inspection_failures and the check afterwards found it unresolved.
- **B** (Spindle speed off standard on CNC-01): reset_setting on CNC-01 was tried for inspection_failures and the check afterwards found it unresolved.

## 34. `alarm` / `resolved` / `CNC-03`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-03): A vibration alarm that began at a job change was caused by an incorrect spindle speed, so check the speed setting against the job's standard before suspecting the bearing.
- **B** (Wrong spindle speed setting on CNC-03): Vibration that jumped suddenly rather than climbing was a setting problem, not wear; check the spindle speed history.

## 35. `alarm` / `resolved` / `CNC-03`

Label: **different** (held out)

- **A** (Spindle bearing wear on CNC-03): A slow, steady vibration rise confined to the alarmed machine indicated spindle bearing wear, so compare its vibration history against the other machines first.
- **B** (Wrong spindle speed setting on CNC-03): A vibration alarm that began at a job change was caused by an incorrect spindle speed, so check the speed setting against the job's standard before suspecting the bearing.

## 36. `status` / `resolved` / `CNC-05`

Label: **different**

- **A** (Failed spindle bearing on CNC-05): When a machine stops unexpectedly, review its vibration history before the stop; a steady climb beforehand showed the spindle bearing had failed.
- **B** (Wrong spindle speed setting on CNC-05): An unexpected stop with normal vibration but high load pointed to the speed setting rather than the bearing.

## 37. `alarm` / `resolved` / `CNC-03`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-03): When vibration alarms right after a job change, compare the machine's spindle speed with the standard for that job; a wrong speed setting caused the vibration.
- **B** (Wrong spindle speed setting on CNC-03): Vibration that jumped suddenly rather than climbing was a setting problem, not wear; check the spindle speed history.

## 38. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): Steady single-machine vibration rise means a worn spindle bearing; compare against the other machines.
- **B** (Spindle bearing wear on CNC-03): Check maintenance records for when the spindle bearing was last serviced; an overdue bearing explained the vibration alarm.

## 39. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Wrong spindle speed setting on CNC-03): When vibration alarms right after a job change, compare the machine's spindle speed with the standard for that job; a wrong speed setting caused the vibration.

## 40. `routine_check` / `resolved` / `CNC-01`

Label: **different** (held out)

- **A** (Early spindle bearing wear on CNC-01): During a routine check, compare each machine's vibration trend with the others; one machine drifting upward slowly had early spindle bearing wear.
- **B** (Spindle speed set off standard on CNC-01): Routine checks should include spindle speed against the job standard; a mis-set machine was caught before it produced rejects.

## 41. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): Steady single-machine vibration rise means a worn spindle bearing; compare against the other machines.

## 42. `inspection_failures` / `resolved` / `CNC-02`

Label: **unsure**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When failed jobs came from one machine and the same batch ran fine elsewhere, the cause was that machine's setting, not the material.

## 43. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Inspection failures clustered on a single machine pointed to a wrong spindle speed setting there, so group failed jobs by machine before anything else.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When jobs start failing inspection, first find out which machine made them; if every failure came from the same machine, compare its spindle speed against the job standard, because a mis-set speed produced the dimensional rejects.

## 44. `alarm` / `resolved` / `CNC-03`

Label: **different**

- **A** (Spindle bearing wear on CNC-03): For a vibration alarm, a long steady upward trend on just one machine was the sign of a failing spindle bearing; replacing it cleared the alarm.
- **B** (Spindle bearing wear on CNC-03): Check maintenance records for when the spindle bearing was last serviced; an overdue bearing explained the vibration alarm.

## 45. `alarm` / `resolved` / `CNC-03`

Label: **unsure** (held out)

- **A** (Spindle bearing wear on CNC-03): Watch motor load together with vibration on the alarmed machine; the load increase gave a clearer early warning than the noisy vibration readings.
- **B** (Spindle bearing wear on CNC-03): Look at the alarmed machine's vibration and temperature history together: both rising gradually while neighbours stayed flat pointed to the spindle bearing.

## 46. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-03): When vibration alarms right after a job change, compare the machine's spindle speed with the standard for that job; a wrong speed setting caused the vibration.
- **B** (Wrong spindle speed setting on CNC-03): A vibration alarm that began at a job change was caused by an incorrect spindle speed, so check the speed setting against the job's standard before suspecting the bearing.

## 47. `status` / `resolved` / `CNC-05`

Label: **different**

- **A** (Failed spindle bearing on CNC-05): After an unexpected stop, check maintenance records first; the stopped machine was past its bearing service interval.
- **B** (Wrong spindle speed setting on CNC-05): An unexpected stop with normal vibration but high load pointed to the speed setting rather than the bearing.

## 48. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Rejects from one machine only: check its spindle speed setting.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When jobs start failing inspection, first find out which machine made them; if every failure came from the same machine, compare its spindle speed against the job standard, because a mis-set speed produced the dimensional rejects.

## 49. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): A slow, steady vibration rise confined to the alarmed machine indicated spindle bearing wear, so compare its vibration history against the other machines first.

## 50. `status` / `resolved` / `CNC-05`

Label: **different** (held out)

- **A** (Failed spindle bearing on CNC-05): When a machine stops unexpectedly, review its vibration history before the stop; a steady climb beforehand showed the spindle bearing had failed.
- **B** (Wrong spindle speed setting on CNC-05): When a machine stops, check its vibration trend before the stop; a flat trend ruled out the bearing and pointed to the speed setting.

## 51. `alarm` / `resolved` / `CNC-03`

Label: **unsure**

- **A** (Spindle bearing wear on CNC-03): Look at the alarmed machine's vibration and temperature history together: both rising gradually while neighbours stayed flat pointed to the spindle bearing.
- **B** (Spindle bearing wear on CNC-03): For a vibration alarm, a long steady upward trend on just one machine was the sign of a failing spindle bearing; replacing it cleared the alarm.

## 52. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Inspection failures clustered on a single machine pointed to a wrong spindle speed setting there, so group failed jobs by machine before anything else.

## 53. `alarm` / `resolved` / `CNC-03`

Label: **same**

- **A** (Spindle bearing wear on CNC-03): Rising motor load alongside vibration on the alarmed machine was the clearest early sign; vibration alone was noisy.
- **B** (Spindle bearing wear on CNC-03): Watch motor load together with vibration on the alarmed machine; the load increase gave a clearer early warning than the noisy vibration readings.

## 54. `alarm` / `resolved` / `CNC-03`

Label: **unsure**

- **A** (Spindle bearing wear on CNC-03): When a vibration alarm fires, check whether vibration has been climbing steadily on that machine alone; a gradual one-machine rise pointed to a worn spindle bearing.
- **B** (Spindle bearing wear on CNC-03): Look at the alarmed machine's vibration and temperature history together: both rising gradually while neighbours stayed flat pointed to the spindle bearing.

## 55. `alarm` / `resolved` / `CNC-03`

Label: **different** (held out)

- **A** (Spindle bearing wear on CNC-03): Look at the alarmed machine's vibration and temperature history together: both rising gradually while neighbours stayed flat pointed to the spindle bearing.
- **B** (Spindle bearing wear on CNC-03): Rising motor load alongside vibration on the alarmed machine was the clearest early sign; vibration alone was noisy.

## 56. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Check whether failed jobs share a material batch before blaming a machine; here they did not, which ruled out the batch.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Before blaming a machine for rejects, check whether the failed jobs used the same material batch; they did not, which ruled the batch out.

## 57. `inspection_failures` / `resolved` / `CNC-02`

Label: **different**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): When several jobs fail inspection, check which machine they ran on; when the failures all came from one machine, its spindle speed setting was off standard.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Check whether failed jobs share a material batch before blaming a machine; here they did not, which ruled out the batch.

## 58. `routine_check` / `resolved` / `CNC-01`

Label: **different**

- **A** (Early spindle bearing wear on CNC-01): During a routine check, compare each machine's vibration trend with the others; one machine drifting upward slowly had early spindle bearing wear.
- **B** (Spindle speed set off standard on CNC-01): On a routine check, compare each machine's spindle speed with its job standard; one was set off standard before any rejects appeared.

## 59. `inspection_failures` / `resolved` / `CNC-02`

Label: **same**

- **A** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): Look at the setting change log for the machine with the rejects; the failures began right after the spindle speed was changed.
- **B** (Wrong spindle speed setting on CNC-02 causing dimensional rejects): The rejects started immediately after a spindle speed change on that machine, so check its recent setting changes first.

## 60. `alarm` / `resolved` / `CNC-03`

Label: **different** (held out)

- **A** (Spindle bearing wear on CNC-03): If the vibration alarm is on one machine, pull that machine's vibration history and compare it with the rest of the line; a gradual, sustained increase on that machine only is characteristic of spindle bearing wear, which replacement fixed.
- **B** (Wrong spindle speed setting on CNC-03): When vibration alarms right after a job change, compare the machine's spindle speed with the standard for that job; a wrong speed setting caused the vibration.
