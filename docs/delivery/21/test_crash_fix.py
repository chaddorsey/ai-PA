#!/usr/bin/env python3
"""
Test to verify the Clingo crash fix (segfault when accessing model.cost after solve context).
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.clingo_wrapper import ClingoSolver

# Simple ASP program that will produce a model with costs
test_program = """
#const n=3.
{ p(1..n) }.
:- not p(1), not p(2), not p(3).
#minimize { 1@p(1); 2@p(2); 3@p(3) }.
"""

if __name__ == "__main__":
    print("Testing Clingo crash fix...")
    print("=" * 60)
    
    solver = ClingoSolver(timeout=5)
    model, stats, result = solver.solve(test_program)
    
    print(f"Solve result: satisfiable={result.satisfiable}")
    print(f"Models found: {stats.get('models_found', 0)}")
    print(f"Cost: {stats.get('cost', 'N/A')}")
    
    if model:
        print("\n✓ Model returned successfully (no crash)")
        print(f"  Model type: {type(model)}")
        if isinstance(model, dict):
            print(f"  Model has symbols: {'symbols' in model}")
            print(f"  Model has cost: {'cost' in model}")
            print(f"  Cost value: {model.get('cost', 'N/A')}")
    else:
        print("\n✗ No model returned")
    
    print("\n" + "=" * 60)
    print("Test complete - if you see this, no crash occurred!")

