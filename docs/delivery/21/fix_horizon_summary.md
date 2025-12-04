# Horizon Reduction Fix Summary

## Problem Identified
The orchestrator's ASP fallback was finding 0 models while direct tests found 2 models. Root cause: horizon reduction was selecting a window (Dec 7-8) that didn't include the actual busy slots (Dec 3-4), resulting in empty busy/work_hours slots.

## Fixes Applied
1. **Prioritize busy slots over time window**: Changed logic to start from busy slots first, then intersect with time window
2. **Fix intersection logic**: Ensure busy slots are always included in the reduced window
3. **Work hours regeneration**: Added logic to regenerate work hours for the new horizon (though this still needs completion)

## Status
- Horizon reduction logic has been updated but still needs testing
- Work hours regeneration is partially implemented but needs completion
- Need to verify that the reduced window actually includes busy slots and work hours

